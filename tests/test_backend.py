import copy
import json
import tempfile
import unittest
from pathlib import Path
from backend.core import Store, Problem, utf16len
from backend.service import Service
from backend.model import OpenAIModel, validate_output

SEED = json.loads((Path(__file__).resolve().parents[1]/'backend/seed.json').read_text())


class FakeModel:
    configured = True
    model = 'TEST-ONLY-NOT-A-REAL-MODEL'
    def __init__(self):
        self.calls = 0
        self.hook = None
    def generate(self,kind,payload):
        self.calls += 1
        if self.hook: self.hook()
        if kind == 'rule':
            return {'labelId':'reliability','field':'exclude','replacement':'已改善的历史问题不计入当前退出原因。','rationale':'人工纠正表明需要时间边界。'}
        return {'annotations':[{'labelId':'reliability','quote':'晚到二十分钟'}],'reviewReasons':[],'abstainReason':''}


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'db.sqlite3')
        self.record = self.store.save(0,copy.deepcopy(SEED))
        self.model = FakeModel(); self.service = Service(self.store,self.model)
    def tearDown(self): self.tmp.cleanup()
    def request(self,kind='annotation'):
        return {'revision':self.store.load()['revision'],'kind':kind,'paragraphId':'P001','requestId':f'request-{self.model.calls}'}
    def review(self,record,annotations):
        return {'paragraphId':'P001','versionId':record['state']['versions'][-1]['id'],'annotations':annotations,'note':'人工检查时间边界','status':'confirmed'}
    def test_persistence_and_conflict(self):
        self.assertEqual(Store(self.store.path).load(),self.record)
        self.store.save(1,self.record['state'])
        with self.assertRaises(Problem) as e: self.store.save(1,self.record['state'])
        self.assertEqual(e.exception.status,409)
    def test_immutable_source_and_invalid_evidence(self):
        changed = copy.deepcopy(self.record['state']); changed['paragraphs'][0]['text'] = '覆盖原文'
        with self.assertRaises(Problem): self.store.save(1,changed)
        changed = copy.deepcopy(self.record['state'])
        r = self.review(self.record,[{'labelId':'reliability','quote':'捏造','start':0,'end':2}]); r['id']=1
        changed['reviews'].append(r)
        with self.assertRaises(Problem): self.store.save(1,changed)
        self.assertEqual(self.store.load()['revision'],1)
    def test_utf16_and_hallucination(self):
        p={'text':'🚎晚点。'}; labels=SEED['versions'][0]['labels']
        value={'annotations':[{'labelId':'reliability','quote':'晚点'}],'reviewReasons':[],'abstainReason':''}
        out=validate_output('annotation',value,p,labels)
        self.assertEqual(out['annotations'][0]['start'],2)
        for text in ('没有证据','晚点晚点'):
            with self.assertRaises(Problem): validate_output('annotation',value,{'text':text},labels)
    def test_suggestion_does_not_confirm_and_idempotency(self):
        args=self.request(); result=self.service.suggest(args)
        self.assertEqual(result['state']['reviews'],[])
        # Retry with the same key and current revision does not spend again.
        args['revision']=result['revision']; self.service.suggest(args)
        self.assertEqual(self.model.calls,1)
        self.assertEqual(len(self.store.load()['state']['suggestions']),1)
    def test_accept_modified_and_reject(self):
        result=self.service.suggest(self.request()); suggestion=result['state']['suggestions'][0]
        args={'revision':result['revision'],'suggestionId':suggestion['id'],'action':'accept','review':self.review(result,[])}
        result=self.service.decide(args)
        self.assertEqual(result['state']['decisions'][0]['status'],'modified')
        with self.assertRaises(Problem): self.service.decide({**args,'revision':result['revision']})
        result=self.service.suggest(self.request()); sid=result['state']['suggestions'][-1]['id']
        result=self.service.decide({'revision':result['revision'],'suggestionId':sid,'action':'reject','note':'需要更多上下文'})
        self.assertEqual(len(result['state']['reviews']),1)
        self.assertEqual(result['state']['decisions'][-1]['status'],'rejected')
    def test_version_change_during_generation(self):
        def publish():
            r=self.store.load(); s=r['state']; v=copy.deepcopy(s['versions'][-1]); v['id']=2; v['reason']='新标准'; v['labels'][0]['exclude']='历史排除'; s['versions'].append(v); self.store.save(r['revision'],s)
        self.model.hook=publish
        result=self.service.suggest(self.request()); suggestion=result['state']['suggestions'][0]
        self.assertEqual(suggestion['versionId'],1)
        with self.assertRaises(Problem): self.service.decide({'revision':result['revision'],'suggestionId':suggestion['id'],'action':'accept','review':self.review(result,[])})
    def test_rule_requires_correction_and_explicit_publish(self):
        with self.assertRaises(Problem): self.service.suggest(self.request('rule'))
        s=self.record['state']; r=self.review(self.record,[]); r.update(id=1,createdAt='test',source='human'); s['reviews'].append(r); self.store.save(1,s)
        result=self.service.suggest(self.request('rule')); suggestion=result['state']['suggestions'][0]
        self.assertEqual(len(result['state']['versions']),1)
        labels=copy.deepcopy(result['state']['versions'][0]['labels']); labels[0]['exclude']=suggestion['output']['replacement']
        result=self.service.decide({'revision':result['revision'],'suggestionId':suggestion['id'],'action':'accept','labels':labels,'reason':'确认时间边界'})
        self.assertEqual(len(result['state']['versions']),2)
        self.assertEqual(result['state']['decisions'][0]['status'],'accepted')
    def test_failure_recorded_no_suggestion(self):
        self.model.hook=lambda: (_ for _ in ()).throw(Problem('测试错误'))
        with self.assertRaises(Problem): self.service.suggest(self.request())
        self.assertEqual(self.store.load()['state']['suggestions'],[])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0],'failed')
    def test_restore_preserves_prior_snapshot(self):
        self.store.restore(1,SEED)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone()[0],2)
    def test_missing_configuration_never_generates(self):
        model=OpenAIModel(); model.key=''; model.model=''
        with self.assertRaises(Problem): Service(self.store,model).suggest(self.request())
        self.assertEqual(self.store.load()['revision'],1)


if __name__=='__main__': unittest.main()
