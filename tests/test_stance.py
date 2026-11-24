import unittest
from backend.core import Problem, validate_annotations
from backend.model import validate_output

class StanceTests(unittest.TestCase):
    def setUp(self):
        self.text='有研究称票价过高导致退出，但本文不支持票价是退出原因。'
        self.a={'labelId':'cost','quote':'票价过高','holder':'被引研究','stance':'opposes','stanceQuote':'但本文不支持票价是退出原因。'}
    def output(self, a):
        return {'annotations':[a],'reviewReasons':[],'abstainReason':''}
    def test_model_metadata_survives_source_validation(self):
        result=validate_output('annotation',self.output(self.a),{'text':self.text},[{'id':'cost'}])
        a=result['annotations'][0]
        self.assertEqual(a['stance'],'opposes'); self.assertEqual(a['holder'],'被引研究')
        validate_annotations([a],self.text,{'cost'})
    def test_fabricated_or_partial_stance_rejected(self):
        for changes in ({'stanceQuote':'假引文'},{'stance':'support'},{'holder':''},{'stanceQuote':''}):
            with self.assertRaises(Problem):validate_output('annotation',self.output({**self.a,**changes}),{'text':self.text},[{'id':'cost'}])
        a=dict(self.a);del a['holder']
        with self.assertRaises(Problem):validate_output('annotation',self.output(a),{'text':self.text},[{'id':'cost'}])
    def test_unclear_can_preserve_missing_context_without_inventing_quote(self):
        a={**self.a,'stance':'unclear','stanceQuote':''}
        result=validate_output('annotation',self.output(a),{'text':self.text},[{'id':'cost'}])
        self.assertEqual(result['annotations'][0]['stance'],'unclear')
    def test_legacy_is_not_silently_marked_supporting(self):
        a={'labelId':'cost','quote':'票价过高'}
        result=validate_output('annotation',self.output(a),{'text':self.text},[{'id':'cost'}])
        self.assertNotIn('stance',result['annotations'][0])
