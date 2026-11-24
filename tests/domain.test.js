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
test('研究范围单独发布新版本，保留历史并要求重新复核', () => {
  const old = saveReview(createWorkspace(),'P001',[],'已检查');
  const scope = {subject:'受访者本人',timeframe:'当前'};
  const next = publishVersion(old,currentVersion(old).labels,'明确范围',scope);
  assert.equal(reviewStatus(next,'P001'),'stale');
  assert.equal(old.versions[0].scope,undefined);
  assert.deepEqual(currentVersion(next).scope,scope);
  assert.equal(versionDiff(old.versions[0],next.versions[1]).length,2);
  assert.throws(() => publishVersion(next,currentVersion(next).labels,'相同',scope));
  assert.throws(() => publishVersion(next,currentVersion(next).labels,'无效',{subject:'',timeframe:'当前'}));
  const labels=structuredClone(currentVersion(next).labels);labels[0].exclude+=' 测试';
  assert.deepEqual(currentVersion(publishVersion(next,labels,'改标签')).scope,scope);
});
test('反驳与旧记录不会进入支持汇总，保留独立态度证据', () => {
  let s=addDocument(createWorkspace(),'反驳示例','有研究称票价过高导致退出，但本文不支持票价是退出原因。');
  const p=s.paragraphs.at(-1);const a=evidence(s,p.id,'cost','票价过高');
  s=saveReview(s,p.id,[{...a,holder:'被引研究',stance:'opposes',stanceQuote:'但本文不支持票价是退出原因。'}],'已核对转折');
  assert.equal(confirmedSummary(s,'supports').flatMap(x=>x.evidence).length,0);
  assert.equal(confirmedSummary(s,'opposes').flatMap(x=>x.evidence).length,1);
  assert.throws(()=>saveReview(s,p.id,[{...a,holder:'作者',stance:'supports',stanceQuote:'虚构的认可'}],''));
  s=saveReview(s,'P001',[evidence(s,'P001','reliability','晚到二十分钟')],'兼容旧记录');
  assert.equal(confirmedSummary(s,'supports').flatMap(x=>x.evidence).length,0);
  assert.equal(confirmedSummary(s,'unclassified').flatMap(x=>x.evidence).length,1);
});
test('跨段态度依据保留引用且拒绝跨材料关联', () => {
 let s=addDocument(createWorkspace(),'论文摘录','有研究称票价过高。\n\n本文反对票价解释。');
 const a={...evidence(s,'P007','cost','票价过高'),holder:'被引研究',stance:'opposes',stanceQuote:'本文反对票价解释。',stanceParagraphId:'P008'};
 s=saveReview(s,'P007',[a],'核对后文');
 assert.equal(confirmedSummary(s,'opposes').find(x=>x.label.id==='cost').evidence[0].stanceParagraphId,'P008');
 assert.throws(()=>saveReview(s,'P007',[{...a,stanceParagraphId:'P001'}],''));
});

test('多个问题共享原文但隔离标注、汇总及失效范围', async () => {
  const {addQuestion,activeQuestion,questionVersions} = await import('../web/domain.js');
  let s=createWorkspace();
  s=saveReview(s,'P001',[evidence(s,'P001','reliability','公交晚到二十分钟')],'原问题');
  s=addQuestion(s,'照护责任如何影响出行？','照护责任','接送孩子等照护安排。');
  const q2=activeQuestion(s);
  assert.equal(reviewStatus(s,'P001'),'pending');
  assert.equal(confirmedSummary(s)[0].evidence.length,0);
  s=saveReview(s,'P001',[evidence(s,'P001','topic','我得接孩子')],'第二问题');
  assert.equal(confirmedSummary(s)[0].evidence[0].quote,'我得接孩子');
  const labels=structuredClone(currentVersion(s).labels); labels[0].include='明确提及照护责任';
  s=publishVersion(s,labels,'收紧定义');
  assert.equal(reviewStatus(s,'P001'),'stale');
  s.activeQuestionId='Q1';
  assert.equal(reviewStatus(s,'P001'),'confirmed');
  assert.equal(confirmedSummary(s)[0].evidence[0].quote,'公交晚到二十分钟');
  assert.equal(questionVersions(s).length,1);
  assert.equal(s.paragraphs.length,6);
  assert.equal(s.reviews.length,2);
  s.activeQuestionId=q2;
  assert.equal(questionVersions(s).length,2);
});

