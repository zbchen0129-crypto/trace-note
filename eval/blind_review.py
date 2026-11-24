"""Build a reference-blind packet; validate/compare real submissions without inventing them."""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from eval.long_context import guard_memory
MAX_BYTES=128000
STANCES=('supports','opposes','mentions','unclear','out_of_scope')

def read(path):
    with Path(path).open('rb') as f:data=f.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError('File exceeds 128 KB')
    return json.loads(data)

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def packet():
    d=read(ROOT/'eval/real-source.json');p=read(ROOT/'eval/paper-attribution.json')
    for text,expected in [(d['text'],d['sha256']),*[(r['text'],r['sha256']) for r in p['paragraphs']]]:
        if hashlib.sha256(text.encode()).hexdigest()!=expected:raise ValueError('Source hash mismatch')
    sources=[{'id':'S1','title':d['title'],'author':d['author'],'year':d['year'],'url':d['sourceUrl'],'selection':d['normalization'],'rights':d['rights'],'paragraphs':[{'id':'D1','text':d['text'],'locator':d['locator']}]},
      {'id':'S2','title':p['title'],'author':p['authors'],'year':p['year'],'url':p['sourceUrl'],'selection':p['selection'],'rights':p['rights'],'paragraphs':[{k:r[k] for k in ('id','text','locator')} for r in p['paragraphs']]}]
    cases=[{'id':'R01','sourceId':'S1','question':'作者是否认可“眼睛的复杂性足以否定自然选择”这一观点？','scope':'仅判断给定摘录中的作者态度，不判断理论在当代科学中的真伪。'},
      {'id':'R02','sourceId':'S1','question':'作者是否提出“有用的渐变”作为回应困难的论证条件？','scope':'区分提出条件、证明条件以及一般事实主张。'},
      {'id':'R03','sourceId':'S2','question':p['researchQuestion'],'scope':'仅限本文牙科论文推文样本；请同时记录被讨论观点的提出者与本文评价者。'}]
    data={'studyId':'tracenote-reference-blind-v1','sources':sources,'cases':cases}
    return {**data,'packetHash':digest(data)}

INSTRUCTIONS='''# TraceNote 独立评审试填包

本包有 2 份真实来源、3 个判断任务。它是小规模可用性试填，不是代表性准确率研究。原文为英文，问题为中文；请记录英语熟悉程度。两项任务共享同一来源，因此不是三个独立样本。

你不知道开发参考判断和模型输出，但可以看到出处；这叫对参考答案盲评，不是匿名来源实验。请先独立阅读 materials.json，不查看项目仓库、模型结果或其他评审者答案。仅按包内摘录作答，不联网补读；缺少信息时可以选择 unclear 并说明需要哪些材料。若以前读过材料或看过参考判断，请在 priorExposure 中如实填写，组织者会单独解释。

填写 response-template.json 的副本：reviewerId 使用自己选的匿名代号，不填姓名或联系方式；englishFamiliarity 填阅读英文研究材料的熟悉程度；priorExposure 填既有接触（没有则填“无”）。packetHash 和 studyId 不修改。

逐题填写 completed=true、stance、claimHolder（被讨论观点提出者）、evaluator（你正在判断谁的态度）、evidence（原文引文数组，每项有 paragraphId 与 quote）、note（解释及不确定性）。引文须连续且可唯一定位，不能用翻译替代。证据不局限于句中某个关键词。无法确定人物时如实写“不明确”。

stance 可选：supports 支持问题所述观点；opposes 反对；mentions 仅提及/转述而未表态；unclear 无法确定；out_of_scope 摘录与问题无关。前三种必须提供至少一条原文证据；后两种可为空但必须解释。不能因为一个观点出现在引号中，就自动选择某种立场。支持某人提出条件，不等于认为该条件已被证明。

独立提交后保留原文件，先不要协商修改。组织者收齐两份后比较，再讨论分歧，并把讨论记录存成另一个文件。没有标准答题时长要求，本包不用于宣称提效。

本包不含开发参考、模型输出或自动判分答案。materials.json 中两个论文摘录不相邻，也不是原文顺序，逐段定位已保留。
'''

