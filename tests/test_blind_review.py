import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from eval.blind_review import packet,build,validate,compare

class BlindReviewTests(unittest.TestCase):
    def setUp(self):
        self.p=packet()
        self.r={'studyId':self.p['studyId'],'packetHash':self.p['packetHash'],'reviewerId':'TEST-A','englishFamiliarity':'test fixture','priorExposure':'TEST ONLY','answers':[{'caseId':c['id'],'completed':True,'stance':'unclear','claimHolder':'不明确','evaluator':'不明确','evidence':[],'note':'测试验证器，不是真实评审'} for c in self.p['cases']]}
    def test_archive_allowlist_and_blank_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'packet.zip';build(path)
            with zipfile.ZipFile(path) as z:
                self.assertEqual(set(z.namelist()),{'INSTRUCTIONS.md','materials.json','response-template.json'})
                material=json.loads(z.read('materials.json'));blank=json.loads(z.read('response-template.json'))
                self.assertNotIn('reference',material);self.assertNotIn('interpretation',str(material))
                self.assertTrue(all(a['stance'] is None and a['completed'] is False for a in blank['answers']))
                with self.assertRaises(ValueError):validate(blank,material)
    def test_wrong_version_duplicate_cases_and_cross_source_quote_rejected(self):
        validate(self.r,self.p)
        for change in ('hash','duplicate','quote'):
            r=copy.deepcopy(self.r)
            if change=='hash':r['packetHash']='wrong'
            elif change=='duplicate':r['answers'][1]['caseId']='R01'
            else:r['answers'][0]['evidence']=[{'paragraphId':'P007','quote':'Twitter citations'}]
            with self.assertRaises(ValueError):validate(r,self.p)
    def test_comparison_preserves_disagreement_without_gold_scoring(self):
        other=copy.deepcopy(self.r);other['reviewerId']='TEST-B';other['answers'][0]['stance']='out_of_scope'
        result=compare(self.r,other,self.p)
        self.assertEqual(result['stanceAgreements'],2)
        self.assertFalse(result['rows'][0]['sameStance'])
        self.assertEqual(self.r['answers'][0]['stance'],'unclear')
        with self.assertRaises(ValueError):compare(self.r,self.r,self.p)
