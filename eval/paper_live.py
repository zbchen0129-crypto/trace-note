"""Frozen two-call real-paper context check; no retries, including interrupted calls."""
import argparse
import copy
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.model import OpenAIModel, validate_output
from eval.long_context import read_json, guard_memory, memory_mb
from eval.run import digest
from server import load_env

ARMS=('excerptOnly','withAuthorResults')
BOOK={'id':1,'labels':[{'id':'engagement','name':'推文计数代表学术交流',
 'definition':'将论文推文计数视为学术交流或参与的指标这一观点。',
 'include':'记录与当前研究问题有关的支持、反对、引述或不确定态度。',
 'exclude':'无关主题；不将样本范围自动推广到所有平台活动。'}]}

def payload_for(fixture,arm):
    if arm not in ARMS:raise ValueError('Unknown arm')
    return {'researchQuestion':fixture['researchQuestion'],
      'researchScope':{'subject':'本文作者 Robinson-Garcia 等对被引观点的评价；区分被引作者 Priem & Costello', 'timeframe':'2017 年本文研究的牙科论文推文样本'},
      'sourceMetadata':{'type':'paper','author':fixture['authors'],'year':fixture['year'],'url':fixture['sourceUrl'],'locator':fixture['selection']},
      'paragraph':{k:v for k,v in fixture['paragraphs'][0].items() if k!='sha256'},
      'context':[{k:v for k,v in fixture['paragraphs'][1].items() if k!='sha256'}] if arm=='withAuthorResults' else [],
      'codebookVersion':copy.deepcopy(BOOK)}

def score(fixture,arm,output):
    items=output.get('annotations',[]);a=items[0] if len(items)==1 else {}
    stance=a.get('stance');source=a.get('stanceParagraphId')
    signals=bool(output.get('reviewReasons') or output.get('abstainReason'))
    # Abstention is valid for the incomplete view, but is reported separately.
    abstained=not items and signals
    source_ok=source==('P008' if arm=='withAuthorResults' else 'P007')
    matched=(len(items)==1 and a.get('labelId')=='engagement' and stance in fixture['reference'][arm] and source_ok) or (arm=='excerptOnly' and abstained)
    return {'arm':arm,'expectedStances':fixture['reference'][arm],'observed':stance,'stanceParagraphId':source,'abstainedWithReason':abstained,'stanceAndSourceMatched':matched,'holder':a.get('holder'),'holderRequiresManualInspection':True}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
    fixture=read_json(ROOT/'eval/paper-attribution.json');guard_memory()
    for p in fixture['paragraphs']:
        if digest(p['text'].encode())!=p['sha256']:raise SystemExit('Source hash mismatch')
    payloads={arm:payload_for(fixture,arm) for arm in ARMS}
    if any(len(json.dumps(p,ensure_ascii=False))>8000 for p in payloads.values()):raise SystemExit('Input exceeds 8000 characters')
    load_env();model=OpenAIModel()
    out=ROOT/'eval/results/paper-live-v1';out.mkdir(parents=True,exist_ok=True)
    manifest={'fixtureHash':digest(fixture),'payloadsHash':digest(payloads),'adapterHash':digest((ROOT/'backend/model.py').read_bytes()),'runnerHash':digest(Path(__file__).read_bytes()),'model':model.model,'maxLiveCalls':2,'maxInputChars':8000,'maxResponseTokens':2500,'memoryBudgetMiB':256,'retries':0}
    path=out/'manifest.json'
    if path.exists() and read_json(path)!=manifest:raise SystemExit('Inputs/model changed; preserve frozen directory')
    if not path.exists():path.write_text(json.dumps(manifest,indent=2))
    rows=[];calls=0
    for arm in ARMS:
        guard_memory();path=out/f'{arm}.json';payload=payloads[arm]
        if path.exists():
            row=read_json(path)
            if row.get('payload')!=payload:raise SystemExit('Cached payload differs')
        elif args.live:
            if not model.configured:raise SystemExit('Model is not configured; no call made')
            row={'arm':arm,'payload':payload,'validation':'started'}
            # Persist before transmission: an interrupted/failed request is never retried.
            path.write_text(json.dumps(row,ensure_ascii=False,indent=2));calls+=1
            print(json.dumps({'starting':arm,'call':calls,'peakRssMiB':round(memory_mb(),2)}),flush=True)
            try:
                row['output']=model.generate('annotation',payload)
                validate_output('annotation',row['output'],payload['paragraph'],BOOK['labels'],payload['context'])
                row['validation']='accepted'
            except Exception as error:
                row.update(validation='failed',errorType=type(error).__name__)
            row['peakRssMiB']=round(memory_mb(),2)
            path.write_text(json.dumps(row,ensure_ascii=False,indent=2));guard_memory()
        else:
            print(json.dumps({'pending':arm,'inputChars':len(json.dumps(payload,ensure_ascii=False))}));continue
        if row['validation']!='accepted':raise SystemExit('Failure/interruption preserved; stop without retry')
        rows.append(score(fixture,arm,row['output']))
    if len(rows)==2:
        report={'manifest':manifest,'newCalls':calls,'peakRssMiB':round(guard_memory(),2),'results':rows,'limitations':'One real paper, two selected non-contiguous excerpts, one sample per arm; assistant-authored references. Explicit citation attribution metadata provided in both views. Checks context sensitivity, not independent accuracy or causal improvement. Holder and semantic scope require manual inspection.'}
        target=out/'report.json'
        if not target.exists():target.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
