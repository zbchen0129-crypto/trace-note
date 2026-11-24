import copy,json,tempfile,unittest
from pathlib import Path
from backend.core import Store,Problem
from backend.service import Service
from backend.model import validate_output

class Model:
    configured=True
    model='TEST-ONLY'
    calls=0
    def generate(self,kind,payload):
        self.calls+=1
        return {'annotations':[{'labelId':'cost','quote':'票价过高','holder':'被引研究','stance':'opposes','stanceQuote':'本文反对票价解释。','stanceParagraphId':'P004'}],'reviewReasons':[],'abstainReason':''}

class ContextLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db')
        s=json.loads((Path(__file__).resolve().parents[1]/'backend/seed.json').read_text())
        s['documents']=[{'id':'d','name':'同一材料'},{'id':'other','name':'其他材料'}]
        s['paragraphs']=[{'id':f'P{i:03}','documentId':'d' if i<5 else 'other','text':t} for i,t in enumerate(['有研究称票价过高。','背景甲','背景乙','本文反对票价解释。','别的材料'],1)]
        s['reviews']=[];s['nextParagraph']=6
        self.store.save(0,s);self.model=Model();self.service=Service(self.store,self.model)
        self.args={'revision':1,'kind':'annotation','paragraphId':'P001','contextIds':['P004'],'requestId':'test-context-1'}
    def tearDown(self):self.tmp.cleanup()
    def test_preview_does_not_call_model_and_matches_saved_request(self):
        preview=self.service.preview(self.args)
        self.assertEqual(self.model.calls,0);self.assertEqual(self.store.load()['revision'],1)
        self.assertEqual([p['id'] for p in preview['payload']['context']],['P002','P004'])
        result=self.service.suggest(self.args);a=result['state']['suggestions'][0]
        self.assertEqual(a['requestSnapshot'],preview['payload'])
        r={'id':1,'paragraphId':'P001','versionId':1,'annotations':a['output']['annotations'],'status':'confirmed','note':''}
        result=self.service.decide({'revision':result['revision'],'suggestionId':a['id'],'action':'accept','review':r})
        self.assertEqual(result['state']['reviews'][0]['annotations'][0]['stanceParagraphId'],'P004')
        restored=self.store.restore(result['revision'],result['state'])
        self.assertEqual(restored['state']['reviews'][0]['annotations'][0]['stanceParagraphId'],'P004')
    def test_invalid_selection_rejected_before_call(self):
        for ids in (['P005'],['P001'],['P404'],['P004']*2,['P002']*5,'P004'):
            with self.assertRaises(Problem):self.service.preview({**self.args,'contextIds':ids})
        self.assertEqual(self.model.calls,0)
    def test_oversized_input_rejected_before_call(self):
        r=self.store.load();s=r['state'];s['paragraphs'][3]['text']='大'*41000
        r=self.store.restore(r['revision'],s)
        with self.assertRaises(Problem):self.service.suggest({**self.args,'revision':r['revision']})
        self.assertEqual(self.model.calls,0)
    def test_model_cannot_cite_unseen_paragraph(self):
        p=self.store.load()['state']['paragraphs'][0]
        value=self.model.generate('annotation',{})
        with self.assertRaises(Problem):validate_output('annotation',value,p,[{'id':'cost'}],[])
    def test_manual_cross_document_reference_rejected(self):
        r=self.store.load();s=r['state'];p=s['paragraphs'][0]
        a={'labelId':'cost','quote':'票价过高','start':5,'end':9,'holder':'被引研究','stance':'opposes','stanceQuote':'别的材料','stanceParagraphId':'P005'}
        # Correct the topic span independently of the stance link.
        a['start']=p['text'].index(a['quote']);a['end']=a['start']+len(a['quote'])
        s['reviews'].append({'id':1,'paragraphId':'P001','versionId':1,'annotations':[a],'status':'confirmed','note':''})
        with self.assertRaises(Problem):self.store.save(r['revision'],s)
