"""Validated snapshots and append-only SQLite history; no model credentials persisted."""
import copy
from contextlib import contextmanager
import json
import sqlite3
from urllib.parse import urlsplit
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


STANCE_FIELDS = {'holder', 'stance', 'stanceQuote'}
STANCES = ('supports', 'opposes', 'mentions', 'unclear')


def validate_stance(annotation, text):
    if not STANCE_FIELDS.intersection(annotation):
        return  # Legacy records stay unclassified, never implicitly supporting.
    require(STANCE_FIELDS.issubset(annotation), '观点归属、态度和依据须一起填写。')
    require(isinstance(annotation['holder'], str) and 1 <= len(annotation['holder'].strip()) <= 200, '请填写观点归属（最多 200 字）。')
    require(annotation['stance'] in STANCES, '观点态度无效。')
    q = annotation['stanceQuote']
    require(isinstance(q, str) and len(q) <= 2000, '态度依据最长 2000 字。')
    require((annotation['stance'] == 'unclear' and not q) or (bool(q.strip()) and text.count(q) == 1), '态度依据须为所选段落中可唯一定位的原文；缺少依据请选择待核。')


def validate_annotations(items, text, labels, paragraph=None, paragraphs=None):
    require(isinstance(items, list) and len(items) <= 8, '标注格式错误。')
    seen = set()
    for a in items:
        require(isinstance(a, dict), '标注必须为对象。')
        require(a.get('labelId') in labels and a['labelId'] not in seen, '标签未知或重复。')
        seen.add(a['labelId'])
        stance_text = text
        if 'stanceParagraphId' in a:
            require(STANCE_FIELDS.issubset(a), '跨段依据缺少态度字段。')
            source = (paragraphs or {}).get(a['stanceParagraphId']) if isinstance(a['stanceParagraphId'],str) else None
            require(source is not None and paragraph is not None and source['documentId'] == paragraph['documentId'], '态度依据必须关联同一材料的有效段落。')
            stance_text = source['text']
        validate_stance(a, stance_text)
        quote = a.get('quote')
        start, end = a.get('start'), a.get('end')
        require(isinstance(quote, str) and bool(quote.strip()), '证据不能为空。')
        require(type(start) is int and type(end) is int and 0 <= start < end <= utf16len(text), '证据位置错误。')
        try:
            actual = text.encode('utf-16-le')[start*2:end*2].decode('utf-16-le')
        except UnicodeError:
            raise Problem('证据位置切断了 Unicode 字符。')
        require(actual == quote, '证据不匹配原文。')


def validate_scope(scope):
    require(isinstance(scope, dict) and set(scope) == {'subject', 'timeframe'}, '研究范围须包含研究对象和时间范围。')
    require(all(isinstance(scope[k], str) and 1 <= len(scope[k].strip()) <= 200 for k in scope), '研究对象和时间范围须为 1–200 字。')
    return scope


DEFAULT_QUESTION = {'id': 'Q1', 'text': '当前为何放弃公共交通？'}


def questions(s):
    return s.get('questions', [DEFAULT_QUESTION])


def question_id(version):
    return version.get('questionId', 'Q1')


def current_version(s, qid):
    matches = [v for v in s['versions'] if question_id(v) == qid]
    require(bool(matches), '研究问题不存在或缺少规则。')
    return matches[-1]


def record_question(s, record):
    return question_id(next(v for v in s['versions'] if v['id'] == record['versionId']))


def validate_source(source):
    require(isinstance(source, dict) and set(source) == {'type','author','year','url','locator'}, '材料来源格式错误。')
    require(source['type'] in ('interview','paper','book','other'), '材料类型无效。')
    for key, limit in {'author':300,'year':20,'url':2000,'locator':300}.items():
        require(isinstance(source[key], str) and len(source[key]) <= limit, '来源字段格式或长度错误。')
    if source['url']:
        try:
            url = urlsplit(source['url'])
            valid = url.scheme in ('http','https') and bool(url.hostname) and not url.username and not url.password
        except ValueError:
            valid = False
        require(valid and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in source['url']), '来源链接须为无账号密码的 HTTP 或 HTTPS 地址。')


def source_revision(s, document_id):
    rows = [r for r in s.get('sourceRevisions', []) if r['documentId'] == document_id]
    return rows[-1]['id'] if rows else 0


def current_source(s, document_id):
    rows = [r for r in s.get('sourceRevisions', []) if r['documentId'] == document_id]
    if rows:
        return rows[-1]['source']
    return next(d for d in s['documents'] if d['id'] == document_id).get('source')


