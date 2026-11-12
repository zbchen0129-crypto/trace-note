"""Bounded live synthetic benchmark. No test references are sent to the model."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import load_env
from backend.model import OpenAIModel, validate_output
from backend.core import Problem

BASELINE = ('请根据给定研究问题、标签定义和上下文给当前段落做多标签标注，'
            '提供原文引文。没有适用标签时返回空数组。需要复核时填写 reviewReasons，'
            '不确定时填写 abstainReason。按给定 JSON 格式返回。')
ARMS = ('direct','workbench')


def digest(value):
    raw = value if isinstance(value,bytes) else json.dumps(value,sort_keys=True,ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def divide(a,b): return a/b if b else None


def scores(rows,cases,label_ids):
    refs={c['id']:set(c['expectedLabels']) for c in cases}
    counts={k:{'tp':0,'fp':0,'fn':0,'support':0} for k in label_ids}
    exact=errors=quote_total=quote_exact=quote_unique=accepted=neg_ok=neg_count=unknown_fp=0
    failures=[]
    for row in rows:
        truth=refs[row['caseId']]; raw=row.get('output'); usable=isinstance(raw,dict) and isinstance(raw.get('annotations'),list)
        predicted={a.get('labelId') for a in raw['annotations'] if isinstance(a,dict)} if usable else set()
        predicted.discard(None)
        unknown_fp += len(predicted-set(label_ids))
        errors += not usable
        accepted += row.get('validation') == 'accepted'
        correct = usable and predicted == truth
        exact += correct
        if not truth: neg_count+=1; neg_ok+=correct
        for label in label_ids:
            c=counts[label]; c['tp']+=label in truth and label in predicted; c['fp']+=label not in truth and label in predicted; c['fn']+=label in truth and label not in predicted; c['support']+=label in truth
        if not correct or row.get('validation') != 'accepted': failures.append({'caseId':row['caseId'],'expected':sorted(truth),'predicted':sorted(predicted),'validation':row.get('validation'),'error':row.get('error')})
        text=row['payload']['paragraph']['text']
        for a in raw.get('annotations',[]) if usable else []:
            quote_total+=1
            q=a.get('quote') if isinstance(a,dict) else None
            valid=isinstance(q,str) and bool(q.strip())
            quote_exact+=bool(valid and q in text)
            quote_unique+=bool(valid and text.count(q)==1)
    tp=sum(c['tp'] for c in counts.values()); fp=unknown_fp+sum(c['fp'] for c in counts.values()); fn=sum(c['fn'] for c in counts.values())
    for c in counts.values():
        c.update(precision=divide(c['tp'],c['tp']+c['fp']),recall=divide(c['tp'],c['tp']+c['fn']),f1=divide(2*c['tp'],2*c['tp']+c['fp']+c['fn']))
    f1s=[c['f1'] for c in counts.values() if c['f1'] is not None]
    return {'unknownLabelPredictions':unknown_fp,'n':len(rows),'microPrecision':divide(tp,tp+fp),'microRecall':divide(tp,tp+fn),'microF1':divide(2*tp,2*tp+fp+fn),'macroF1':sum(f1s)/len(f1s) if f1s else None,'exactMatch':divide(exact,len(rows)),'negativeExact':divide(neg_ok,neg_count),'negativeCount':neg_count,'responseErrors':errors,'acceptedCoverage':divide(accepted,len(rows)),'quoteCount':quote_total,'exactQuoteRate':divide(quote_exact,quote_total),'uniqueQuoteRate':divide(quote_unique,quote_total),'byLabel':counts,'failures':failures}


def report(output,manifest,cases,rows):
    labels=[l['id'] for l in manifest['codebook']['labels']]
    metrics={arm:scores([r for r in rows if r['arm']==arm],cases,labels) for arm in ARMS}
    result={'manifest':manifest,'metrics':metrics}
    (output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    def pct(value): return 'N/A' if value is None else f'{value:.1%}'
    lines=['# TraceNote 合成案例评估','', '**这是开发助手编写的合成案例和参考标签，不是独立人工金标准或真实用户研究。**', '',f"模型：`{manifest['model']}`。固定规则 v{manifest['codebook']['id']}。每组 {len(cases)} 个案例，一次采样，无自动重试。",'', '| 指标 | 直接提示 | 工作台提示 + 校验 |','|---|---:|---:|']
    for key,name in [('microPrecision','多标签微平均精确率'),('microRecall','多标签微平均召回率'),('microF1','多标签微平均 F1'),('macroF1','宏平均 F1'),('exactMatch','段落标签完全匹配'),('negativeExact','无标签案例完全匹配'),('exactQuoteRate','原文子串匹配率'),('uniqueQuoteRate','原文唯一定位率'),('acceptedCoverage','校验通过覆盖率')]:
        lines.append(f'| {name} | {pct(metrics["direct"][key])} | {pct(metrics["workbench"][key])} |')
    lines += ['', '标签指标使用校验前的模型结果；格式失败作为未匹配并计漏标。通过率单独报告，不能通过丢弃失败样本抬高 F1。无标签样本完全匹配单独计数。空分母使用 N/A。引用字符串合法不证明其语义支持标签。', '', '两组使用相同模型、材料、上下文、规则、结构化输出格式和输出预算，仅提示不同。校验器对两组结果都作离线诊断；工作台实际会阻止不合格建议保存。基线也采用结构化输出，避免将解析差异误当成模型能力提升。人工审核未加入分数，未测量研究者耗时。', '', '## 错误与差异','']
    for arm in ARMS:
        lines.append(f'### {arm}')
        failures=metrics[arm]['failures']
        if not failures: lines.append('本次小样本中没有发现标签不匹配或校验失败。')
        for fail in failures: lines.append('- '+json.dumps(fail,ensure_ascii=False))
        lines.append('')
    lines += ['## 可以与不可以得出的结论','','这次实验用于检查软件和边界案例。即使指标相同或全部通过，也不证明工作台比直接提示更准确，更不能声称在真实访谈上达到相同水平。主题版本管理、人工审核和证据追溯的价值需要真实工作流和独立参与者验证。','', '尚未测量：独立人工证据支持率、研究者间分歧、复核耗时、重复运行稳定性。需要至少两位独立标注者先盲标再讨论分歧，保留不同解释；不能将开发助手的参考标签冒称人工一致意见。','',f"数据 SHA-256：`{manifest['casesHash']}`。规则 SHA-256：`{manifest['codebookHash']}`。完整请求数据和输出保存在同目录逐例 JSON 中，不含密钥。"]
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    return metrics


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--live',action='store_true'); parser.add_argument('--output',default='eval/results/context-v2'); parser.add_argument('--cases',default='eval/context-cases.json'); parser.add_argument('--max-calls',type=int,default=32); args=parser.parse_args()
    cases=json.loads((ROOT/args.cases).read_text()); codebook=json.loads((ROOT/'eval/codebook.json').read_text())
    load_env(); model=OpenAIModel()
    manifest={'model':model.model,'casesHash':digest(cases),'codebookHash':digest(codebook),'adapterHash':digest((ROOT/'backend/model.py').read_bytes()),'runnerHash':digest(Path(__file__).read_bytes()),'baselineInstructions':BASELINE,'codebook':codebook,'referenceType':'synthetic-assistant-authored-not-human-gold','sampling':'one response per case per arm; alternating arm order'}
    output=ROOT/args.output; output.mkdir(parents=True,exist_ok=True)
    path=output/'manifest.json'
    if path.exists() and json.loads(path.read_text()) != manifest: raise SystemExit('输入或实现已变化，请使用新的输出目录，不能混合运行。')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    rows=[]; calls=0
    for i,case in enumerate(cases):
        for arm in ARMS if i%2==0 else tuple(reversed(ARMS)):
            path=output/f'{case["id"]}-{arm}.json'
            if path.exists(): rows.append(json.loads(path.read_text())); continue
            if not args.live or calls>=args.max_calls: raise SystemExit('缺少缓存或已达到调用上限；使用 --live 运行，已有结果会复用。')
            if not model.configured: raise SystemExit('请配置本地密钥与模型。')
            payload={'paragraph':case['paragraph'],'context':case['context'],'codebookVersion':codebook,'researchQuestion':'当前为何放弃公共交通？'}
            row={'caseId':case['id'],'arm':arm,'payload':payload,'model':model.model}
            started=time.monotonic(); calls+=1
            try:
                value=model.generate('annotation',payload,**({'instructions_override':BASELINE} if arm=='direct' else {}))
                row['output']=value
                try:
                    validate_output('annotation',value,case['paragraph'],codebook['labels']); row['validation']='accepted'
                except Problem as error: row.update(validation='rejected',error=str(error))
            except Problem as error: row.update(validation='request_failed',error=str(error))
            row['seconds']=round(time.monotonic()-started,3)
            path.write_text(json.dumps(row,ensure_ascii=False,indent=2)); rows.append(row)
            print(f'{case["id"]} {arm}: {row["validation"]} ({row["seconds"]}s)',flush=True)
            if row['validation']=='request_failed': raise SystemExit('请求失败，停止后续计费调用；保留结果供检查。')
    metrics=report(output,manifest,cases,rows)
    print(json.dumps({arm:{k:v for k,v in m.items() if k not in ('byLabel','failures')} for arm,m in metrics.items()},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
