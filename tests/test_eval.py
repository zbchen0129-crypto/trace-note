import unittest
from eval.run import scores

class ScoreTests(unittest.TestCase):
    def row(self,id,annotations=None):
        return {'caseId':id,'payload':{'paragraph':{'text':'票价太贵'}},'validation':'accepted','output':{'annotations':annotations or []}}
    def test_multilabel_counts_and_negative(self):
        cases=[{'id':'A','expectedLabels':['cost','comfort']},{'id':'B','expectedLabels':[]}]
        rows=[self.row('A',[{'labelId':'cost','quote':'票价太贵'},{'labelId':'transfer','quote':'捏造'}]),self.row('B')]
        result=scores(rows,cases,['cost','comfort','transfer'])
        self.assertEqual(result['microF1'],.5)
        self.assertEqual(result['exactMatch'],.5)
        self.assertEqual(result['negativeExact'],1)
        self.assertEqual(result['exactQuoteRate'],.5)
    def test_unknown_label_counts_as_false_positive(self):
        row=self.row('A',[{'labelId':'invented','quote':'票价太贵'}])
        result=scores([row],[{'id':'A','expectedLabels':['cost']}],['cost'])
        self.assertEqual(result['unknownLabelPredictions'],1)
        self.assertEqual(result['microPrecision'],0)
        self.assertEqual(result['microF1'],0)
    def test_request_failure_is_not_correct_empty(self):
        row={'caseId':'A','payload':{'paragraph':{'text':'x'}},'validation':'request_failed'}
        result=scores([row],[{'id':'A','expectedLabels':[]}],['cost'])
        self.assertEqual(result['exactMatch'],0)
        self.assertEqual(result['responseErrors'],1)
        self.assertIsNone(result['exactQuoteRate'])
    def test_rejection_does_not_erase_raw_labels(self):
        row=self.row('A',[{'labelId':'cost','quote':'不存在'}]); row['validation']='rejected'
        result=scores([row],[{'id':'A','expectedLabels':['cost']}],['cost'])
        self.assertEqual(result['microF1'],1)
        self.assertEqual(result['acceptedCoverage'],0)
        self.assertEqual(result['exactQuoteRate'],0)

if __name__=='__main__': unittest.main()
