export const STORAGE_KEY = 'tracenote.workspace.v1';
export const demoParagraphs = [
  '上个月有三次公交晚到二十分钟。我得接孩子，后来就改开车了。',
  '车票不贵，主要是每天要换两次车，第二趟经常接不上。',
  '高峰期挤得转不了身。我有时候宁愿多花点钱打车。',
  '一个月交通费大概一百二十，但这个钱对我没什么压力。',
  '晚上那趟车让我不太放心。',
  '以前经常晚点，不过改了时刻表以后好多了。现在不坐，主要是公司搬家了。'
];
const initialLabels = [
  { id: 'reliability', name: '可靠性问题', definition: '晚点、取消或到达时间不确定，使出行难以安排。', include: '明确描述服务时间不可靠。', exclude: '车程长但时间稳定；不能由接不上车自行推断晚点。' },
  { id: 'transfer', name: '换乘负担', definition: '换乘次数、步行或接续等待造成出行负担。', include: '明确描述换乘带来的困难。', exclude: '直达车的车程长。' },
  { id: 'cost', name: '费用负担', definition: '交通支出造成压力或因价格而放弃公共交通。', include: '明确表达负担不起、票价过高或费用压力。', exclude: '价格不贵、没有压力；为改善体验接受额外支出。' },
  { id: 'comfort', name: '舒适度问题', definition: '拥挤、座位、温度或噪声造成乘车不适。', include: '明确描述身体或感官不适。', exclude: '笼统的不放心、不想坐，含义未明时保留歧义。' }
];
export function createWorkspace() {
  return {
    schemaVersion: 1, title: '公共交通退出经历研究',
    documents: [{ id: 'doc-demo', name: '教学案例 · 六段虚构访谈摘录', fictional: true }],
    paragraphs: demoParagraphs.map((text, i) => ({ id: `P${String(i + 1).padStart(3, '0')}`, documentId: 'doc-demo', text })),
    versions: [{ id: 1, createdAt: new Date().toISOString(), reason: '初始标签体系', labels: initialLabels }],
    reviews: [], nextParagraph: 7
  };
}
export const defaultQuestion = {id:'Q1',text:'当前为何放弃公共交通？'};
export function questions(state) { return state.questions || [defaultQuestion]; }
export function activeQuestion(state) { return state.activeQuestionId || 'Q1'; }
export function questionVersions(state) { return state.versions.filter(v => (v.questionId || 'Q1') === activeQuestion(state)); }
export function currentVersion(state) { return questionVersions(state).at(-1); }
export function inQuestion(state, record) { return questionVersions(state).some(v => v.id === record.versionId); }
export function addQuestion(state, text, name, definition) {
  if (!text.trim() || text.trim().length > 500 || !name.trim() || !definition.trim()) throw new Error('请填写研究问题、初始标签与定义。');
  if (questions(state).length >= 20) throw new Error('每个项目最多 20 个问题。');
  const next = structuredClone(state);
  next.questions = structuredClone(questions(state));
  const id = `Q-${crypto.randomUUID()}`;
  next.questions.push({id,text:text.trim()}); next.activeQuestionId = id;
  next.versions.push({id:next.versions.length+1,questionId:id,createdAt:new Date().toISOString(),reason:'新研究问题的初始规则',labels:[{id:'topic',name:name.trim(),definition:definition.trim(),include:'与当前研究问题有关的支持、反对、引述或疑问，分别记录态度。',exclude:'与当前研究问题无关的内容。'}]});
  return next;
}
export function latestReview(state, paragraphId) { return state.reviews.filter(r => r.paragraphId === paragraphId && inQuestion(state, r)).at(-1); }
export function reviewStatus(state, paragraphId) {
  const review = latestReview(state, paragraphId);
  if (!review) return 'pending';
  const documentId = state.paragraphs.find(p => p.id === paragraphId).documentId;
  if ((review.sourceRevision || 0) !== sourceRevision(state, documentId)) return 'source-stale';
  if (review.versionId !== currentVersion(state).id) return 'stale';
  return review.status;
}
export const sourceTypes = {interview:'访谈',paper:'论文',book:'书籍',other:'其他'};
export function validateSource(source) {
  if (!source || typeof source !== 'object' || Object.keys(source).sort().join() !== 'author,locator,type,url,year' || !Object.hasOwn(sourceTypes,source.type)) throw new Error('材料来源格式错误。');
  for (const [key,limit] of Object.entries({author:300,year:20,url:2000,locator:300})) {
    if (typeof source[key] !== 'string' || source[key].length > limit) throw new Error('来源字段格式或长度错误。');
  }
  if (source.url) {
    let url; try { url=new URL(source.url); } catch { throw new Error('来源链接须为完整 HTTP 或 HTTPS 地址。'); }
    if (!['http:','https:'].includes(url.protocol) || !url.hostname || url.username || url.password || /[\s\u0000-\u001f\u007f]/.test(source.url)) throw new Error('来源链接须为无账号密码的 HTTP 或 HTTPS 地址。');
  }
  return source;
}
export function sourceRevision(state, documentId) { return (state.sourceRevisions || []).filter(r=>r.documentId===documentId).at(-1)?.id || 0; }
export function sourceDocument(state, documentId) {
 const doc=state.documents.find(d=>d.id===documentId);
 const correction=(state.sourceRevisions || []).filter(r=>r.documentId===documentId).at(-1);
 return correction ? {...doc,source:correction.source} : doc;
}
export function sourceCitation(document) {
  const source=document?.source;
  if (!source) return `${document?.name || '未知材料'} · 来源未记录`;
  return [document.name,sourceTypes[source.type],source.author,source.year,source.locator && `摘录范围：${source.locator}`,source.url].filter(Boolean).join(' · ');
}
export function addDocument(state, name, text, source) {
  if (source !== undefined) validateSource(source);
  if (!name.trim()) throw new Error('请填写材料名称。');
  if (text.length > 200000) throw new Error('第一版每份材料最多 20 万字符。');
  const chunks = text.replace(/\r\n?/g, '\n').split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);
  if (!chunks.length) throw new Error('请先输入材料正文。');
  const next = structuredClone(state);
  const id = `doc-${next.documents.length + 1}`;
  next.documents.push({ id, name: name.trim(), fictional: false, ...(source === undefined ? {} : {source:structuredClone(source)}) });
  for (const text of chunks) next.paragraphs.push({ id: `P${String(next.nextParagraph++).padStart(3, '0')}`, documentId: id, text });
  return next;
}
export const stanceNames = { supports:'支持该观点', opposes:'反对该观点', mentions:'仅提及／引述', unclear:'态度待核', unclassified:'旧记录未判定' };
export function validateStance(a, text) {
  const fields = ['holder','stance','stanceQuote'];
  if (!fields.some(k => k in a)) return;
  if (!fields.every(k => k in a) || typeof a.holder !== 'string' || !a.holder.trim() || a.holder.trim().length > 200 || !['supports','opposes','mentions','unclear'].includes(a.stance)) throw new Error('请完整填写观点归属和态度。');
  const q=a.stanceQuote;
  if (typeof q !== 'string' || q.length > 2000 || !((a.stance === 'unclear' && q === '') || (q.trim() && text.includes(q) && text.indexOf(q) === text.lastIndexOf(q)))) throw new Error('态度依据须为所选段落中可唯一定位的原文；缺少依据请选择待核。');
}
export function saveReview(state, paragraphId, annotations, note, status = 'confirmed') {
  const paragraph = state.paragraphs.find(p => p.id === paragraphId);
  if (!paragraph) throw new Error('找不到段落。');
  if (!['confirmed', 'ambiguous'].includes(status)) throw new Error('无效的复核状态。');
  if (status === 'ambiguous' && !note.trim()) throw new Error('请记录歧义原因或需要补充的上下文。');
  const version = currentVersion(state);
  const used = new Set();
  for (const annotation of annotations) {
    if (!version.labels.some(l => l.id === annotation.labelId) || used.has(annotation.labelId)) throw new Error('标签无效或重复。');
    used.add(annotation.labelId);
    const source = annotation.stanceParagraphId === undefined ? paragraph : state.paragraphs.find(p => p.id === annotation.stanceParagraphId && p.documentId === paragraph.documentId);
    if (!source) throw new Error('态度依据必须关联同一材料的有效段落。');
    validateStance(annotation, source.text);
    if (!annotation.quote?.trim()) throw new Error('每个标签都需要一段原文证据。');
    if (!Number.isInteger(annotation.start) || !Number.isInteger(annotation.end) || annotation.start < 0 || annotation.end <= annotation.start || paragraph.text.slice(annotation.start, annotation.end) !== annotation.quote) throw new Error('证据必须与当前段落原文完全一致。');
  }
  const next = structuredClone(state);
  next.reviews.push({ id: next.reviews.length + 1, paragraphId, versionId: version.id, sourceRevision: sourceRevision(state, paragraph.documentId), annotations: structuredClone(annotations), note: note.trim(), status, source: 'human', createdAt: new Date().toISOString() });
  return next;
}
export function publishVersion(state, labels, reason, scope = currentVersion(state).scope) {
  if (scope !== undefined && (!scope || Object.keys(scope).sort().join() !== "subject,timeframe" || ![scope.subject, scope.timeframe].every(v => typeof v === "string" && v.trim().length > 0 && v.trim().length <= 200))) throw new Error("研究对象和时间范围须为 1–200 字。");
  if (!reason.trim()) throw new Error('请填写规则修改原因。');
  if (labels.length < 1 || labels.length > 8) throw new Error('第一版支持 1–8 个标签。');
  const ids = new Set(); const names = new Set();
  const historyIds = new Set(questionVersions(state).flatMap(v=>v.labels.map(l=>l.id)));
  const activeIds = new Set(currentVersion(state).labels.map(l=>l.id));
  for (const label of labels) {
    if (!label.id || ids.has(label.id) || !label.name.trim() || names.has(label.name.trim()) || !label.definition.trim()) throw new Error('标签名称必须唯一，且定义不能为空。');
    if (historyIds.has(label.id) && !activeIds.has(label.id)) throw new Error('已移除的标签身份不能重新使用，请创建新标签。');
    ids.add(label.id); names.add(label.name.trim());
  }
  if (JSON.stringify(labels) === JSON.stringify(currentVersion(state).labels) && JSON.stringify(scope) === JSON.stringify(currentVersion(state).scope)) throw new Error('规则没有变化。');
  const next = structuredClone(state);
  next.versions.push({ id: next.versions.length + 1, questionId: activeQuestion(state), createdAt: new Date().toISOString(), reason: reason.trim(), labels: structuredClone(labels), ...(scope === undefined ? {} : {scope: structuredClone(scope)}) });
  return next;
}
export function versionDiff(before, after) {
  const fields = ['name', 'definition', 'include', 'exclude'];
  const changes = [...new Set([...before.labels, ...after.labels].map(l => l.id))].flatMap(id => {
    const a = before.labels.find(l => l.id === id), b = after.labels.find(l => l.id === id);
    if (!a || !b) return [{ name: (b || a).name, field: 'label', before: a?.name || '无', after: b?.name || '从当前版本移除' }, ...fields.filter(f=>f!=='name').map(field=>({name:(b || a).name,field,before:a?.[field] || '无',after:b?.[field] || '无'}))];
    return fields.filter(f => a[f] !== b[f]).map(field => ({ name: b.name, field, before: a[field], after: b[field] }));
  });
  for (const field of ['subject','timeframe']) {
    if (before.scope?.[field] !== after.scope?.[field]) changes.push({name:'研究范围',field,before:before.scope?.[field] || '未明确（旧版本）',after:after.scope?.[field] || '未明确'});
  }
  return changes;
}
export function confirmedSummary(state, stance = null) {
  return currentVersion(state).labels.map(label => ({ label, evidence: state.paragraphs.flatMap(p => {
    if (reviewStatus(state, p.id) !== 'confirmed') return [];
    const review = latestReview(state, p.id);
    return review.annotations.filter(a => a.labelId === label.id && (stance === null || (a.stance || 'unclassified') === stance)).map(a => ({ paragraphId: p.id, documentId: p.documentId, ...a }));
  }) }));
}

