// One public-domain excerpt; no network, model, or user database access.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createWorkspace,addDocument,addQuestion,activeQuestion,saveReview,reviewStatus,evidenceReport} from '../web/domain.js';
const [stage,dir]=process.argv.slice(2);
function read(path) {assert.ok(fs.statSync(path).size<=128000);return JSON.parse(fs.readFileSync(path,'utf8'));}
function write(name,value) {const text=JSON.stringify(value,null,2);assert.ok(text.length<1000000);fs.writeFileSync(`${dir}/${name}.json`,text);}
const source=read(new URL('./real-source.json',import.meta.url));
assert.equal(createHash('sha256').update(source.text).digest('hex'),source.sha256);
if(stage==='prepare') {
 let s=addDocument(createWorkspace(),source.title,source.text,{type:'book',author:source.author,year:source.year,url:source.sourceUrl,locator:'Chapter VI — eye passage'});
 s=addQuestion(s,'作者是否将眼睛的复杂性视为否定自然选择的理由？','复杂性反对意见','判断作者是否认可“眼睛复杂，因此不能由自然选择形成”的观点。');
 const q1=activeQuestion(s),p=s.paragraphs.at(-1);
 write('base',s);
 const quote='absurd in the highest possible degree',start=p.text.indexOf(quote);
 const stanceQuote='Yet reason tells me'+p.text.split('Yet reason tells me')[1];
 s=saveReview(s,p.id,[{labelId:'topic',quote,start,end:start+quote.length,holder:'Charles Darwin（先让步，后回应）',stance:'opposes',stanceQuote}], '开发助手演示判断：转折后的条件论证回应了开头困难；不是独立研究者标注。');
 assert.equal(evidenceReport(s,'supports').evidence.length,0);
 assert.equal(evidenceReport(s,'opposes').evidence.length,1);
 s=addQuestion(s,'作者是否以有用的渐变作为回应困难的条件？','有用渐变条件','区分条件论证与无条件的实证结论。');
 const q2=activeQuestion(s),q='each grade being useful to its possessor',a=p.text.indexOf(q);
 s=saveReview(s,p.id,[{labelId:'topic',quote:q,start:a,end:a+q.length,holder:'Charles Darwin',stance:'supports',stanceQuote}], '支持的是作者提出了这一论证条件，不声称这些条件已由本摘录全部证明。');
 assert.equal(evidenceReport(s,'supports').question.id,q2);
 write('reviewed',s);write('ids',{q1,q2,paragraphId:p.id,documentId:p.documentId});
} else {
 let s=read(`${dir}/corrected.json`),ids=read(`${dir}/ids.json`);
 for(const q of [ids.q1,ids.q2]) {s.activeQuestionId=q;assert.equal(reviewStatus(s,ids.paragraphId),'source-stale');assert.equal(evidenceReport(s,'supports').evidence.length,0);assert.equal(evidenceReport(s,'opposes').evidence.length,0);}
 s.activeQuestionId=ids.q1;
 const prior=s.reviews.find(r=>r.versionId===s.versions.find(v=>v.questionId===ids.q1).id);
 s=saveReview(s,ids.paragraphId,prior.annotations,'重新核对版本、章节和出处；保留原判断。');
 const report=evidenceReport(s,'opposes');assert.equal(report.evidence.length,1);assert.equal(report.evidence[0].review.sourceRevision,1);
 assert.equal(report.documents[0].fictional,false);assert.equal(report.evidence[0].paragraphText,source.text);
 write('evidence',report);write('reconfirmed',s);
 s.activeQuestionId=ids.q2;assert.equal(reviewStatus(s,ids.paragraphId),'source-stale');
}
const rss=process.resourceUsage().maxRSS/1024;
assert.ok(rss<256,'Memory budget exceeded; no retry');
console.log(JSON.stringify({stage,peakRssMiB:rss}));
