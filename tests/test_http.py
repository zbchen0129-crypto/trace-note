import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from server import make_server
from test_backend import FakeModel, SEED


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=make_server(0,Path(self.tmp.name)/'db.sqlite3',FakeModel())
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.client=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()
    def call(self,path,payload=None,origin=None):
        headers={'Content-Type':'application/json'}
        if origin: headers['Origin']=origin
        req=urllib.request.Request(self.base+path,data=json.dumps(payload).encode() if payload else None,headers=headers)
        with self.client.open(req,timeout=3) as response: return json.load(response)
    def test_full_api_review_and_conflict(self):
        r=self.call('/api/workspace',{'revision':0,'state':SEED})
        r=self.call('/api/suggest',{'revision':r['revision'],'kind':'annotation','paragraphId':'P001','requestId':'http-test-request'})
        s=r['state']['suggestions'][0]
        self.assertEqual(r['state']['reviews'],[])
        review={'paragraphId':'P001','versionId':1,'annotations':s['output']['annotations'],'note':'人工核对','status':'confirmed'}
        r=self.call('/api/decide',{'revision':r['revision'],'suggestionId':s['id'],'action':'accept','review':review})
        self.assertEqual(r['state']['decisions'][0]['status'],'accepted')
        self.assertEqual(self.call('/api/workspace')['state']['reviews'][0]['annotations'][0]['quote'],'晚到二十分钟')
        with self.assertRaises(urllib.error.HTTPError) as e: self.call('/api/workspace',{'revision':1,'state':r['state']})
        self.assertEqual(e.exception.code,409); e.exception.close()
    def test_cross_origin_blocked_and_secrets_not_exposed(self):
        with self.assertRaises(urllib.error.HTTPError) as e: self.call('/api/workspace',{'revision':0,'state':SEED},'https://untrusted.example')
        self.assertEqual(e.exception.code,403); e.exception.close()
        self.assertNotIn('key',self.call('/api/status'))
        with self.assertRaises(urllib.error.HTTPError) as e: self.call('/.env')
        self.assertEqual(e.exception.code,404); e.exception.close()


if __name__=='__main__': unittest.main()
