"""Four sequential stance checks; synthetic references, not independent evidence."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from eval.long_context import read_json, guard_memory, memory_mb
from eval.run import digest
from server import load_env
from backend.model import OpenAIModel, validate_output
from backend.core import Problem


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
    cases=read_json(ROOT/'eval/stance-cases.json')
    if len(cases)>4:raise ValueError('At most four sequential cases')
    load_env();model=OpenAIModel()
    book={'id':1,'labels':[{'id':'livingStandard','name':'生活水平提升','definition':'生活水平提升被讨论为退出公共交通的候选原因。','include':'对这一解释的支持、反对、引用或疑问均记录，并分别判断态度。','exclude':'无关主题。'}]}
    manifest={'casesHash':digest(cases),'bookHash':digest(book),'adapterHash':digest((ROOT/'backend/model.py').read_bytes()),'runnerHash':digest(Path(__file__).read_bytes()),'model':model.model}
    out=ROOT/'eval/results/stance-v1';out.mkdir(parents=True,exist_ok=True)
    path=out/'manifest.json'
    if path.exists() and read_json(path)!=manifest:raise ValueError('Inputs changed; preserve existing results')
    path.write_text(json.dumps(manifest,indent=2))
    rows=[]
    for case in cases:
        guard_memory();path=out/(case['id']+'.json')
        payload={'paragraph':{'id':case['id'],'text':case['text']},'context':[],'codebookVersion':book,'researchQuestion':'本文作者是否认可生活水平提升导致当前退出公共交通这一解释？'}
        if len(json.dumps(payload))>32000:raise ValueError('Input budget exceeded')
        if path.exists():row=read_json(path)
        elif args.live:
            row={'id':case['id'],'payload':payload}
            try:
                row['output']=model.generate('annotation',payload)
                validate_output('annotation',row['output'],payload['paragraph'],book['labels'])
                row['validation']='accepted'
            except Problem as e:
                row.update(validation='failed',error=str(e))
            row['peakRssMiB']=round(memory_mb(),2)
            path.write_text(json.dumps(row,ensure_ascii=False,indent=2))
            guard_memory()
        else:raise SystemExit('Missing cache; --live permits at most four calls')
        if row['validation']!='accepted':raise SystemExit('Failure recorded; stop without retry')
        annotations=row['output']['annotations']
        rows.append({'id':case['id'],'expected':case['stance'],'observed':[a.get('stance') for a in annotations], 'matched':len(annotations)==1 and annotations[0].get('stance')==case['stance']})
        print(json.dumps(rows[-1],ensure_ascii=False),flush=True)
    result={'manifest':manifest,'peakRssMiB':round(memory_mb(),2),'results':rows,'limit':'One sample on four assistant-authored cases; not held out, not a semantic guarantee.'}
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
