import { STORAGE_KEY, createWorkspace, currentVersion, latestReview, reviewStatus, addDocument, saveReview, publishVersion, versionDiff, confirmedSummary, stanceNames, questions, activeQuestion, questionVersions, inQuestion, addQuestion, sourceCitation, sourceDocument, sourceRevision, evidenceReport } from './domain.js';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let state = createWorkspace(), storageError = '', revision = 0, configured = false, busy = false;
let view = 'workspace', selected = state.paragraphs[0]?.id, filter = 'all', dirty = false;
let summaryStance = 'supports';
let pendingAnnotation = null, pendingRule = null;
const statusNames = { pending: '待标注', confirmed: '已确认', ambiguous: '歧义待核', stale: '版本待复核', 'source-stale': '来源待复核' };
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
function adopt(record) { const qid=activeQuestion(state); state = record.state; if (questions(state).some(q=>q.id===qid)) state.activeQuestionId=qid; revision = record.revision; dirty = false; }
async function commit(next) {
  if (storageError) throw new Error(storageError);
  const result=await api('/api/workspace',{revision,state:next}); state=next; adopt(result);
}
function canLeave() { return !busy && (!dirty || window.confirm('当前修改尚未保存，确定离开吗？')); }
function documentName(p) { return state.documents.find(d => d.id === p.documentId)?.name || ''; }
function render() {
  $('#questions').innerHTML = `<label>当前研究问题<select id="question-select">${questions(state).map(q=>`<option value="${esc(q.id)}" ${q.id===activeQuestion(state)?'selected':''}>${esc(q.text)}</option>`).join('')}</select></label><button type="button" id="new-question" class="secondary">＋ 新增研究问题</button><p class="hint">材料共享；下方标注、规则、进度和汇总仅属于当前问题。</p>`;
  $('#question-select').onchange = e => {
    if (!canLeave()) { e.target.value=activeQuestion(state); return; }
    state.activeQuestionId=e.target.value; pendingAnnotation=null; pendingRule=null; dirty=false; filter='all'; render();
  };
  $('#new-question').onclick = () => { if (canLeave()) $('#question-dialog').showModal(); };

  $('.notice').textContent = storageError || `SQLite 本地保存 · ${configured ? 'AI 已配置，预览确认后将把所选原文、上下文及规则发送给 OpenAI' : 'AI 待配置：请在本地 .env 填写密钥和模型名称'} · 默认材料为虚构教学案例`;
  document.querySelectorAll('header button, nav button').forEach(b => b.disabled = Boolean(storageError));
  document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  const reviewed = state.paragraphs.filter(p => reviewStatus(state, p.id) === 'confirmed').length;
  const unresolved = state.paragraphs.filter(p => ['ambiguous', 'stale', 'source-stale'].includes(reviewStatus(state, p.id))).length;
  $('#stats').innerHTML = [[state.documents.length, '份研究材料'], [state.paragraphs.length, '段原始文本'], [reviewed, '段已确认'], [unresolved, '段需要复核']].map(([n, text]) => `<div><strong>${n}</strong><span>${text}</span></div>`).join('') + `<div class="version-stat"><span class="pill">Codebook v${currentVersion(state).id}</span><span>当前标签版本</span></div>`;
  $('#content').innerHTML = view === 'workspace' ? workspaceHTML() : view === 'codebook' ? codebookHTML() : summaryHTML();
  if (view === 'workspace') { bindReview(); bindAI(); }
  if (view === 'codebook') { bindCodebook(); bindAI(); }
  if (view === 'summary') {
    $('#summary-stance').onchange = e => { summaryStance=e.target.value; render(); };
    $('#export-evidence').onclick = () => {
      try {
        const report=evidenceReport(state,summaryStance);
        const url=URL.createObjectURL(new Blob([JSON.stringify(report)],{type:'application/json'}));
        const a=document.createElement('a'); a.href=url; a.download='tracenote-evidence.json'; a.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000); toast(`已导出当前问题与分组的 ${report.evidence.length} 条证据。`);
      } catch (error) { toast(error.message); }
    };
  }
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
  return `<div class="section-title"><div><h2>材料标注</h2><p>阅读上下文，记录标签与证据。</p></div><select id="filter" aria-label="筛选段落"><option value="all">全部段落</option><option value="queue">待标注与复核</option><option value="confirmed">已确认</option><option value="ambiguous">歧义待核</option><option value="stale">版本待复核</option><option value="source-stale">来源待复核</option></select></div><div class="workbench"><section class="paragraph-list" aria-label="段落列表"><div class="panel-label">MATERIALS <span>${list.length} 段</span></div>${list.map(item => `<button class="paragraph-item ${item.id === selected ? 'selected' : ''}" data-paragraph="${item.id}"><div><b>${item.id}</b><span class="status ${reviewStatus(state,item.id)}">${statusNames[reviewStatus(state,item.id)]}</span></div><p>${esc(item.text)}</p><small>${esc(documentName(item))}</small></button>`).join('') || '<p class="empty">此队列已清空。</p>'}</section><section class="source-panel">${p ? `<div class="panel-label">SOURCE TEXT <span>${p.id}</span></div><h3>${esc(documentName(p))}</h3><p class="hint">${esc(sourceCitation(sourceDocument(state,p.documentId)))}</p>${sourceHistoryHTML(p)}<div class="source-text" id="source-text">${highlighted(p.text, review?.annotations || [])}</div><p class="hint">黄色高亮来自最近保存的证据。新证据请从上方复制到右侧。</p><details class="context"><summary>查看同一材料的相邻段落</summary>${contextHTML(p)}</details><div class="audit"><h4>人工决策记录 <span>${state.reviews.filter(r => r.paragraphId === p.id && inQuestion(state, r)).length}</span></h4>${state.reviews.filter(r => r.paragraphId === p.id && inQuestion(state, r)).slice().reverse().map(r => `<div class="audit-entry"><b>规则 v${r.versionId} · 来源版本 ${r.sourceRevision || 0} · ${statusNames[r.status]}</b><small>${r.createdAt && !Number.isNaN(Date.parse(r.createdAt)) ? new Date(r.createdAt).toLocaleString('zh-CN') : '时间未记录'}</small><p>${esc(r.note || '未添加备注')} · ${r.annotations.length} 个标签</p>${r.annotations.map(a => `<p>${esc(state.versions.find(v=>v.id===r.versionId)?.labels.find(l=>l.id===a.labelId)?.name || a.labelId)}：「${esc(a.quote)}」 · ${esc(a.holder || '归属未记录')} · ${stanceNames[a.stance || 'unclassified']}<br>态度依据（${esc(a.stanceParagraphId || r.paragraphId)}）：${esc(a.stanceQuote || '未记录')}</p>`).join('')}</div>`).join('') || '<p class="muted">保存标注后，修改记录会显示在这里。</p>'}</div>` : '<div class="empty">没有待处理材料，可以导入新材料。</div>'}</section><section class="review-panel">${p ? reviewHTML(p, review) : ''}</section></div>`;
}
function contextHTML(p) {
  const doc = state.documents.find(d => d.id === p.documentId);
  if (doc.fictional) return '<p class="muted">这份材料是独立虚构摘录集合，相邻段落不代表同一次访谈的上下文。</p>';
  const parts = state.paragraphs.filter(x => x.documentId === p.documentId), index = parts.findIndex(x => x.id === p.id);
  return [parts[index-1], parts[index+1]].filter(Boolean).map(x => `<p><b>${x.id}</b> ${esc(x.text)}</p>`).join('') || '<p class="muted">没有相邻段落。</p>';
}
function reviewHTML(p, review) {
  return `<div class="panel-label">YOUR INTERPRETATION <span>v${currentVersion(state).id}</span></div><h3>标签与证据</h3>${aiHTML(p)}${review?.annotations.some(a=>!currentVersion(state).labels.some(l=>l.id===a.labelId)) ? '<p class="inline-warning">旧判断包含已移除标签，其证据仍保留在左侧历史中。请按当前标签重新审核；保存不会自动迁移旧标签。</p>' : ''}${reviewStatus(state,p.id) === 'source-stale' ? '<div class="inline-warning">来源已更正。请核对出处、观点归属及当前规则后重新确认；旧判断保留，但暂不计入汇总或证据导出。</div>' : ''}${reviewStatus(state,p.id) === 'stale' ? '<div class="inline-warning">规则已更新。以下是旧版标注，请根据当前定义重新检查；确认前不会计入汇总。</div>' : ''}<form id="review-form">${currentVersion(state).labels.map(label => {
    const a = (pendingAnnotation?.paragraphId === p.id ? pendingAnnotation.output : review)?.annotations.find(a => a.labelId === label.id);
    return `<div class="annotation"><label class="check-label"><input type="checkbox" name="label" value="${esc(label.id)}" ${a ? 'checked' : ''}>${esc(label.name)}</label><details><summary>查看定义与边界</summary><p>${esc(label.definition)}</p><p>纳入：${esc(label.include)}</p><p>排除：${esc(label.exclude)}</p></details><div class="evidence ${a ? '' : 'hidden'}"><label>原文证据<textarea data-evidence="${esc(label.id)}" rows="2" placeholder="粘贴当前段落中的连续原文">${esc(a?.quote || '')}</textarea></label><label>观点归属<input data-holder maxlength="200" placeholder="如：作者本人、受访者、被引研究" value="${esc(a?.holder || '')}"></label><label>作者／受访者对该解释的态度<select data-stance><option value="">请选择（不默认支持）</option>${Object.entries(stanceNames).filter(([k]) => k !== 'unclassified').map(([k,v]) => `<option value="${k}" ${a?.stance === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label><label>态度依据段落 ID<input data-stance-source maxlength="20" value="${esc(a?.stanceParagraphId || p.id)}" placeholder="如 P001，同一材料内"></label><label>态度判断依据<textarea data-stance-quote rows="2" maxlength="2000" placeholder="复制包含否定、转折或认可的原文。填写上方段落 ID 并复制该段原文；无法取得依据时选择待核。">${esc(a?.stanceQuote || '')}</textarea></label></div></div>`;
  }).join('')}<label class="note-label">判断备注<textarea name="note" rows="3" placeholder="例如：不放心含义不明，需要更多上下文。">${esc(review?.note || '')}</textarea></label><p class="hint">可多选；不选标签并确认，表示已审阅且无适用标签。</p><div class="review-actions"><button type="submit" class="primary">确认并保存</button><button type="button" id="ambiguous" class="secondary">标记歧义待核</button></div></form>`;
}
function bindReview() {
  if ($('#edit-source')) $('#edit-source').onclick = () => { if (canLeave()) editSource(); };
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
        const box = input.closest('.annotation');
        return { labelId: input.value, quote, start, end: start + quote.length, holder:box.querySelector('[data-holder]').value.trim(), stance:box.querySelector('[data-stance]').value, stanceQuote:box.querySelector('[data-stance-quote]').value.trim(), stanceParagraphId:box.querySelector('[data-stance-source]').value.trim() };
      });
      const next = saveReview(state, selected, annotations, form.elements.note.value, status);
      if (pendingAnnotation?.paragraphId === selected) adopt(await api('/api/decide',{revision,suggestionId:pendingAnnotation.id,action:'accept',review:next.reviews.at(-1)}));
      else await commit(next);
      pendingAnnotation = null; render(); toast('已保存人工判断与原文证据。');
    } catch (error) { toast(error.message); }
  }
  form.onsubmit = e => { e.preventDefault(); save('confirmed'); }; $('#ambiguous').onclick = () => save('ambiguous');
}
function labelEditorHTML(l) {
  return `<fieldset data-label-id="${esc(l.id)}"><label>标签名称<input name="name" value="${esc(l.name)}" required maxlength="120"></label><label>定义<textarea name="definition" required rows="2" maxlength="2000">${esc(l.definition)}</textarea></label><div class="rule-columns"><label>纳入条件<textarea name="include" rows="3" maxlength="2000">${esc(l.include)}</textarea></label><label>排除条件<textarea name="exclude" rows="3" maxlength="2000">${esc(l.exclude)}</textarea></label></div><button type="button" class="secondary" data-remove-label>从下一版本移除</button></fieldset>`;
}
function codebookHTML() {
  const current = currentVersion(state);
  const editingLabels = structuredClone(current.labels);
  if (pendingRule) { const value = pendingRule.output; editingLabels.find(l => l.id === value.labelId)[value.field] = value.replacement; }
  return `<div class="section-title"><div><h2>标签与规则版本</h2><p>明确标准，保留每一次判断依据。</p></div><span class="pill">当前 v${current.id}</span></div><div class="codebook-grid"><section class="card"><h3>编辑下一版本</h3>${pendingRule ? `<div class="inline-warning">已载入 AI 规则建议。可修改内容，预览差异后确认发布。</div>` : ''}<p class="muted">修改不会立即生效。预览差异并确认后，才会发布新版本。</p><form id="codebook-form"><fieldset><legend>研究范围（随规则版本保存）</legend><p class="hint">${current.scope ? "修改范围后，旧判断将重新进入复核队列。" : "旧版本未明确范围；以下为建议值，预览并发布后才生效。"}</p><label>研究对象<input name="scopeSubject" maxlength="200" required value="${esc(current.scope?.subject ?? (activeQuestion(state)==='Q1' ? '受访者本人；排除转述的其他人的经历' : '材料作者或当前受访者'))}"></label><label>时间范围<input name="scopeTimeframe" maxlength="200" required value="${esc(current.scope?.timeframe ?? (activeQuestion(state)==='Q1' ? '访谈所述当前退出公共交通的原因；排除已改善且不再影响当前决定的历史问题' : ''))}"></label></fieldset><div id="label-drafts">${editingLabels.map(labelEditorHTML).join('')}</div><div id="removed-labels"></div><button type="button" id="add-label" class="secondary">＋ 新增标签</button><p class="hint">每个问题保留 1–8 个标签。移除仅在发布后生效；历史标注保留。改名沿用原标签，新增标签拥有独立身份。</p><label>修改原因<textarea name="reason" rows="2" required placeholder="例如：P006 中历史问题已改善，需要明确时间边界。">${esc(pendingRule?.output.rationale || '')}</textarea></label><button class="primary">预览版本差异</button></form><div id="diff-preview"></div></section><section class="card version-history"><h3>待审核规则建议</h3>${ruleSuggestionsHTML()}<h3>版本历史</h3><p class="hint">第一版采取保守策略：新版本发布后，当前问题的全部已审段落重新进入复核队列，包括原先无标签的段落。</p>${questionVersions(state).slice().reverse().map((v) => `<article><span class="pill">v${v.id}</span><small>${new Date(v.createdAt).toLocaleString('zh-CN')}</small><p>${esc(v.reason)}</p>${questionVersions(state).indexOf(v) > 0 ? diffHTML(versionDiff(questionVersions(state)[questionVersions(state).indexOf(v)-1],v)) : '<p class="muted">当前问题的初始规则</p>'}</article>`).join('')}</section></div>`;
}
function diffHTML(diffs) {
  const names = { name: '名称', definition: '定义', include: '纳入条件', exclude: '排除条件', label: '标签', subject: '研究对象', timeframe: '时间范围' };
  return diffs.map(d => `<div class="diff"><b>${esc(d.name)} · ${names[d.field]}</b><div class="before">− ${esc(d.before)}</div><div class="after">＋ ${esc(d.after)}</div></div>`).join('');
}
function bindCodebook() {
  const form = $('#codebook-form');
  const changed = () => { dirty = true; $('#diff-preview').innerHTML = ''; };
  const activeDrafts = () => [...form.querySelectorAll('fieldset[data-label-id]:not([data-removed])')];
  const refreshRemoved = () => {
    $('#removed-labels').innerHTML = [...form.querySelectorAll('[data-removed]')].map(f=>`<p>${esc(f.querySelector('[name=name]').value || '未命名标签')}：待移除 <button type="button" data-undo-label="${esc(f.dataset.labelId)}">撤销移除</button></p>`).join('');
    $('#add-label').disabled = activeDrafts().length >= 8;
  };
  form.oninput = changed;
  $('#add-label').onclick = () => {
    if (activeDrafts().length >= 8) { toast('最多保留 8 个标签。'); return; }
    // Bound all draft fields, including removed entries, for repeated add/remove operations.
    if (form.querySelectorAll('[data-label-id]').length >= 24) { toast('本次草稿最多操作 24 个标签，请先发布或离开后重新编辑。'); return; }
    $('#label-drafts').insertAdjacentHTML('beforeend',labelEditorHTML({id:`label-${crypto.randomUUID()}`,name:'',definition:'',include:'',exclude:''}));
    changed(); refreshRemoved(); activeDrafts().at(-1).querySelector('[name=name]').focus();
  };
  form.onclick = e => {
    const remove=e.target.closest('[data-remove-label]'), undo=e.target.closest('[data-undo-label]');
    if (remove) {
      if (activeDrafts().length <= 1) { toast('至少保留一个标签；可先新增替代标签。'); return; }
      const f=remove.closest('fieldset'); f.dataset.removed='true'; f.hidden=true; f.disabled=true; changed(); refreshRemoved();
    }
    if (undo) {
      if (activeDrafts().length >= 8) { toast('最多保留 8 个标签，请先移除另一个标签。'); return; }
      const f=[...form.querySelectorAll('[data-removed]')].find(f=>f.dataset.labelId===undo.dataset.undoLabel);
      delete f.dataset.removed; f.hidden=false; f.disabled=false; changed(); refreshRemoved();
    }
  };
  refreshRemoved();
  form.onsubmit = e => {
    e.preventDefault();
    try {
      const labels = activeDrafts().map(f => Object.fromEntries([['id',f.dataset.labelId], ...['name','definition','include','exclude'].map(k => [k,f.querySelector(`[name=${k}]`).value.trim()])]));
      const scope = {subject:form.elements.scopeSubject.value.trim(), timeframe:form.elements.scopeTimeframe.value.trim()};
      const next = publishVersion(state, labels, form.elements.reason.value, scope);
      const count = state.paragraphs.filter(p => latestReview(state,p.id)).length;
      $('#diff-preview').innerHTML = `<h3>确认发布 v${currentVersion(next).id}</h3>${diffHTML(versionDiff(currentVersion(state),currentVersion(next)))}<p>${count} 段已审材料需要重新复核，旧判断将完整保留。</p><button id="publish" class="primary" type="button">确认发布新版本</button>`;
      $('#publish').onclick = async () => { try { if (pendingRule) adopt(await api('/api/decide',{revision,suggestionId:pendingRule.id,action:'accept',labels,scope,reason:form.elements.reason.value})); else await commit(next); pendingRule = null; render(); toast('新版本已发布，旧标注已进入复核队列。'); } catch (error) { toast(error.message); } };
      $('#diff-preview').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (error) { toast(error.message); }
  };
}
function summaryHTML() {
  return `<div class="section-title"><div><h2>主题与原文证据</h2><p>仅展示当前规则和来源版本下，研究者已确认的标注。</p></div><span class="pill">v${currentVersion(state).id}</span></div><div class="summary-note">数量指带标签的段落数，同一段可以有多个标签。不代表人数、总体比例或因果关系。以下引文均为保存的原文片段。</div><label>证据关系<select id="summary-stance">${Object.entries(stanceNames).map(([k,v]) => `<option value="${k}" ${summaryStance === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label><p class="hint">分组表示人工确认的文本立场，不代表观点已被事实证明。旧记录须复核后才能计入支持证据。</p><button id="export-evidence" class="secondary">导出当前分组证据 JSON</button><p class="hint">仅导出当前问题与所选立场，附原文、出处、规则及人工判断。来源待复核 ${state.paragraphs.filter(p=>reviewStatus(state,p.id)==='source-stale').length} 段，已排除。此文件不能用作项目恢复备份。</p><div class="summary-grid">${confirmedSummary(state, summaryStance).map(({ label, evidence }) => `<section class="card theme-card"><div class="theme-heading"><h3>${esc(label.name)}</h3><span>${evidence.length} 段</span></div><p class="muted">${esc(label.definition)}</p>${evidence.map(e => `<button class="quote-card" data-jump="${e.paragraphId}"><blockquote>“${esc(e.quote)}”</blockquote><p>${esc(sourceCitation(sourceDocument(state,e.documentId)))}</p><span>${e.paragraphId} · ${esc(e.holder || '归属未记录')} · ${stanceNames[e.stance || 'unclassified']}</span><p>${esc(e.stanceQuote || '尚无态度依据')}</p><span>态度依据段落：${esc(e.stanceParagraphId || e.paragraphId)}</span></button>${e.stanceParagraphId && e.stanceParagraphId !== e.paragraphId ? `<button class="secondary" data-jump="${esc(e.stanceParagraphId)}">查看态度依据 ${esc(e.stanceParagraphId)}</button>` : ''}`).join('') || '<div class="empty">当前分组暂无已确认标注。</div>'}</section>`).join('')}</div>`;
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
  try { const next = addDocument(state,form.elements.name.value,form.elements.text.value,{type:form.elements.sourceType.value,author:form.elements.author.value.trim(),year:form.elements.year.value.trim(),url:form.elements.sourceUrl.value.trim(),locator:form.elements.locator.value.trim()}); const nextSelected = next.paragraphs[state.paragraphs.length].id; await commit(next); selected = nextSelected; pendingAnnotation = null; view = 'workspace'; filter = 'all'; form.reset(); $('#import-dialog').close(); render(); toast('材料已导入，原文与段落 ID 已保存。'); } catch (error) { toast(error.message); }
};
$('#export').onclick = () => {
  const payload = storageError ? localStorage.getItem(STORAGE_KEY) || JSON.stringify(state) : JSON.stringify(state,null,2);
  const url = URL.createObjectURL(new Blob([payload],{type:'application/json'})); const a = document.createElement('a'); a.href = url; a.download = 'tracenote-project.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000); toast('已导出项目记录。');
};
window.addEventListener('beforeunload', e => { if (dirty || busy) { e.preventDefault(); e.returnValue = ''; } });
$('#cancel-question').onclick = () => $('#question-dialog').close();
$('#question-form').onsubmit = async e => {
  e.preventDefault(); const f=e.target;
  try { await commit(addQuestion(state,f.elements.question.value,f.elements.labelName.value,f.elements.definition.value)); pendingAnnotation=null; pendingRule=null; view='codebook'; filter='all'; f.reset(); $('#question-dialog').close(); render(); toast('研究问题已创建。已有问题的判断保持独立。'); } catch(error) { toast(error.message); }
};
await boot();

function decisionFor(id) { return state.decisions?.find(d => d.suggestionId === id); }
function suggestionStale(x) {
 const p=state.paragraphs.find(p=>p.id===x.paragraphId);
 return x.versionId !== currentVersion(state).id || sourceRevision(state,p.documentId) !== (x.requestSnapshot?.sourceRevision || 0) || (x.requestSnapshot && JSON.stringify(sourceDocument(state,p.documentId)?.source) !== JSON.stringify(x.requestSnapshot.sourceMetadata));
}
function aiHTML(p) {
  const suggestions = (state.suggestions || []).filter(x => x.paragraphId === p.id && x.kind === 'annotation' && inQuestion(state, x));
  return `<div class="ai-panel"><label>补充上下文段落 ID（同一材料，最多 4 段）<input id="extra-context" placeholder="例如 P007, P012" maxlength="100"></label><p class="hint">${currentVersion(state).scope ? `研究对象：${esc(currentVersion(state).scope.subject)}<br>时间范围：${esc(currentVersion(state).scope.timeframe)}` : '当前版本尚未明确研究对象和时间范围，可在“标签与规则版本”中设置并发布。'}</p><div class="actions"><button type="button" class="secondary" id="generate-ai" ${!configured ? 'disabled' : ''}>生成 AI 标注建议</button><button type="button" class="secondary" id="generate-rule" ${!configured ? 'disabled' : ''}>根据纠正建议规则</button></div><p class="hint">模型读取当前段落、相邻段落和你选择的补充段落；发送前可预览。独立虚构摘录不带上下文。涉及前文时间、人物或指代时，请先核对原文；信息不足可标记歧义待核。只有确认保存的标注才进入主题汇总。</p>${suggestions.slice().reverse().map(x => {
    const d = decisionFor(x.id), stale = suggestionStale(x);
    return `<article class="ai-suggestion"><b>AI 建议 · v${x.versionId} · ${esc(x.model)}</b><p class="hint">${x.researchScope ? `请求范围：${esc(x.researchScope.subject)}；${esc(x.researchScope.timeframe)}` : '旧请求未明确研究范围'}</p><p>${x.output.annotations.map(a => `${esc(currentVersion(state).labels.find(l => l.id === a.labelId)?.name || a.labelId)}：「${esc(a.quote)}」 · ${esc(a.holder || '归属未判定')} · ${stanceNames[a.stance || 'unclassified']}<br>态度依据（${esc(a.stanceParagraphId || x.paragraphId)}）：${esc(a.stanceQuote || '缺少依据，需复核')}`).join('<br>') || '建议不贴标签'}</p><p>${esc([...x.output.reviewReasons,x.output.abstainReason].filter(Boolean).join('；'))}</p>${d ? `<span class="pill">${esc({accepted:'已接受',modified:'修改后确认',rejected:'已拒绝'}[d.status])}</span><p>${esc(d.note || '')}</p>` : `<button type="button" class="secondary" data-apply-annotation="${x.id}" ${stale ? 'disabled' : ''}>${stale ? '规则或来源已变，请重新生成' : '载入表单审核'}</button> <button type="button" class="secondary" data-reject="${x.id}">拒绝</button>`}</article>`;
  }).join('')}${pendingAnnotation?.paragraphId === p.id ? '<p class="inline-warning">正在审核 AI 建议，可修改标签与证据，再点击下方确认保存。</p>' : ''}</div>`;
}
function ruleSuggestionsHTML() {
  return (state.suggestions || []).filter(x => x.kind === 'rule' && inQuestion(state, x)).slice().reverse().map(x => {
    const d = decisionFor(x.id), v = x.output;
    return `<article class="ai-suggestion"><b>${esc(x.paragraphId)} · 规则 v${x.versionId}</b><p>${esc(v.replacement)}</p><p class="muted">${esc(v.rationale)}</p>${d ? `<span class="pill">${esc({accepted:'已接受',modified:'修改后发布',rejected:'已拒绝'}[d.status])}</span>` : `<button class="secondary" data-apply-rule="${x.id}" ${suggestionStale(x) ? 'disabled' : ''}>载入规则编辑器</button> <button class="secondary" data-reject="${x.id}">拒绝</button>`}</article>`;
  }).join('') || '<p class="muted">先保存人工纠正和备注，再在标注页请求规则建议。</p>';
}
function bindAI() {
  async function generate(kind) {
    if (!canLeave()) return;
    try {
      const contextIds = ($('#extra-context')?.value || '').split(/[,，\s]+/).filter(Boolean);
      const request = {revision,questionId:activeQuestion(state),paragraphId:selected,kind,contextIds,requestId:crypto.randomUUID()};
      const preview = await api('/api/preview',request);
      const dialog = document.createElement('dialog');
      dialog.innerHTML = `<h2>确认发送给模型的内容</h2><p>${preview.inputChars} / ${preview.limit} 字符。确认后调用模型；取消不会产生模型请求。</p><pre style="white-space:pre-wrap;max-height:55vh;overflow:auto">${esc(`研究问题：${preview.payload.researchQuestion}\n来源记录：${preview.payload.sourceMetadata ? sourceCitation({name:'',source:preview.payload.sourceMetadata}) : '未记录'}\n研究对象：${preview.payload.researchScope?.subject || "未明确"}\n时间范围：${preview.payload.researchScope?.timeframe || "未明确"}\n\n当前段落 ${preview.payload.paragraph.id}\n${preview.payload.paragraph.text}\n\n补充及相邻上下文\n${preview.payload.context.map(p=>`${p.id}：${p.text}`).join("\n\n") || "无"}\n\n标签规则 v${preview.payload.codebookVersion.id}\n${preview.payload.codebookVersion.labels.map(l=>`${l.name}：${l.definition}\n纳入：${l.include}\n排除：${l.exclude}`).join("\n\n")}`)}</pre><details><summary>完整请求内容（含纠正记录）</summary><pre style="white-space:pre-wrap;max-height:40vh;overflow:auto">${esc(JSON.stringify(preview.payload,null,2))}</pre></details><button type="button" data-cancel>取消</button><button type="button" data-send>确认发送</button>`;
      document.body.append(dialog); dialog.showModal();
      const approved = await new Promise(resolve => { dialog.querySelector('[data-cancel]').onclick=()=>resolve(false); dialog.querySelector('[data-send]').onclick=()=>resolve(true); dialog.oncancel=e=>{e.preventDefault();resolve(false);}; });
      dialog.close(); dialog.remove(); if (!approved) return;
      toast('正在请求模型，请等待；本次不会自动确认标注或修改规则。');
      adopt(await api('/api/suggest',request));
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
    if (!window.confirm('将恢复此备份的材料、规则和人工记录。当前项目仍保留在数据库历史快照中；AI 建议和审核关联不从备份导入。继续吗？')) return;
    adopt(await api('/api/restore',{revision,state:restored})); pendingAnnotation = null; pendingRule = null; selected = state.paragraphs[0]?.id; view = 'workspace'; filter = 'all'; render(); toast('人工研究记录已恢复；恢复前版本保留在数据库历史中。');
  } catch (error) { toast(error.message); } finally { e.target.value = ''; }
};

function sourceHistoryHTML(p) {
 const doc=state.documents.find(d=>d.id===p.documentId);
 const rows=(state.sourceRevisions || []).filter(r=>r.documentId===p.documentId);
 return `<button type="button" id="edit-source" class="secondary">更正来源信息</button><details><summary>来源修改记录（${rows.length}）</summary><p>导入时：${esc(sourceCitation(doc))}</p>${rows.slice().reverse().map(r=>`<article><b>来源修订 ${r.id}</b><p>${esc(r.createdAt)} · ${esc(r.reason)}</p><p>${esc(sourceCitation({...doc,source:r.source}))}</p></article>`).join('')}</details>`;
}
function editSource() {
 const p=state.paragraphs.find(p=>p.id===selected), doc=sourceDocument(state,p.documentId);
 const original=doc.source || {type:'other',author:'',year:'',url:'',locator:''};
 const requestRevision=revision;
 const dialog=document.createElement('dialog');
 dialog.innerHTML=`<form><h2>更正来源信息</h2><p>当前：${esc(sourceCitation(doc))}</p><p class="hint">保留原文、原始来源及历次更正。更正适用于该材料所有研究问题；未审核 AI 建议需重新生成。旧人工判断将进入来源待复核；重新确认前不计入汇总及证据导出。</p><label>材料类型<select name="type">${Object.entries({interview:'访谈',paper:'论文',book:'书籍',other:'其他'}).map(([k,v])=>`<option value="${k}" ${original.type===k?'selected':''}>${v}</option>`).join('')}</select></label>${[['author','作者／来源署名',300],['year','年份／日期',20],['url','来源链接',2000],['locator','本次摘录的章节／页码',300]].map(([k,label,max])=>`<label>${label}<input name="${k}" maxlength="${max}" value="${esc(original[k])}"></label>`).join('')}<label>更正原因<textarea name="reason" required maxlength="1000" rows="2"></textarea></label><p role="status" data-error></p><button type="button" data-cancel>取消</button><button type="submit">保存更正并保留历史</button></form>`;
 document.body.append(dialog);dialog.showModal();
 const close=()=>{dialog.close();dialog.remove();};
 dialog.querySelector('[data-cancel]').onclick=close;
 dialog.oncancel=e=>{e.preventDefault();close();};
 dialog.querySelector('form').onsubmit=async e=>{
   e.preventDefault(); const f=e.target;
   const source=Object.fromEntries(['type','author','year','url','locator'].map(k=>[k,f.elements[k].value.trim()]));
   try { adopt(await api('/api/source',{revision:requestRevision,documentId:doc.id,source,reason:f.elements.reason.value}));pendingAnnotation=null;pendingRule=null;close();render();toast('来源已更正，历史记录保留。'); }
   catch(error){dialog.querySelector('[data-error]').textContent=error.message;}
 };
}
