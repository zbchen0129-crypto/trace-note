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
export function currentVersion(state) { return state.versions.at(-1); }
export function latestReview(state, paragraphId) { return state.reviews.filter(r => r.paragraphId === paragraphId).at(-1); }
export function reviewStatus(state, paragraphId) {
  const review = latestReview(state, paragraphId);
  if (!review) return 'pending';
  if (review.versionId !== currentVersion(state).id) return 'stale';
  return review.status;
}
export function addDocument(state, name, text) {
  if (!name.trim()) throw new Error('请填写材料名称。');
  if (text.length > 200000) throw new Error('第一版每份材料最多 20 万字符。');
  const chunks = text.replace(/\r\n?/g, '\n').split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);
  if (!chunks.length) throw new Error('请先输入访谈内容。');
  const next = structuredClone(state);
  const id = `doc-${next.documents.length + 1}`;
  next.documents.push({ id, name: name.trim(), fictional: false });
  for (const text of chunks) next.paragraphs.push({ id: `P${String(next.nextParagraph++).padStart(3, '0')}`, documentId: id, text });
  return next;
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
    if (!annotation.quote?.trim()) throw new Error('每个标签都需要一段原文证据。');
    if (!Number.isInteger(annotation.start) || !Number.isInteger(annotation.end) || annotation.start < 0 || annotation.end <= annotation.start || paragraph.text.slice(annotation.start, annotation.end) !== annotation.quote) throw new Error('证据必须与当前段落原文完全一致。');
  }
  const next = structuredClone(state);
  next.reviews.push({ id: next.reviews.length + 1, paragraphId, versionId: version.id, annotations: structuredClone(annotations), note: note.trim(), status, source: 'human', createdAt: new Date().toISOString() });
  return next;
}
export function publishVersion(state, labels, reason) {
  if (!reason.trim()) throw new Error('请填写规则修改原因。');
  if (labels.length < 1 || labels.length > 8) throw new Error('第一版支持 1–8 个标签。');
  const ids = new Set(); const names = new Set();
  for (const label of labels) {
    if (!label.id || ids.has(label.id) || !label.name.trim() || names.has(label.name.trim()) || !label.definition.trim()) throw new Error('标签名称必须唯一，且定义不能为空。');
    ids.add(label.id); names.add(label.name.trim());
  }
  if (JSON.stringify(labels) === JSON.stringify(currentVersion(state).labels)) throw new Error('规则没有变化。');
  const next = structuredClone(state);
  next.versions.push({ id: currentVersion(state).id + 1, createdAt: new Date().toISOString(), reason: reason.trim(), labels: structuredClone(labels) });
  return next;
}
export function versionDiff(before, after) {
  const fields = ['name', 'definition', 'include', 'exclude'];
  return [...new Set([...before.labels, ...after.labels].map(l => l.id))].flatMap(id => {
    const a = before.labels.find(l => l.id === id), b = after.labels.find(l => l.id === id);
    if (!a || !b) return [{ name: (b || a).name, field: 'label', before: a?.name || '无', after: b?.name || '已删除' }];
    return fields.filter(f => a[f] !== b[f]).map(field => ({ name: b.name, field, before: a[field], after: b[field] }));
  });
}
export function confirmedSummary(state) {
  return currentVersion(state).labels.map(label => ({ label, evidence: state.paragraphs.flatMap(p => {
    if (reviewStatus(state, p.id) !== 'confirmed') return [];
    const review = latestReview(state, p.id);
    return review.annotations.filter(a => a.labelId === label.id).map(a => ({ paragraphId: p.id, documentId: p.documentId, ...a }));
  }) }));
}