def validate_state(s):
    require(isinstance(s, dict) and s.get('schemaVersion') == 1, '不支持的项目格式。')
    for key in ('documents', 'paragraphs', 'versions', 'reviews'):
        require(isinstance(s.get(key), list), f'缺少 {key}。')
    require(isinstance(s.get('title'), str), '缺少项目名称。')
    qs = questions(s)
    require(isinstance(qs, list) and 1 <= len(qs) <= 20, '每个项目支持 1–20 个研究问题。')
    qids = set()
    for q in qs:
        require(isinstance(q, dict) and isinstance(q.get('id'), str) and 1 <= len(q['id']) <= 80 and q['id'] not in qids and isinstance(q.get('text'), str) and 1 <= len(q['text'].strip()) <= 500, '研究问题格式错误。')
        qids.add(q['id'])
    require(qs[0] == DEFAULT_QUESTION, '初始研究问题不可覆盖。')
    require(s.get('activeQuestionId', 'Q1') in qids, '当前研究问题不存在。')
    docs, paragraphs, versions = {}, {}, {}
    for d in s['documents']:
        require(isinstance(d, dict) and isinstance(d.get('id'), str) and d['id'] not in docs and isinstance(d.get('name'), str), '文档格式错误。')
        if 'source' in d:
            validate_source(d['source'])
        docs[d['id']] = d
    corrections = s.get('sourceRevisions', [])
    require(isinstance(corrections, list) and len(corrections) <= 1000, '来源更正记录格式错误或超过 1000 条。')
    for i, r in enumerate(corrections, 1):
        require(isinstance(r, dict) and r.get('id') == i and isinstance(r.get('documentId'), str) and r['documentId'] in docs, '来源更正关联错误。')
        require(isinstance(r.get('reason'), str) and 1 <= len(r['reason'].strip()) <= 1000 and isinstance(r.get('createdAt'),str), '请填写来源更正原因（最多 1000 字）。')
        validate_source(r.get('source'))
    for p in s['paragraphs']:
        require(isinstance(p, dict) and isinstance(p.get('id'), str) and p['id'] not in paragraphs and p.get('documentId') in docs and isinstance(p.get('text'), str) and bool(p['text'].strip()), '段落格式错误。')
        require(p['id'].startswith('P') and p['id'][1:].isdigit() and len(p['text']) <= 200000, '段落编号或长度错误。')
        paragraphs[p['id']] = p
    require(type(s.get('nextParagraph')) is int and s['nextParagraph'] > max([int(x[1:]) for x in paragraphs] or [0]), '段落编号会发生冲突。')
    require(bool(s['versions']), '至少需要一个规则版本。')
    label_history, active_labels = {}, {}
    for i, v in enumerate(s['versions'], 1):
        require(isinstance(v, dict) and v.get('id') == i and isinstance(v.get('reason'), str) and bool(v['reason'].strip()), '规则版本错误。')
        require(isinstance(v.get('labels'), list) and 1 <= len(v['labels']) <= 8, '标签数量应为 1–8。')
        require(isinstance(question_id(v), str) and question_id(v) in qids, '规则关联了未知研究问题。')
        ids, names = set(), set()
        for label in v['labels']:
            require(isinstance(label, dict) and all(isinstance(label.get(k), str) for k in ('id','name','definition','include','exclude')), '标签格式错误。')
            require(label['id'] and label['id'] not in ids and label['name'].strip() and label['name'].strip() not in names and label['definition'].strip(), '标签重复或定义为空。')
            ids.add(label['id']); names.add(label['name'].strip())
        qid = question_id(v)
        require(not (ids & (label_history.get(qid, set()) - active_labels.get(qid, set()))), '已移除的标签身份不能重新使用，请创建新标签。')
        label_history.setdefault(qid, set()).update(ids)
        active_labels[qid] = ids
        if 'scope' in v:
            validate_scope(v['scope'])
        versions[i] = ids
    require(all(any(question_id(v) == qid for v in s['versions']) for qid in qids), '每个研究问题必须有规则版本。')
    for i, r in enumerate(s['reviews'], 1):
        require(isinstance(r, dict) and r.get('id') == i and r.get('paragraphId') in paragraphs and r.get('versionId') in versions, '审核记录关联错误。')
        sr = r.get('sourceRevision', 0)
        require(type(sr) is int and (sr == 0 or any(x['id'] == sr and x['documentId'] == paragraphs[r['paragraphId']]['documentId'] for x in s.get('sourceRevisions', []))), '审核来源版本关联错误。')
        require(r.get('status') in ('confirmed','ambiguous') and isinstance(r.get('note'), str), '审核状态错误。')
        require(r['status'] != 'ambiguous' or bool(r['note'].strip()), '请记录歧义原因。')
        validate_annotations(r.get('annotations'), paragraphs[r['paragraphId']]['text'], versions[r['versionId']], paragraphs[r['paragraphId']], paragraphs)
    return s


def normalize(s):
    s = copy.deepcopy(s)
    s.setdefault('suggestions', [])
    s.setdefault('decisions', [])
    s.setdefault('sourceRevisions', [])
    return s


def validate_transition(old, new):
    validate_state(new)
    require(questions(new)[:len(questions(old))] == questions(old), '已有研究问题不可覆盖。')
    for key in ('documents','paragraphs','versions','reviews','suggestions','decisions'):
        require(new.get(key, [])[:len(old[key])] == old[key], f'已有 {key} 不可覆盖；请通过备份恢复操作。')
    require(new.get('sourceRevisions', []) == old.get('sourceRevisions', []), '来源更正只能通过专用接口追加。')
    require(new['suggestions'] == old['suggestions'] and new['decisions'] == old['decisions'], '模型建议与决定只能通过审核接口更新。')
    for review in new['reviews'][len(old['reviews']):]:
        doc_id = next(p['documentId'] for p in new['paragraphs'] if p['id'] == review['paragraphId'])
        require(review.get('sourceRevision', 0) == source_revision(new, doc_id), '来源已更正，请重新核对后确认。')
        require(review['versionId'] == current_version(new, record_question(new, review))['id'], '不能向旧规则版本添加审核。')


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