test('标签新增移除保留旧证据，禁止复用已退休身份', () => {
 let s=createWorkspace();
 s=saveReview(s,'P001',[evidence(s,'P001','reliability','公交晚到二十分钟')],'旧证据');
 const original=structuredClone(currentVersion(s).labels[0]);
 const added={id:'care-new',name:'照护责任',definition:'接送孩子',include:'明确照护安排',exclude:'无关描述'};
 const before=currentVersion(s);
 s=publishVersion(s,[...before.labels.slice(1),added],'以照护维度补充研究');
 assert.equal(reviewStatus(s,'P001'),'stale');
 assert.equal(s.reviews[0].annotations[0].labelId,'reliability');
 assert.equal(s.versions[0].labels[0].name,'可靠性问题');
 assert.ok(versionDiff(before,currentVersion(s)).some(d=>d.name==='照护责任' && d.field==='definition' && d.after==='接送孩子'));
 assert.throws(()=>publishVersion(s,[...currentVersion(s).labels,original],'复用旧身份'),/身份/);
 const renamed=structuredClone(currentVersion(s).labels);renamed.at(-1).name='家庭照护';
 s=publishVersion(s,renamed,'改名');
 assert.equal(currentVersion(s).labels.at(-1).id,'care-new');
 assert.throws(()=>publishVersion(s,[],'全部移除'));
 assert.throws(()=>publishVersion(s,Array.from({length:9},(_,i)=>({...added,id:`l${i}`,name:`n${i}`})),'过量'),/1–8/);
});

test('材料来源随导入保存，不把摘录范围伪装成逐段页码', async () => {
 const {sourceCitation}=await import('../web/domain.js');
 const source={type:'book',author:'示例作者',year:'2026',url:'https://example.org/book',locator:'第 3 章，印刷页 42–44'};
 let s=addDocument(createWorkspace(),'书籍摘录','第一段\n\n第二段',source);
 assert.deepEqual(s.documents.at(-1).source,source);
 assert.equal(s.paragraphs.at(-1).locator,undefined);
 assert.match(sourceCitation(s.documents.at(-1)),/摘录范围：第 3 章/);
 source.author='外部修改'; assert.equal(s.documents.at(-1).source.author,'示例作者');
 assert.match(sourceCitation(createWorkspace().documents[0]),/来源未记录/);
 assert.throws(()=>addDocument(s,'恶意链接','正文',{...source,url:'javascript:alert(1)'}));
 assert.throws(()=>addDocument(s,'凭据链接','正文',{...source,url:'https://user:secret@example.org'}));
});

test('来源更正解析最新记录而不修改导入来源', async () => {
 const {sourceDocument,sourceRevision,sourceCitation}=await import('../web/domain.js');
 const s=createWorkspace(); const original=structuredClone(s.documents[0]);
 s.sourceRevisions=[{id:1,documentId:original.id,source:{type:'paper',author:'更正作者',year:'2026',url:'',locator:'第 4 页'}}];
 assert.equal(sourceRevision(s,original.id),1);
 assert.match(sourceCitation(sourceDocument(s,original.id)),/更正作者/);
 assert.deepEqual(s.documents[0],original);
 assert.equal(sourceRevision(s,'missing'),0);
});

test('来源变更跨问题进入复核，重新确认才可导出，保留跨段依据', async () => {
 const {addQuestion,evidenceReport}=await import('../web/domain.js');
 let s=addDocument(createWorkspace(),'论文','有研究称票价过高。\n\n本文反对票价解释。');
 const a={...evidence(s,'P007','cost','票价过高'),holder:'被引研究',stance:'opposes',stanceQuote:'本文反对票价解释。',stanceParagraphId:'P008'};
 s=saveReview(s,'P007',[a],'核对反驳');
 s=saveReview(s,'P001',[],'其他材料');
 s=addQuestion(s,'另一个问题','主题','定义'); const q2=s.activeQuestionId;
 s=saveReview(s,'P007',[],'另一问题判断');
 s.sourceRevisions=[{id:1,documentId:s.paragraphs[6].documentId,source:{type:'paper',author:'作者',year:'2026',url:'',locator:'第 5 页'}}];
 assert.equal(reviewStatus(s,'P007'),'source-stale');
 s.activeQuestionId='Q1';assert.equal(reviewStatus(s,'P007'),'source-stale');
 assert.equal(reviewStatus(s,'P001'),'confirmed');
 assert.equal(evidenceReport(s,'opposes').evidence.length,0);
 s=saveReview(s,'P007',[a],'已核对出处');
 const report=evidenceReport(s,'opposes');
 assert.equal(report.evidence.length,1);
 assert.equal(report.evidence[0].review.sourceRevision,1);
 assert.equal(report.evidence[0].stanceParagraphText,'本文反对票价解释。');
 assert.equal(report.documents[0].source.locator,'第 5 页');
 assert.equal(report.question.id,'Q1');
 assert.equal(evidenceReport(s,'supports').evidence.length,0);
 assert.equal(s.reviews[0].sourceRevision,0);
 s.activeQuestionId=q2;assert.equal(reviewStatus(s,'P007'),'source-stale');
});
test('旧记录缺少来源版本按初始版本处理；导出限制总量', async () => {
 const {evidenceReport}=await import('../web/domain.js');
 let s=saveReview(createWorkspace(),'P001',[evidence(createWorkspace(),'P001','reliability','晚到二十分钟')],'');
 delete s.reviews[0].sourceRevision;
 assert.equal(evidenceReport(s,'unclassified').evidence.length,1);
 s.paragraphs[0].text+='x'.repeat(510000);
 assert.throws(()=>evidenceReport(s,'unclassified'),/超过/);
});
