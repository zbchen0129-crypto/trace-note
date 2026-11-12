#!/usr/bin/env python3
"""Local-only HTTP app, SQLite persistence and server-side model requests."""
import argparse
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from backend.core import Store, Problem
from backend.model import OpenAIModel
from backend.service import Service

ROOT = Path(__file__).resolve().parent


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line: continue
            key, value = line.split('=',1)
            if key.strip() in ('OPENAI_API_KEY','TRACENOTE_MODEL'):
                os.environ.setdefault(key.strip(),value.strip().strip('\"\''))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,service,**kwargs):
        self.service = service
        super().__init__(*args,directory=str(ROOT/'web'),**kwargs)

    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()

    def allowed(self):
        host = self.headers.get('Host','')
        allowed = {f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}'}
        if host not in allowed: raise Problem('Host 不允许。',403)
        if self.headers.get('Origin') not in (None,'http://'+host): raise Problem('跨站请求不允许。',403)
        if self.headers.get('Sec-Fetch-Site') == 'cross-site': raise Problem('跨站请求不允许。',403)

    def reply(self,status,data):
        raw = json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        try:
            self.allowed()
            path = urlsplit(self.path).path
            if path == '/api/status':
                self.reply(200,{'storage':'sqlite','configured':self.service.model.configured,'model':self.service.model.model or None})
            elif path == '/api/workspace': self.reply(200,self.service.store.load())
            elif path == '/api/jobs':
                with self.service.store.connect() as db:
                    self.reply(200,{'jobs':[dict(r) for r in db.execute('SELECT id,status,error FROM jobs ORDER BY rowid DESC LIMIT 10')]})
            elif path.startswith('/api/'): self.reply(404,{'error':'接口不存在。'})
            else: super().do_GET()
        except Problem as error: self.reply(error.status,{'error':str(error)})

    def do_POST(self):
        try:
            self.allowed()
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json': raise Problem('需要 JSON 请求。',415)
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 5_000_000: raise Problem('请求为空或超过 5MB。',413)
            args = json.loads(self.rfile.read(length))
            if not isinstance(args,dict) or type(args.get('revision')) is not int: raise Problem('缺少项目修订号。')
            path = urlsplit(self.path).path
            if path == '/api/workspace': result = self.service.store.save(args['revision'],args['state'])
            elif path == '/api/restore': result = self.service.store.restore(args['revision'],args['state'])
            elif path == '/api/suggest': result = self.service.suggest(args)
            elif path == '/api/decide': result = self.service.decide(args)
            else: raise Problem('接口不存在。',404)
            self.reply(200,result)
        except Problem as error: self.reply(error.status,{'error':str(error)})
        except (ValueError,KeyError,TypeError,AttributeError,UnicodeError): self.reply(400,{'error':'请求或项目格式错误，未保存。'})
        except Exception: self.reply(500,{'error':'本地服务处理失败，未报告保存成功。'})

    def log_message(self,format,*args):
        pass  # Do not log research text, credentials, or request bodies.


def make_server(port=8767, db=None, model=None):
    service = Service(Store(db or ROOT/'data'/'tracenote.sqlite3'),model or OpenAIModel())
    return ThreadingHTTPServer(('127.0.0.1',port),partial(Handler,service=service))


if __name__ == '__main__':
    load_env()
    parser = argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8767); args = parser.parse_args()
    server = make_server(args.port)
    print(f'TraceNote: http://localhost:{server.server_port} (SQLite; AI configuration checked in UI)',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