// Portable evidence report, distinct from a restorable project backup.
export function evidenceReport(state, stance = 'supports') {
  if (!Object.hasOwn(stanceNames, stance)) throw new Error('无效的证据分组。');
  const report = {format:'tracenote-evidence',formatVersion:1,generatedAt:new Date().toISOString(),
    question:structuredClone(questions(state).find(q=>q.id===activeQuestion(state))),
    codebook:structuredClone(currentVersion(state)),stance,offsetUnit:'UTF-16 code units',
    policy:'仅含当前问题、当前规则及当前来源版本下人工确认的所选立场；出处为研究者录入，未验证真实性。',
    excludedParagraphs:{},documents:[],evidence:[]};
  const docs=new Set(); let size=JSON.stringify(report).length;
  const append=(target,row)=>{
    size+=JSON.stringify(row).length;
    if (size>1000000 || report.evidence.length>=5000) throw new Error('证据导出超过 100 万字符或 5000 条，请缩小项目后重试。');
    target.push(structuredClone(row));
  };
  for (const p of state.paragraphs) {
    const status=reviewStatus(state,p.id);
    if (status!=='confirmed') {report.excludedParagraphs[status]=(report.excludedParagraphs[status] || 0)+1;continue;}
    const review=latestReview(state,p.id);
    for (const a of review.annotations) {
      if ((a.stance || 'unclassified')!==stance) continue;
      if (!docs.has(p.documentId)) {
        append(report.documents,{...sourceDocument(state,p.documentId),sourceRevision:sourceRevision(state,p.documentId)});
        docs.add(p.documentId);
      }
      const context=state.paragraphs.find(x=>x.id===(a.stanceParagraphId || p.id));
      append(report.evidence,{paragraphId:p.id,documentId:p.documentId,paragraphText:p.text,
        ...a,stance:a.stance || 'unclassified',stanceParagraphId:context.id,stanceParagraphText:context.text,
        review:{id:review.id,versionId:review.versionId,sourceRevision:review.sourceRevision || 0,createdAt:review.createdAt || null,note:review.note}});
    }
  }
  return report;
}
