import copy
import json
import tempfile
import unittest
from pathlib import Path
from backend.core import Store, Problem, current_version, DEFAULT_QUESTION
from backend.service import Service


class Model:
    configured = True
    model = 'TEST-ONLY-QUESTIONS'
    def generate(self, kind, payload):
        if kind == 'rule':
            return {'labelId': payload['codebookVersion']['labels'][0]['id'], 'field': 'include', 'replacement': '测试新边界', 'rationale': '测试隔离'}
        return {'annotations': [], 'reviewReasons': [], 'abstainReason': ''}


class QuestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'test.db')
        s = json.loads((Path(__file__).resolve().parents[1]/'backend/seed.json').read_text())
        s['reviews'] = []
        self.record = self.store.save(0, s)
        self.service = Service(self.store, Model())
    def tearDown(self):
        self.tmp.cleanup()
    def second(self):
        s = copy.deepcopy(self.store.load()['state'])
        s['questions'] = [DEFAULT_QUESTION, {'id': 'Q2', 'text': '怎样改善出行体验？'}]
        s['versions'].append({**copy.deepcopy(s['versions'][0]), 'id': 2, 'questionId': 'Q2'})
        return s
    def review(self, version, number, note=''):
        return {'id': number, 'paragraphId': 'P001', 'versionId': version, 'annotations': [], 'status': 'confirmed', 'note': note}
    def test_legacy_and_two_questions_restore(self):
        s = self.second()
        s['reviews'] = [self.review(1, 1), self.review(2, 2)]
        r = self.store.save(1, s)
        self.assertEqual(current_version(r['state'], 'Q1')['id'], 1)
        r = self.store.restore(r['revision'], r['state'])
        self.assertEqual(len(r['state']['questions']), 2)
        self.assertEqual(len(r['state']['reviews']), 2)
    def test_current_version_is_per_question_and_old_versions_rejected(self):
        r = self.store.save(1, self.second())
        s = r['state']; s['reviews'].append(self.review(1, 1))
        r = self.store.save(r['revision'], s)  # Q1 remains valid despite global v2.
        s = r['state']; s['versions'].append({**copy.deepcopy(s['versions'][0]), 'id': 3})
        r = self.store.save(r['revision'], s)
        s = r['state']; s['reviews'].append(self.review(1, 2))
        with self.assertRaises(Problem): self.store.save(r['revision'], s)
    def test_question_identity_and_membership_are_immutable(self):
        r = self.store.save(1, self.second())
        for key in ('text', 'id'):
            s = copy.deepcopy(r['state']); s['questions'][1][key] = 'changed'
            with self.assertRaises(Problem): self.store.save(r['revision'], s)
        s = copy.deepcopy(r['state']); s['versions'][0]['questionId'] = 'Q2'
        with self.assertRaises(Problem): self.store.save(r['revision'], s)
    def test_requests_and_corrections_are_scoped(self):
        s = self.second(); s['reviews'] = [self.review(1, 1, 'Q1 private correction')]
        r = self.store.save(1, s)
        args = {'revision': r['revision'], 'questionId': 'Q2', 'kind': 'annotation', 'paragraphId': 'P001', 'requestId': 'question-two'}
        p = self.service.preview(args)['payload']
        self.assertEqual(p['researchQuestion'], '怎样改善出行体验？')
        self.assertEqual(p['codebookVersion']['id'], 2)
        with self.assertRaises(Problem): self.service.preview({**args, 'kind': 'rule'})
        with self.assertRaises(Problem): self.service.preview({**args, 'questionId': 'missing'})
        r = self.service.suggest(args)
        sug = r['state']['suggestions'][-1]
        with self.assertRaises(Problem):
            self.service.decide({'revision':r['revision'],'suggestionId':sug['id'],'action':'accept','review':self.review(1, 2)})
    def test_accept_q1_suggestion_after_q2_added(self):
        r = self.service.suggest({'revision':1,'kind':'annotation','paragraphId':'P001','requestId':'question-one'})
        sug = r['state']['suggestions'][-1]
        r = self.store.save(r['revision'], self.second())
        r = self.service.decide({'revision':r['revision'],'suggestionId':sug['id'],'action':'accept','review':self.review(1, 1)})
        self.assertEqual(r['state']['reviews'][0]['versionId'], 1)

    def test_rule_acceptance_only_updates_own_question(self):
        s = self.second(); s['reviews'] = [self.review(1, 1, '修改原问题的边界')]
        r = self.store.save(1, s)
        r = self.service.suggest({'revision':r['revision'],'kind':'rule','paragraphId':'P001','questionId':'Q1','requestId':'rule-q-one'})
        sug = r['state']['suggestions'][-1]
        labels = copy.deepcopy(current_version(r['state'], 'Q1')['labels'])
        labels[0]['include'] = '测试新边界'
        r = self.service.decide({'revision':r['revision'],'suggestionId':sug['id'],'action':'accept','labels':labels,'reason':'确认规则'})
        self.assertEqual(current_version(r['state'], 'Q1')['id'], 3)
        self.assertEqual(current_version(r['state'], 'Q2')['id'], 2)
        self.assertEqual(r['state']['decisions'][-1]['versionId'], 3)

    def test_removed_label_history_preserved_and_identity_not_reused(self):
        s = self.store.load()['state']
        p = s['paragraphs'][0]; quote = '公交晚到二十分钟'; start = p['text'].index(quote)
        review = self.review(1, 1)
        review['annotations'] = [{'labelId':'reliability','quote':quote,'start':start,'end':start+len(quote)}]
        s['reviews'].append(review)
        r = self.store.save(1, s)
        s = r['state']; old = copy.deepcopy(s['versions'][0])
        s['versions'].append({**copy.deepcopy(old),'id':2,'labels':old['labels'][1:]})
        r = self.store.save(r['revision'], s)
        self.assertEqual(r['state']['reviews'][0]['annotations'][0]['labelId'],'reliability')
        s = r['state']; s['versions'].append({**old,'id':3})
        with self.assertRaises(Problem): self.store.save(r['revision'], s)
        restored = self.store.restore(r['revision'], self.store.load()['state'])
        self.assertEqual(restored['state']['versions'][0]['labels'][0]['id'],'reliability')

    def test_empty_duplicate_and_overfull_label_sets_rejected(self):
        for mode in ('empty','duplicate','overfull'):
            s = self.store.load()['state']; v=copy.deepcopy(s['versions'][0]);v['id']=2
            label=v['labels'][0]
            if mode=='empty':v['labels']=[]
            elif mode=='duplicate':v['labels']=[label,{**label,'id':'another','name':' '+label['name']+' '}]
            else:v['labels']=[{**label,'id':str(i),'name':str(i)} for i in range(9)]
            s['versions'].append(v)
            with self.assertRaises(Problem):self.store.save(1,s)
