"""Validated snapshots and append-only SQLite history; no model credentials persisted."""
import copy
from contextlib import contextmanager
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def require(condition, message):
    if not condition:
        raise Problem(message)


def utf16len(text):
    return len(text.encode('utf-16-le')) // 2


def validate_annotations(items, text, labels):
    require(isinstance(items, list) and len(items) <= 8, '标注格式错误。')
    seen = set()
    for a in items:
        require(isinstance(a, dict), '标注必须为对象。')
        require(a.get('labelId') in labels and a['labelId'] not in seen, '标签未知或重复。')
        seen.add(a['labelId'])
        quote = a.get('quote')
        start, end = a.get('start'), a.get('end')
        require(isinstance(quote, str) and bool(quote.strip()), '证据不能为空。')
        require(type(start) is int and type(end) is int and 0 <= start < end <= utf16len(text), '证据位置错误。')
        try:
            actual = text.encode('utf-16-le')[start*2:end*2].decode('utf-16-le')
        except UnicodeError:
            raise Problem('证据位置切断了 Unicode 字符。')
        require(actual == quote, '证据不匹配原文。')


def validate_state(s):
    require(isinstance(s, dict) and s.get('schemaVersion') == 1, '不支持的项目格式。')
    for key in ('documents', 'paragraphs', 'versions', 'reviews'):
        require(isinstance(s.get(key), list), f'缺少 {key}。')
    require(isinstance(s.get('title'), str), '缺少项目名称。')
    docs, paragraphs, versions = {}, {}, {}
    for d in s['documents']:
        require(isinstance(d, dict) and isinstance(d.get('id'), str) and d['id'] not in docs and isinstance(d.get('name'), str), '文档格式错误。')
        docs[d['id']] = d
    for p in s['paragraphs']:
        require(isinstance(p, dict) and isinstance(p.get('id'), str) and p['id'] not in paragraphs and p.get('documentId') in docs and isinstance(p.get('text'), str) and bool(p['text'].strip()), '段落格式错误。')
        require(p['id'].startswith('P') and p['id'][1:].isdigit() and len(p['text']) <= 200000, '段落编号或长度错误。')
        paragraphs[p['id']] = p
    require(type(s.get('nextParagraph')) is int and s['nextParagraph'] > max([int(x[1:]) for x in paragraphs] or [0]), '段落编号会发生冲突。')
    require(bool(s['versions']), '至少需要一个规则版本。')
    for i, v in enumerate(s['versions'], 1):
        require(isinstance(v, dict) and v.get('id') == i and isinstance(v.get('reason'), str) and bool(v['reason'].strip()), '规则版本错误。')
        require(isinstance(v.get('labels'), list) and 1 <= len(v['labels']) <= 8, '标签数量应为 1–8。')
        ids, names = set(), set()
        for label in v['labels']:
            require(isinstance(label, dict) and all(isinstance(label.get(k), str) for k in ('id','name','definition','include','exclude')), '标签格式错误。')
            require(label['id'] and label['id'] not in ids and label['name'].strip() and label['name'] not in names and label['definition'].strip(), '标签重复或定义为空。')
            ids.add(label['id']); names.add(label['name'])
        versions[i] = ids
    for i, r in enumerate(s['reviews'], 1):
        require(isinstance(r, dict) and r.get('id') == i and r.get('paragraphId') in paragraphs and r.get('versionId') in versions, '审核记录关联错误。')
        require(r.get('status') in ('confirmed','ambiguous') and isinstance(r.get('note'), str), '审核状态错误。')
        require(r['status'] != 'ambiguous' or bool(r['note'].strip()), '请记录歧义原因。')
        validate_annotations(r.get('annotations'), paragraphs[r['paragraphId']]['text'], versions[r['versionId']])
    return s


def normalize(s):
    s = copy.deepcopy(s)
    s.setdefault('suggestions', [])
    s.setdefault('decisions', [])
    return s


def validate_transition(old, new):
    validate_state(new)
    for key in ('documents','paragraphs','versions','reviews','suggestions','decisions'):
        require(new.get(key, [])[:len(old[key])] == old[key], f'已有 {key} 不可覆盖；请通过备份恢复操作。')
    require(new['suggestions'] == old['suggestions'] and new['decisions'] == old['decisions'], '模型建议与决定只能通过审核接口更新。')
    for review in new['reviews'][len(old['reviews']):]:
        require(review['versionId'] == new['versions'][-1]['id'], '不能向旧规则版本添加审核。')


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS snapshots(revision INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, reason TEXT NOT NULL, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, status TEXT NOT NULL, error TEXT, suggestion_id TEXT);''')
            db.execute("UPDATE jobs SET status='failed',error='服务重启中断了请求；请主动重新生成。' WHERE status='running'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def load(self, db=None):
        if db is None:
            with self.connect() as connection:
                return self.load(connection)
        row = db.execute('SELECT revision,state FROM snapshots ORDER BY revision DESC LIMIT 1').fetchone()
        return {'revision': row['revision'], 'state': json.loads(row['state'])} if row else {'revision': 0, 'state': None}

    def update(self, revision, mutate, reason):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self.load(db)
            if revision is not None and record['revision'] != revision:
                raise Problem('项目已在另一个页面更新，请刷新后重试。未覆盖任何记录。', 409)
            state = mutate(copy.deepcopy(record['state']))
            validate_state(state)
            db.execute('INSERT INTO snapshots(created,reason,state) VALUES(?,?,?)', (now(), reason, json.dumps(state,ensure_ascii=False)))
            return self.load(db)

    def save(self, revision, state):
        state = normalize(state)
        def mutate(old):
            if old:
                validate_transition(old,state)
            else:
                require(not state['suggestions'] and not state['decisions'], '初次迁移只接受人工项目数据。')
            return state
        return self.update(revision,mutate,'save')

    def restore(self, revision, state):
        # Restore manual research records, retaining an immutable DB snapshot of the prior project.
        state = normalize(state)
        state['suggestions'] = []
        state['decisions'] = []
        return self.update(revision,lambda old: state,'restore-manual-records')
