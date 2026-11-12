import test from 'node:test';
import assert from 'node:assert/strict';
import { createWorkspace, addDocument, saveReview, publishVersion, currentVersion, latestReview, reviewStatus, confirmedSummary, versionDiff } from '../web/domain.js';
const evidence = (state, id, labelId, quote) => { const start = state.paragraphs.find(p => p.id === id).text.indexOf(quote); return { labelId, quote, start, end: start + quote.length }; };
test('导入保留原文与稳定 ID，统一换行并按空行分段', () => {
  const first = createWorkspace();
  const next = addDocument(first, '访谈', '原文 A\r\n第二行\r\n\r\n原文 B');
  assert.equal(next.paragraphs[6].id, 'P007');
  assert.equal(next.paragraphs[6].text, '原文 A\n第二行');
  assert.equal(addDocument(next, '另一份', 'C').paragraphs.at(-1).id, 'P009');
  assert.equal(first.paragraphs.length, 6);
  assert.throws(() => addDocument(first,'空材料','  '));
});
test('拒绝捏造引文、错误偏移、无效标签', () => {
  const s = createWorkspace();
  assert.throws(() => saveReview(s,'P001',[{labelId:'reliability',quote:'不存在的引文',start:0,end:6}],' '));
  const a = evidence(s,'P001','reliability','晚到二十分钟');
  assert.throws(() => saveReview(s,'P001',[{...a,start:a.start+1}],''));
  assert.throws(() => saveReview(s,'P001',[{...a,labelId:'imaginary'}],''));
});
test('同段支持多标签，并按标签追溯到同一个原文 ID', () => {
  let s = createWorkspace();
  s = addDocument(s,'多标签示例','车经常晚点，而且车里特别拥挤。');
  s = saveReview(s,'P007',[evidence(s,'P007','reliability','车经常晚点'), evidence(s,'P007','comfort','车里特别拥挤')],'两个明确问题');
  assert.equal(confirmedSummary(s).filter(x => x.evidence.length).length,2);
  assert.equal(confirmedSummary(s)[0].evidence[0].paragraphId,'P007');
});
test('规则变更保留旧判断，旧标注与无标签判断都进入复核，重新确认才进汇总', () => {
  let s = createWorkspace();
  s = saveReview(s,'P001',[evidence(s,'P001','reliability','晚到二十分钟')],'');
  s = saveReview(s,'P004',[],'明确没有费用压力');
  const labels = structuredClone(currentVersion(s).labels);
  labels[0].exclude += ' 已改善的历史问题不计入当前原因。';
  s = publishVersion(s,labels,'补充时间边界');
  assert.equal(reviewStatus(s,'P001'),'stale');
  assert.equal(reviewStatus(s,'P004'),'stale');
  assert.equal(confirmedSummary(s)[0].evidence.length,0);
  assert.equal(s.reviews.length,2);
  assert.equal(s.versions[0].labels[0].exclude.includes('历史'),false);
  assert.equal(versionDiff(s.versions[0],s.versions[1]).length,1);
  s = saveReview(s,'P001',latestReview(s,'P001').annotations,'仍然适用');
  assert.equal(confirmedSummary(s)[0].evidence.length,1);
  assert.equal(s.reviews.length,3);
});
test('歧义需要说明且不进入已确认主题汇总', () => {
  const s = createWorkspace();
  assert.throws(() => saveReview(s,'P005',[],'','ambiguous'));
  const next = saveReview(s,'P005',[],'不放心含义不明确','ambiguous');
  assert.equal(reviewStatus(next,'P005'),'ambiguous');
  assert.ok(confirmedSummary(next).every(x => !x.evidence.length));
});
test('重复保存使用最新决定计数，历史仍然保留', () => {
  let s = createWorkspace();
  s = saveReview(s,'P001',[evidence(s,'P001','reliability','晚到二十分钟')],'');
  s = saveReview(s,'P001',[evidence(s,'P001','reliability','晚到二十分钟')],'再次复核');
  assert.equal(confirmedSummary(s)[0].evidence.length,1);
  s = saveReview(s,'P001',[],'取消标签');
  assert.equal(confirmedSummary(s)[0].evidence.length,0);
  assert.equal(s.reviews.length,3);
});
test('禁止空规则、重复标签和没有修改的版本', () => {
  const s = createWorkspace(), labels = currentVersion(s).labels;
  assert.throws(() => publishVersion(s,labels,'无变化'));
  assert.throws(() => publishVersion(s,[],'删除全部'));
  assert.throws(() => publishVersion(s,[labels[0],labels[0]],'重复'));
});
