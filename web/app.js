import { STORAGE_KEY, createWorkspace, currentVersion, latestReview, reviewStatus, addDocument, saveReview, publishVersion, versionDiff, confirmedSummary } from './domain.js';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let state = createWorkspace(), storageError = '', revision = 0, configured = false, busy = false;
let view = 'workspace', selected = state.paragraphs[0]?.id, filter = 'all', dirty = false;
let pendingAnnotation = null, pendingRule = null;
const statusNames = { pending: '待标注', confirmed: '已确认', ambiguous: '歧义待核', stale: '版本待复核' };
function toast(message) { $('#toast').textContent = message; $('#toast').classList.add('visible'); clearTimeout(toast.timer); toast.timer = setTimeout(() => $('#toast').classList.remove('visible'), 7000); }
async function api(path, body) {
  if (busy) throw new Error('正在保存或生成，请稍候。');
  busy = true; document.body.classList.add('busy');
  try {
    const response = await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '本地服务请求失败。');
    return result;
  } finally { busy = false; document.body.classList.remove('busy'); }
}
function adopt(record) { state = record.state; revision = record.revision; dirty = false; }
async function commit(next) {
  if (storageError) throw new Error(storageError);
  adopt(await api('/api/workspace',{revision,state:next}));
}
function canLeave() { return !busy && (!dirty || window.confirm('当前修改尚未保存，确定离开吗？')); }
function documentName(p) { return state.documents.find(d => d.id === p.documentId)?.name || ''; }
function render() {
  $('.notice').textContent = storageError || `SQLite 本地保存 · ${configured ? 'AI 已配置，点击生成将把当前段落、邻近上下文及规则发送给 OpenAI' : 'AI 待配置：请在本地 .env 填写密钥和模型名称'} · 默认材料为虚构教学案例`;
  document.querySelectorAll('header button, nav button').forEach(b => b.disabled = Boolean(storageError));
  document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  const reviewed = state.paragraphs.filter(p => reviewStatus(state, p.id) === 'confirmed').length;
  const unresolved = state.paragraphs.filter(p => ['ambiguous', 'stale'].includes(reviewStatus(state, p.id))).length;
  $('#stats').innerHTML = [[state.documents.length, '份研究材料'], [state.paragraphs.length, '段原始文本'], [reviewed, '段已确认'], [unresolved, '段需要复核']].map(([n, text]) => `<div><strong>${n}</strong><span>${text}</span></div>`).join('') + `<div class="version-stat"><span class="pill">Codebook v${currentVersion(state).id}</span><span>当前标签版本</span></div>`;
  $('#content').innerHTML = view === 'workspace' ? workspaceHTML() : view === 'codebook' ? codebookHTML() : summaryHTML();
  if (view === 'workspace') { bindReview(); bindAI(); }
  if (view === 'codebook') { bindCodebook(); bindAI(); }
}
function highlighted(text, annotations) {
  const ranges = annotations.map(a => [a.start, a.end]).sort((a,b) => a[0]-b[0]);
  const merged = [];
  for (const range of ranges) { const prev = merged.at(-1); if (prev && range[0] <= prev[1]) prev[1] = Math.max(prev[1], range[1]); else merged.push([...range]); }
  let cursor = 0, result = '';
  for (const [start, end] of merged) { result += esc(text.slice(cursor, start)) + '<mark>' + esc(text.slice(start, end)) + '</mark>'; cursor = end; }
  return result + esc(text.slice(cursor));
}
function workspaceHTML() {
  const list = state.paragraphs.filter(p => filter === 'all' || (filter === 'queue' ? reviewStatus(state,p.id) !== 'confirmed' : reviewStatus(state,p.id) === filter));
  if (!list.some(p => p.id === selected)) selected = list[0]?.id;
  const p = state.paragraphs.find(p => p.id === selected), review = p && latestReview(state,p.id);
  return `<div class="section-title"><div><h2>访谈标注</h2><p>阅读上下文，记录标签与证据。</p></div><select id="filter" aria-label="筛选段落"><option value="all">全部段落</option><option value="queue">待标注与复核</option><option value="confirmed">已确认</option><option value="ambiguous">歧义待核</option><option value="stale">版本待复核</option></select></div><div class="workbench"><section class="paragraph-list" aria-label="段落列表"><div class="panel-label">MATERIALS <span>${list.length} 段</span></div>${list.map(item => `<button class="paragraph-item ${item.id === selected ? 'selected' : ''}" data-paragraph="${item.id}"><div><b>${item.id}</b><span class="status ${reviewStatus(state,item.id)}">${statusNames[reviewStatus(state,item.id)]}</span></div><p>${esc(item.text)}</p><small>${esc(documentName(item))}</small></button>`).join('') || '<p class="empty">此队列已清空。</p>'}</section><section class="source-panel">${p ? `<div class="panel-label">SOURCE TEXT <span>${p.id}</span></div><h3>${esc(documentName(p))}</h3><div class="source-text" id="source-text">${highlighted(p.text, review?.annotations || [])}</div><p class="hint">黄色高亮来自最近保存的证据。新证据请从上方复制到右侧。</p><details class="context"><summary>查看同一材料的相邻段落</summary>${contextHTML(p)}</details><div class="audit"><h4>人工决策记录 <span>${state.reviews.filter(r => r.paragraphId === p.id).length}</span></h4>${state.reviews.filter(r => r.paragraphId === p.id).slice().reverse().map(r => `<div class="audit-entry"><b>规则 v${r.versionId} · ${statusNames[r.status]}</b><small>${new Date(r.createdAt).toLocaleString('zh-CN')}</small><p>${esc(r.note || '未添加备注')} · ${r.annotations.length} 个标签</p>${r.annotations.map(a => `<p>「${esc(a.quote)}」</p>`).join('')}</div>`).join('') || '<p class="muted">保存标注后，修改记录会显示在这里。</p>'}</div>` : '<div class="empty">没有待处理材料，可以导入新访谈。</div>'}</section><section class="review-panel">${p ? reviewHTML(p, review) : ''}</section></div>`;
}
function contextHTML(p) {
  const doc = state.documents.find(d => d.id === p.documentId);
  if (doc.fictional) return '<p class="muted">这份材料是独立虚构摘录集合，相邻段落不代表同一次访谈的上下文。</p>';
  const parts = state.paragraphs.filter(x => x.documentId === p.documentId), index = parts.findIndex(x => x.id === p.id);
  return [parts[index-1], parts[index+1]].filter(Boolean).map(x => `<p><b>${x.id}</b> ${esc(x.text)}</p>`).join('') || '<p class="muted">没有相邻段落。</p>';
}
function reviewHTML(p, review) {
  return `<div class="panel-label">YOUR INTERPRETATION <span>v${currentVersion(state).id}</span></div><h3>标签与证据</h3>${aiHTML(p)}${reviewStatus(state,p.id) === 'stale' ? '<div class="inline-warning">规则已更新。以下是旧版标注，请根据当前定义重新检查；确认前不会计入汇总。</div>' : ''}<form id="review-form">${currentVersion(state).labels.map(label => {
    const a = (pendingAnnotation?.paragraphId === p.id ? pendingAnnotation.output : review)?.annotations.find(a => a.labelId === label.id);
    return `<div class="annotation"><label class="check-label"><input type="checkbox" name="label" value="${esc(label.id)}" ${a ? 'checked' : ''}>${esc(label.name)}</label><details><summary>查看定义与边界</summary><p>${esc(label.definition)}</p><p>纳入：${esc(label.include)}</p><p>排除：${esc(label.exclude)}</p></details><label class="evidence ${a ? '' : 'hidden'}">原文证据<textarea data-evidence="${esc(label.id)}" rows="2" placeholder="粘贴当前段落中的连续原文">${esc(a?.quote || '')}</textarea></label></div>`;
  }).join('')}<label class="note-label">判断备注<textarea name="note" rows="3" placeholder="例如：不放心含义不明，需要更多上下文。">${esc(review?.note || '')}</textarea></label><p class="hint">可多选；不选标签并确认，表示已审阅且无适用标签。</p><div class="review-actions"><button type="submit" class="primary">确认并保存</button><button type="button" id="ambiguous" class="secondary">标记歧义待核</button></div></form>`;
}
function bindReview() {
  $('#filter').value = filter;
  $('#filter').onchange = e => { if (!canLeave()) { e.target.value = filter; return; } filter = e.target.value; pendingAnnotation = null; dirty = false; render(); };
  document.querySelectorAll('[data-paragraph]').forEach(b => b.onclick = () => { if (!canLeave()) return; selected = b.dataset.paragraph; pendingAnnotation = null; dirty = false; render(); });
  const form = $('#review-form'); if (!form) return;
  form.oninput = () => { dirty = true; };
  form.querySelectorAll('[name=label]').forEach(input => input.onchange = () => input.closest('.annotation').querySelector('.evidence').classList.toggle('hidden', !input.checked));
  async function save(status) {
    try {
      const p = state.paragraphs.find(p => p.id === selected);
      const annotations = [...form.querySelectorAll('[name=label]:checked')].map(input => {
        const quote = input.closest('.annotation').querySelector('textarea').value.trim();
        const start = p.text.indexOf(quote);
        if (quote && p.text.indexOf(quote, start + 1) !== -1) throw new Error('证据在段落中出现多次，请复制更长的原文以明确定位。');
        return { labelId: input.value, quote, start, end: start + quote.length };
      });
      const next = saveReview(state, selected, annotations, form.elements.note.value, status);
      if (pendingAnnotation?.paragraphId === selected) adopt(await api('/api/decide',{revision,suggestionId:pendingAnnotation.id,action:'accept',review:next.reviews.at(-1)}));
      else await commit(next);
      pendingAnnotation = null; render(); toast('已保存人工判断与原文证据。');
    } catch (error) { toast(error.message); }
  }
  form.onsubmit = e => { e.preventDefault(); save('confirmed'); }; $('#ambiguous').onclick = () => save('ambiguous');
}
function codebookHTML() {
  const current = currentVersion(state);
  const editingLabels = structuredClone(current.labels);
  if (pendingRule) { const value = pendingRule.output; editingLabels.find(l => l.id === value.labelId)[value.field] = value.replacement; }
  return `<div class="section-title"><div><h2>标签与规则版本</h2><p>明确标准，保留每一次判断依据。</p></div><span class="pill">当前 v${current.id}</span></div><div class="codebook-grid"><section class="card"><h3>编辑下一版本</h3>${pendingRule ? `<div class="inline-warning">已载入 AI 规则建议。可修改内容，预览差异后确认发布。</div>` : ''}<p class="muted">修改不会立即生效。预览差异并确认后，才会发布新版本。</p><form id="codebook-form">${editingLabels.map(l => `<fieldset data-label-id="${esc(l.id)}"><label>标签名称<input name="name" value="${esc(l.name)}" required></label><label>定义<textarea name="definition" required rows="2">${esc(l.definition)}</textarea></label><div class="rule-columns"><label>纳入条件<textarea name="include" rows="3">${esc(l.include)}</textarea></label><label>排除条件<textarea name="exclude" rows="3">${esc(l.exclude)}</textarea></label></div></fieldset>`).join('')}<label>修改原因<textarea name="reason" rows="2" required placeholder="例如：P006 中历史问题已改善，需要明确时间边界。">${esc(pendingRule?.output.rationale || '')}</textarea></label><button class="primary">预览版本差异</button></form><div id="diff-preview"></div></section><section class="card version-history"><h3>待审核规则建议</h3>${ruleSuggestionsHTML()}<h3>版本历史</h3><p class="hint">第一版采取保守策略：新版本发布后，全部已审段落重新进入复核队列，包括原先无标签的段落。</p>${state.versions.slice().reverse().map((v) => `<article><span class="pill">v${v.id}</span><small>${new Date(v.createdAt).toLocaleString('zh-CN')}</small><p>${esc(v.reason)}</p>${v.id > 1 ? diffHTML(versionDiff(state.versions.find(x => x.id === v.id-1),v)) : '<p class="muted">4 个初始主题标签</p>'}</article>`).join('')}</section></div>`;
}
function diffHTML(diffs) {
  const names = { name: '名称', definition: '定义', include: '纳入条件', exclude: '排除条件', label: '标签' };
  return diffs.map(d => `<div class="diff"><b>${esc(d.name)} · ${names[d.field]}</b><div class="before">− ${esc(d.before)}</div><div class="after">＋ ${esc(d.after)}</div></div>`).join('');
}
function bindCodebook() {
  const form = $('#codebook-form');
  form.oninput = () => { dirty = true; $('#diff-preview').innerHTML = ''; };
  form.onsubmit = e => {
    e.preventDefault();
    try {
      const labels = [...form.querySelectorAll('fieldset')].map(f => Object.fromEntries([['id',f.dataset.labelId], ...['name','definition','include','exclude'].map(k => [k,f.querySelector(`[name=${k}]`).value.trim()])]));
      const next = publishVersion(state, labels, form.elements.reason.value);
      const count = state.paragraphs.filter(p => latestReview(state,p.id)).length;
      $('#diff-preview').innerHTML = `<h3>确认发布 v${currentVersion(next).id}</h3>${diffHTML(versionDiff(currentVersion(state),currentVersion(next)))}<p>${count} 段已审材料需要重新复核，旧判断将完整保留。</p><button id="publish" class="primary" type="button">确认发布新版本</button>`;
      $('#publish').onclick = async () => { try { if (pendingRule) adopt(await api('/api/decide',{revision,suggestionId:pendingRule.id,action:'accept',labels,reason:form.elements.reason.value})); else await commit(next); pendingRule = null; render(); toast('新版本已发布，旧标注已进入复核队列。'); } catch (error) { toast(error.message); } };
      $('#diff-preview').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (error) { toast(error.message); }
  };
}
function summaryHTML() {
  return `<div class="section-title"><div><h2>主题与原文证据</h2><p>仅展示当前规则版本下，研究者已确认的标注。</p></div><span class="pill">v${currentVersion(state).id}</span></div><div class="summary-note">数量指带标签的段落数，同一段可以有多个标签。不代表人数、总体比例或因果关系。以下引文均为保存的原文片段。</div><div class="summary-grid">${confirmedSummary(state).map(({ label, evidence }) => `<section class="card theme-card"><div class="theme-heading"><h3>${esc(label.name)}</h3><span>${evidence.length} 段</span></div><p class="muted">${esc(label.definition)}</p>${evidence.map(e => `<button class="quote-card" data-jump="${e.paragraphId}"><blockquote>“${esc(e.quote)}”</blockquote><span>${e.paragraphId} · 查看原文 ↗</span></button>`).join('') || '<div class="empty">暂无当前版本的已确认标注。</div>'}</section>`).join('')}</div>`;
}
document.querySelector('nav').onclick = e => { const button = e.target.closest('[data-view]'); if (!button || !canLeave()) return; view = button.dataset.view; pendingAnnotation = null; pendingRule = null; dirty = false; render(); };
$('#content').addEventListener('click', e => { const button = e.target.closest('[data-jump]'); if (!button || !canLeave()) return; view = 'workspace'; selected = button.dataset.jump; filter = 'all'; dirty = false; render(); });
$('#import').onclick = () => { if (!canLeave()) return; $('#import-dialog').showModal(); };
$('#cancel-import').onclick = () => $('#import-dialog').close();
$('#file').onchange = async e => {
  const file = e.target.files[0]; if (!file) return;
  if (file.size > 800000) { toast('文件过大，请导入较小的 TXT 材料。'); return; }
  try { const form = $('#import-form'); form.elements.text.value = await file.text(); if (!form.elements.name.value) form.elements.name.value = file.name.replace(/\.txt$/i,''); } catch { toast('无法读取该文件。'); }
};
$('#import-form').onsubmit = async e => {
  e.preventDefault(); const form = e.target;
  try { const next = addDocument(state,form.elements.name.value,form.elements.text.value); const nextSelected = next.paragraphs[state.paragraphs.length].id; await commit(next); selected = nextSelected; pendingAnnotation = null; view = 'workspace'; filter = 'all'; form.reset(); $('#import-dialog').close(); render(); toast('访谈已导入，原文与段落 ID 已保存。'); } catch (error) { toast(error.message); }
};
$('#export').onclick = () => {
  const payload = storageError ? localStorage.getItem(STORAGE_KEY) || JSON.stringify(state) : JSON.stringify(state,null,2);
  const url = URL.createObjectURL(new Blob([payload],{type:'application/json'})); const a = document.createElement('a'); a.href = url; a.download = 'tracenote-project.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000); toast('已导出项目记录。');
};
window.addEventListener('beforeunload', e => { if (dirty || busy) { e.preventDefault(); e.returnValue = ''; } });
await boot();

function decisionFor(id) { return state.decisions?.find(d => d.suggestionId === id); }
function aiHTML(p) {
  const suggestions = (state.suggestions || []).filter(x => x.paragraphId === p.id && x.kind === 'annotation');
  return `<div class="ai-panel"><div class="actions"><button type="button" class="secondary" id="generate-ai" ${!configured ? 'disabled' : ''}>生成 AI 标注建议</button><button type="button" class="secondary" id="generate-rule" ${!configured ? 'disabled' : ''}>根据纠正建议规则</button></div><p class="hint">模型建议需人工审核。只有确认保存的标注才进入主题汇总。</p>${suggestions.slice().reverse().map(x => {
    const d = decisionFor(x.id), stale = x.versionId !== currentVersion(state).id;
    return `<article class="ai-suggestion"><b>AI 建议 · v${x.versionId} · ${esc(x.model)}</b><p>${x.output.annotations.map(a => `${esc(currentVersion(state).labels.find(l => l.id === a.labelId)?.name || a.labelId)}：「${esc(a.quote)}」`).join('<br>') || '建议不贴标签'}</p><p>${esc([...x.output.reviewReasons,x.output.abstainReason].filter(Boolean).join('；'))}</p>${d ? `<span class="pill">${esc({accepted:'已接受',modified:'修改后确认',rejected:'已拒绝'}[d.status])}</span><p>${esc(d.note || '')}</p>` : `<button type="button" class="secondary" data-apply-annotation="${x.id}" ${stale ? 'disabled' : ''}>${stale ? '旧版建议，请重新生成' : '载入表单审核'}</button> <button type="button" class="secondary" data-reject="${x.id}">拒绝</button>`}</article>`;
  }).join('')}${pendingAnnotation?.paragraphId === p.id ? '<p class="inline-warning">正在审核 AI 建议，可修改标签与证据，再点击下方确认保存。</p>' : ''}</div>`;
}
function ruleSuggestionsHTML() {
  return (state.suggestions || []).filter(x => x.kind === 'rule').slice().reverse().map(x => {
    const d = decisionFor(x.id), v = x.output;
    return `<article class="ai-suggestion"><b>${esc(x.paragraphId)} · 规则 v${x.versionId}</b><p>${esc(v.replacement)}</p><p class="muted">${esc(v.rationale)}</p>${d ? `<span class="pill">${esc({accepted:'已接受',modified:'修改后发布',rejected:'已拒绝'}[d.status])}</span>` : `<button class="secondary" data-apply-rule="${x.id}" ${x.versionId !== currentVersion(state).id ? 'disabled' : ''}>载入规则编辑器</button> <button class="secondary" data-reject="${x.id}">拒绝</button>`}</article>`;
  }).join('') || '<p class="muted">先保存人工纠正和备注，再在标注页请求规则建议。</p>';
}
function bindAI() {
  async function generate(kind) {
    if (!canLeave()) return;
    try {
      toast('正在请求模型，请等待；本次不会自动确认标注或修改规则。');
      adopt(await api('/api/suggest',{revision,paragraphId:selected,kind,requestId:crypto.randomUUID()}));
      pendingAnnotation = null;
      if (kind === 'rule') view = 'codebook';
      render(); toast('建议已保存，请人工审核。');
    } catch (error) { toast(error.message); }
  }
  if ($('#generate-ai')) $('#generate-ai').onclick = () => generate('annotation');
  if ($('#generate-rule')) $('#generate-rule').onclick = () => generate('rule');
  document.querySelectorAll('[data-apply-annotation]').forEach(b => b.onclick = () => {
    if (!canLeave()) return;
    pendingAnnotation = state.suggestions.find(x => x.id === b.dataset.applyAnnotation); render(); dirty = true;
  });
  document.querySelectorAll('[data-apply-rule]').forEach(b => b.onclick = () => {
    if (!canLeave()) return;
    pendingRule = state.suggestions.find(x => x.id === b.dataset.applyRule); render(); dirty = true;
  });
  document.querySelectorAll('[data-reject]').forEach(b => b.onclick = async () => {
    if (!canLeave()) return;
    const note = window.prompt('请记录拒绝这条建议的原因：'); if (!note?.trim()) return;
    try { adopt(await api('/api/decide',{revision,suggestionId:b.dataset.reject,action:'reject',note})); pendingAnnotation = null; pendingRule = null; render(); toast('已记录拒绝原因。'); } catch (error) { toast(error.message); }
  });
}
async function boot() {
  try {
    const status = await api('/api/status'); configured = status.configured;
    let record = await api('/api/workspace');
    if (!record.state) {
      const old = localStorage.getItem(STORAGE_KEY);
      record = await api('/api/workspace',{revision:0,state:old ? JSON.parse(old) : createWorkspace()});
    }
    adopt(record); selected = state.paragraphs[0]?.id; render();
  } catch (error) {
    storageError = '本地数据库连接或迁移失败：' + error.message + '。请运行 python3 server.py；旧浏览器记录仍保留。';
    render(); $('#content').innerHTML = '<div class="inline-warning">'+esc(storageError)+'</div>';
  }
}
$('#restore').onclick = () => { if (canLeave()) $('#restore-file').click(); };
$('#restore-file').onchange = async e => {
  const file = e.target.files[0]; if (!file) return;
  try {
    if (file.size > 5000000) throw new Error('备份不得超过 5MB。');
    const restored = JSON.parse(await file.text());
    if (!window.confirm('将恢复此备份的访谈、规则和人工记录。当前项目仍保留在数据库历史快照中；AI 建议和审核关联不从备份导入。继续吗？')) return;
    adopt(await api('/api/restore',{revision,state:restored})); pendingAnnotation = null; pendingRule = null; selected = state.paragraphs[0]?.id; view = 'workspace'; filter = 'all'; render(); toast('人工研究记录已恢复；恢复前版本保留在数据库历史中。');
  } catch (error) { toast(error.message); } finally { e.target.value = ''; }
};
