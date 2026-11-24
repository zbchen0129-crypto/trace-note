import copy
import unittest
from backend.core import Problem
import test_questions

# Reuse fixture setup only, without inheriting unrelated test methods.
class SourceTests(unittest.TestCase):
    setUp = test_questions.QuestionTests.setUp
    tearDown = test_questions.QuestionTests.tearDown
    source = {'type':'paper','author':'合成案例作者','year':'2026','url':'https://example.org/paper','locator':'第 3 节，印刷页 42–44'}
    def attach(self, source):
        r=self.store.load();s=r['state'];s['documents'][0]['source']=copy.deepcopy(source)
        return self.store.restore(r['revision'],s)
    def test_source_persists_in_restore_preview_and_snapshot(self):
        r=self.attach(self.source)
        args={'revision':r['revision'],'kind':'annotation','paragraphId':'P001','requestId':'source-test-one'}
        self.assertEqual(self.service.preview(args)['payload']['sourceMetadata'],self.source)
        r=self.service.suggest(args)
        self.assertEqual(r['state']['suggestions'][-1]['requestSnapshot']['sourceMetadata'],self.source)
        r=self.store.restore(r['revision'],r['state'])
        self.assertEqual(r['state']['documents'][0]['source'],self.source)
    def test_invalid_sources_rejected(self):
        for changes in ({'type':'pdf'},{'author':'a'*301},{'locator':5},{'url':'javascript:alert(1)'},{'url':'https://user:password@example.org'},{'url':'https://example.org/\nx'}):
            with self.subTest(changes=changes):
                with self.assertRaises(Problem):self.attach({**self.source,**changes})
    def test_existing_source_cannot_be_silently_overwritten(self):
        r=self.attach(self.source);s=r['state'];s['documents'][0]['source']['locator']='另一页'
        with self.assertRaises(Problem):self.store.save(r['revision'],s)

    def correct(self, source=None, reason='核对原件后更正'):
        return self.service.correct_source({'revision':self.store.load()['revision'],'documentId':'doc-demo','source':source or self.source,'reason':reason})

    def test_correction_append_history_restore_and_conflict(self):
        original=self.store.load()['state']['documents'][0]
        r=self.correct()
        self.assertEqual(r['state']['documents'][0],original)
        self.assertEqual(r['state']['sourceRevisions'][0]['source'],self.source)
        with self.assertRaises(Problem):self.correct(reason='')
        with self.assertRaises(Problem):self.correct()
        with self.assertRaises(Problem):self.service.correct_source({'revision':1,'documentId':'doc-demo','source':{**self.source,'year':'2025'},'reason':'旧页面'})
        r=self.correct({**self.source,'year':'2025'})
        restored=self.store.restore(r['revision'],r['state'])
        self.assertEqual(len(restored['state']['sourceRevisions']),2)
        s=copy.deepcopy(restored['state']);s['sourceRevisions'][0]['reason']='覆盖历史'
        with self.assertRaises(Problem):self.store.save(restored['revision'],s)
        s=copy.deepcopy(restored['state']);s['sourceRevisions'].append({**s['sourceRevisions'][0],'id':3})
        with self.assertRaises(Problem):self.store.save(restored['revision'],s)

    def test_old_suggestion_cannot_be_accepted_after_correction(self):
        r=self.service.suggest({'revision':1,'kind':'annotation','paragraphId':'P001','requestId':'before-source'})
        sug=r['state']['suggestions'][-1]
        r=self.correct()
        with self.assertRaisesRegex(Problem,'来源信息已更正'):
            self.service.decide({'revision':r['revision'],'suggestionId':sug['id'],'action':'accept','review':test_questions.QuestionTests.review(self,1,1)})
        r=self.service.decide({'revision':r['revision'],'suggestionId':sug['id'],'action':'reject','note':'来源已更正'})
        self.assertEqual(r['state']['decisions'][-1]['status'],'rejected')
        p=self.service.preview({'revision':r['revision'],'kind':'annotation','paragraphId':'P001'})['payload']
        self.assertEqual(p['sourceMetadata'],self.source)
        self.assertEqual(p['sourceRevision'],1)

    def test_source_change_during_generation_discards_output(self):
        original=self.service.model.generate
        def during(kind,payload):
            self.correct()
            return original(kind,payload)
        self.service.model.generate=during
        with self.assertRaises(Problem):
            self.service.suggest({'revision':1,'kind':'annotation','paragraphId':'P001','requestId':'inflight-source'})
        self.assertEqual(self.store.load()['state']['suggestions'],[])

    def test_reviews_require_current_source_revision_and_preserve_history(self):
        r=self.store.load();s=r['state'];s['reviews'].append(test_questions.QuestionTests.review(self,1,1))
        r=self.store.save(r['revision'],s)
        r=self.correct();s=copy.deepcopy(r['state'])
        review=test_questions.QuestionTests.review(self,1,2)
        s['reviews'].append(review)
        with self.assertRaisesRegex(Problem,'来源已更正'):self.store.save(r['revision'],s)
        review['sourceRevision']=1
        r=self.store.save(r['revision'],s)
        self.assertNotIn('sourceRevision',r['state']['reviews'][0])
        self.assertEqual(r['state']['reviews'][1]['sourceRevision'],1)
        s=copy.deepcopy(r['state']);s['reviews'][-1]['sourceRevision']=999
        with self.assertRaisesRegex(Problem,'审核来源版本'):self.store.restore(r['revision'],s)

    def test_accepted_model_review_stamped_by_server(self):
        r=self.correct()
        r=self.service.suggest({'revision':r['revision'],'kind':'annotation','paragraphId':'P001','requestId':'current-source'})
        r=self.service.decide({'revision':r['revision'],'suggestionId':r['state']['suggestions'][-1]['id'],'action':'accept','review':test_questions.QuestionTests.review(self,1,1)})
        self.assertEqual(r['state']['reviews'][-1]['sourceRevision'],1)
