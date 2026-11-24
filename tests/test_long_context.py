import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from eval.long_context import payload_for, read_json, guard_memory, MAX_FILE_BYTES, summarize

class ContextBudgetTests(unittest.TestCase):
    def setUp(self):
        self.case = {'paragraphs':[{'id':str(i),'text':str(i)} for i in range(7)],'targetIndex':3}
    def test_adjacent_does_not_leak_remote_context_or_references(self):
        self.case['references'] = {'answer':'secret'}
        p = payload_for(self.case, 'adjacent', {})
        self.assertEqual([x['id'] for x in p['context']], ['2','4'])
        self.assertNotIn('references', p)
        self.assertEqual(len(payload_for(self.case, 'bounded_full', {})['context']),6)
    def test_context_budget_rejects_instead_of_truncating(self):
        self.case['paragraphs'][0]['text']='x'*32001
        with self.assertRaises(ValueError): payload_for(self.case,'bounded_full',{})
        payload_for(self.case,'adjacent',{})
    def test_oversized_file_stops_before_json_parse(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'large.json';p.write_bytes(b' '* (MAX_FILE_BYTES+1))
            with self.assertRaises(ValueError):read_json(p)
    def test_peak_memory_guard(self):
        with patch('eval.long_context.memory_mb',return_value=257):
            with self.assertRaises(ValueError):guard_memory()
    def test_uncertain_reference_requires_review_signal(self):
        c={'references':{'adjacent':{'labels':[],'review':True}}}
        v={'annotations':[],'reviewReasons':[],'abstainReason':''}
        self.assertFalse(summarize(c,'adjacent',v,'accepted')['referenceMatched'])
        v['abstainReason']='时间不明'
        self.assertTrue(summarize(c,'adjacent',v,'accepted')['referenceMatched'])
