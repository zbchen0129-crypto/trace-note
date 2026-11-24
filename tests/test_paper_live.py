import unittest
from eval.paper_live import payload_for,score,ROOT
from eval.long_context import read_json

class PaperLiveTests(unittest.TestCase):
    def setUp(self):self.f=read_json(ROOT/'eval/paper-attribution.json')
    def test_arms_differ_only_in_supplied_context_without_reference_leak(self):
        a=payload_for(self.f,'excerptOnly');b=payload_for(self.f,'withAuthorResults')
        self.assertEqual(a['context'],[]);self.assertEqual(b.pop('context')[0]['id'],'P008');a.pop('context')
        self.assertEqual(a,b)
        for key in ['reference','referenceStatus','holder']:self.assertNotIn(key,a)
    def test_incomplete_view_abstention_and_wrong_source(self):
        empty={'annotations':[],'reviewReasons':['缺少作者评价'],'abstainReason':''}
        self.assertTrue(score(self.f,'excerptOnly',empty)['stanceAndSourceMatched'])
        self.assertFalse(score(self.f,'withAuthorResults',empty)['stanceAndSourceMatched'])
        wrong={'annotations':[{'labelId':'engagement','stance':'opposes','stanceParagraphId':'P007'}]}
        self.assertFalse(score(self.f,'withAuthorResults',wrong)['stanceAndSourceMatched'])
