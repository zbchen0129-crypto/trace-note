import json
import unittest
from unittest.mock import patch
from backend.model import OpenAIModel

class GenericPromptTests(unittest.TestCase):
    def test_actual_request_preserves_question_and_attribution_contract(self):
        model=OpenAIModel();model.key='offline-placeholder';model.model='offline-test'
        output={'annotations':[],'reviewReasons':[],'abstainReason':''}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):
                return json.dumps({'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(output)}]}]}).encode()
        payload={'researchQuestion':'作者如何评价学术交流？','researchScope':{'subject':'论文作者','timeframe':'所述样本'}}
        with patch('backend.model.urllib.request.urlopen',return_value=Response()) as call:
            self.assertEqual(model.generate('annotation',payload),output)
        request=json.loads(call.call_args.args[0].data)
        self.assertEqual(json.loads(request['input']),payload)
        self.assertIn('被引作者与本文作者',request['instructions'])
        self.assertIn('样本内结论',request['instructions'])
        self.assertNotIn('目标对象的原因',request['instructions'])