def build(destination):
    data=packet();template={'studyId':data['studyId'],'packetHash':data['packetHash'],'reviewerId':'','englishFamiliarity':'','priorExposure':'','answers':[{'caseId':c['id'],'completed':False,'stance':None,'claimHolder':'','evaluator':'','evidence':[],'note':''} for c in data['cases']]}
    files={'INSTRUCTIONS.md':INSTRUCTIONS,'materials.json':json.dumps(data,ensure_ascii=False,indent=2),'response-template.json':json.dumps(template,ensure_ascii=False,indent=2)}
    if any(len(v.encode())>MAX_BYTES for v in files.values()):raise ValueError('Packet file exceeds budget')
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    # The explicit allowlist prevents coordinator files/results entering the reviewer archive.
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
        for name,value in files.items():z.writestr(name,value)
    with zipfile.ZipFile(destination) as z:
        assert set(z.namelist())==set(files) and z.testzip() is None
    return {'archive':str(destination),'packetHash':data['packetHash'],'sources':2,'tasks':3,'reviewerSubmissions':0}

def validate(response,data):
    if response.get('studyId')!=data['studyId'] or response.get('packetHash')!=data['packetHash']:raise ValueError('Wrong packet/version')
    for field in ('reviewerId','englishFamiliarity','priorExposure'):
        if not isinstance(response.get(field),str) or not 1<=len(response[field].strip())<=500:raise ValueError('Missing/oversized '+field)
    answers=response.get('answers')
    if not isinstance(answers,list) or len(answers)!=len(data['cases']):raise ValueError('Expected exactly three answers')
    indexed={}
    for a in answers:
        if not isinstance(a,dict):raise ValueError('Answer must be an object')
        key=a.get('caseId')
        if not isinstance(key,str) or key in indexed:raise ValueError('Duplicate/invalid case ID')
        indexed[key]=a
    if set(indexed)!={c['id'] for c in data['cases']}:raise ValueError('Case IDs differ')
    for c in data['cases']:
        a=indexed[c['id']]
        if a.get('completed') is not True or a.get('stance') not in STANCES:raise ValueError('Incomplete answer '+c['id'])
        for field in ('claimHolder','evaluator','note'):
            if not isinstance(a.get(field),str) or not 1<=len(a[field].strip())<=2000:raise ValueError('Missing/oversized '+field)
        evidence=a.get('evidence');paragraphs={p['id']:p['text'] for s in data['sources'] if s['id']==c['sourceId'] for p in s['paragraphs']}
        if not isinstance(evidence,list) or len(evidence)>4:raise ValueError('At most four evidence quotes')
        if a['stance'] in STANCES[:3] and not evidence:raise ValueError('Evidence required')
        for e in evidence:
            if not isinstance(e,dict) or not isinstance(e.get('paragraphId'),str):raise ValueError('Invalid evidence')
            q=e.get('quote');text=paragraphs.get(e['paragraphId'],'')
            if not isinstance(q,str) or not q.strip() or len(q)>2000 or text.count(q)!=1:raise ValueError('Evidence missing, ambiguous, or outside case source')
    return indexed

def compare(left,right,data):
    a=validate(left,data);b=validate(right,data)
    if left['reviewerId'].strip()==right['reviewerId'].strip():raise ValueError('Two distinct reviewer IDs required')
    rows=[{'caseId':c['id'],'sourceId':c['sourceId'],'sameStance':a[c['id']]['stance']==b[c['id']]['stance'],'left':a[c['id']],'right':b[c['id']]} for c in data['cases']]
    return {'packetHash':data['packetHash'],'reviewers':[left['reviewerId'],right['reviewerId']],'priorExposure':[left['priorExposure'],right['priorExposure']],'stanceAgreements':sum(r['sameStance'] for r in rows),'taskCount':len(rows),'rows':rows,'warning':'Descriptive comparison only; not accuracy, independence, reliability coefficient, or adjudicated truth. Review attribution and evidence even when stances match. Preserve originals; save adjudication separately.'}

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('build');v=sub.add_parser('validate');v.add_argument('response');c=sub.add_parser('compare');c.add_argument('left');c.add_argument('right');args=parser.parse_args();guard_memory()
    if args.action=='build':result=build(ROOT/'artifacts/review/tracenote-blind-review-v1.zip')
    elif args.action=='validate':validate(read(args.response),packet());result={'valid':True,'meaning':'Structural/source validation only; no correctness scoring'}
    else:result=compare(read(args.left),read(args.right),packet())
    result['peakRssMiB']=round(guard_memory(),2);print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
