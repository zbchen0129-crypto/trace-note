import copy
import hashlib
import json
import uuid
from .core import Problem, require, now
from .model import validate_output


class Service:
    def __init__(self, store, model):
        self.store, self.model = store, model

    def suggest(self, args):
        require(self.model.configured, 'AI 尚未配置：请在本地 .env 填写密钥与模型名称后重启。')
        kind = args.get('kind')
        require(kind in ('annotation','rule'), '未知任务类型。')
        record = self.store.load()
        if record['revision'] != args.get('revision'):
            raise Problem('项目已更新，请刷新后生成建议。',409)
        s = record['state']; require(s is not None, '请先初始化项目。')
        p = next((p for p in s['paragraphs'] if p['id'] == args.get('paragraphId')),None)
        require(p is not None, '段落不存在。')
        version = s['versions'][-1]
        payload = {'paragraph':p,'codebookVersion':version,'researchQuestion':'当前为何放弃公共交通？'}
        doc = next(d for d in s['documents'] if d['id'] == p['documentId'])
        siblings = [x for x in s['paragraphs'] if x['documentId'] == p['documentId']]
        index = siblings.index(p)
        payload['context'] = [] if doc.get('fictional') else [x for x in siblings[max(0,index-1):index+2] if x['id'] != p['id']]
        if kind == 'rule':
            reviews = [r for r in s['reviews'] if r['paragraphId'] == p['id']]
            require(reviews and reviews[-1]['note'].strip(), '请先保存人工纠正及说明，再请求规则建议。')
            payload['humanReview'] = reviews[-1]
            payload['priorSuggestions'] = [x for x in s['suggestions'] if x['paragraphId'] == p['id'] and x['kind'] == 'annotation'][-1:]
        require(len(json.dumps(payload,ensure_ascii=False)) <= 40000, '当前段落及上下文过长，请拆分材料后重试。')
        job_id = args.get('requestId')
        require(isinstance(job_id,str) and 8 <= len(job_id) <= 80, '缺少有效请求 ID。')
        fingerprint = hashlib.sha256(json.dumps([kind,payload],sort_keys=True).encode()).hexdigest()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if job:
                require(job['fingerprint'] == fingerprint, '请求 ID 已用于不同内容。')
                if job['status'] == 'completed':
                    return self.store.load()
                raise Problem(job['error'] or '此请求仍在运行，请稍后刷新。',409)
            running = db.execute("SELECT id FROM jobs WHERE status='running'").fetchone()
            if running:
                raise Problem('已有模型任务运行中，请等待完成。',409)
            db.execute('INSERT INTO jobs(id,fingerprint,status) VALUES(?,?,?)',(job_id,fingerprint,'running'))
        try:
            value = validate_output(kind,self.model.generate(kind,payload),p,version['labels'])
            suggestion = {'id':str(uuid.uuid4()),'kind':kind,'paragraphId':p['id'],'versionId':version['id'],'createdAt':now(),'model':self.model.model,'output':value,'triggerReviewId':payload.get('humanReview',{}).get('id')}
            def append(current):
                # Restore can replace the project while an upstream request is in flight.
                require(current is not None and p in current['paragraphs'] and version in current['versions'], '材料或规则已恢复为另一份项目，放弃此请求结果。')
                current['suggestions'].append(suggestion)
                return current
            result = self.store.update(None,append,'ai-suggestion')
            with self.store.connect() as db:
                db.execute("UPDATE jobs SET status='completed',suggestion_id=? WHERE id=?",(suggestion['id'],job_id))
            return result
        except Exception as error:
            message = str(error) if isinstance(error,Problem) else '生成失败，请重试。'
            with self.store.connect() as db:
                db.execute("UPDATE jobs SET status='failed',error=? WHERE id=?",(message,job_id))
            if isinstance(error,Problem): raise
            raise Problem(message,502) from None

    def decide(self, args):
        def mutate(s):
            suggestion = next((x for x in s['suggestions'] if x['id'] == args.get('suggestionId')),None)
            require(suggestion is not None, '找不到建议。')
            require(not any(d['suggestionId'] == suggestion['id'] for d in s['decisions']), '此建议已经审核。')
            action = args.get('action'); require(action in ('accept','reject'), '未知审核操作。')
            decision = {'suggestionId':suggestion['id'],'createdAt':now(),'note':args.get('note','')}
            if action == 'reject':
                require(isinstance(decision['note'],str) and decision['note'].strip(), '请填写拒绝原因。')
                decision['status'] = 'rejected'
            else:
                require(suggestion['versionId'] == s['versions'][-1]['id'], '建议基于旧规则，请在当前规则下重新生成。')
                value = suggestion['output']
                if suggestion['kind'] == 'annotation':
                    review = copy.deepcopy(args.get('review'))
                    require(isinstance(review,dict) and review.get('paragraphId') == suggestion['paragraphId'] and review.get('versionId') == suggestion['versionId'], '审核段落或版本不匹配。')
                    review.update(id=len(s['reviews'])+1,source='human',suggestionId=suggestion['id'],createdAt=now())
                    s['reviews'].append(review)
                    decision['status'] = 'accepted' if review['annotations'] == value['annotations'] else 'modified'
                    decision['reviewId'] = review['id']
                else:
                    labels = args.get('labels')
                    require(isinstance(labels,list) and labels != s['versions'][-1]['labels'], '规则没有变化。')
                    reason = args.get('reason',''); require(isinstance(reason,str) and reason.strip(), '请填写修改原因。')
                    expected = copy.deepcopy(s['versions'][-1]['labels'])
                    next(l for l in expected if l['id'] == value['labelId'])[value['field']] = value['replacement']
                    decision['status'] = 'accepted' if labels == expected else 'modified'
                    s['versions'].append({'id':len(s['versions'])+1,'labels':labels,'reason':reason,'createdAt':now(),'suggestionId':suggestion['id']})
                    decision['versionId'] = s['versions'][-1]['id']
            s['decisions'].append(decision)
            return s
        return self.store.update(args.get('revision'),mutate,'ai-decision')
