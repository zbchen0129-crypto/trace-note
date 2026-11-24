"""Bounded offline workflow acceptance using a real public-domain excerpt."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.core import Store
from backend.service import Service
from eval.long_context import guard_memory, memory_mb

def read(path):
    if path.stat().st_size>128000:raise RuntimeError('Input exceeds 128 KB')
    return json.loads(path.read_text())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--node',default='node');args=parser.parse_args()
    guard_memory()
    source=read(ROOT/'eval/real-source.json')
    with tempfile.TemporaryDirectory(prefix='tracenote-real-') as temp:
        folder=Path(temp);stages=[]
        def run(stage):
            result=subprocess.run([args.node,str(ROOT/'eval/real_workflow.js'),stage,temp],capture_output=True,text=True,timeout=20,check=True)
            if len(result.stdout)>10000:raise RuntimeError('Unexpected child output size')
            stages.append(json.loads(result.stdout));guard_memory()
        run('prepare')
        store=Store(folder/'isolated.db')
        r=store.save(0,read(folder/'base.json'))
        r=store.save(r['revision'],read(folder/'reviewed.json'))
        ids=read(folder/'ids.json')
        # Only metadata specificity changes; original text and old reviews stay immutable.
        doc=next(d for d in r['state']['documents'] if d['id']==ids['documentId'])
        service=Service(store,None)
        r=service.correct_source({'revision':r['revision'],'documentId':doc['id'],'source':{**doc['source'],'locator':source['locator']},'reason':'验收：补充核对后的版次与摘录定位；不把起始页当作完整摘录页码。'})
        (folder/'corrected.json').write_text(json.dumps(r['state']))
        run('finish')
        r=store.save(r['revision'],read(folder/'reconfirmed.json'))
        restored=store.restore(r['revision'],r['state'])
        assert restored['state']['reviews']==r['state']['reviews']
        assert restored['state']['sourceRevisions']==r['state']['sourceRevisions']
        out=ROOT/'eval/results/real-workflow-v1';out.mkdir(parents=True,exist_ok=True)
        for name in ('evidence','reconfirmed'):
            (out/f'{name}.json').write_text((folder/f'{name}.json').read_text())
        result={'kind':'offline workflow acceptance; assistant-authored decisions','sourceUrl':source['sourceUrl'],'sourceTextSha256':source['sha256'],'realExcerpts':1,'researchQuestions':2,'liveModelCalls':0,'checks':['literal evidence and source preserved','opposition excluded from support group','question isolation','source correction invalidates both questions','one-question reconfirmation leaves other stale','SQLite save and backup restore','portable evidence report'],'stages':stages,'pythonPeakRssMiB':memory_mb(),'memoryBudgetMiBPerProcess':256,'limits':'128 KB input files, one excerpt, sequential child processes, 20 seconds per child; checkpoint RSS guard, not machine-wide allocation ceiling','codeHashes':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['web/domain.js','backend/core.py','backend/service.py','eval/real_workflow.js','eval/real_workflow.py']}}
        guard_memory();(out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
