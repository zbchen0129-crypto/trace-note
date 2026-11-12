# Three-minute demo

Use fictional materials. Start the local server and open localhost:8767. The current development database already contains completed examples; an extracted source package starts with six fresh excerpts. No API credentials are included in the package.

## 0:00 — Research question and codebook

Open **标签与版本**. Explain that coding means assigning interpretive labels to interview evidence. Show a definition, an inclusion rule, and an exclusion rule. This demo asks why people currently stop using public transportation.

## 0:30 — Evidence-backed suggestion

Open **访谈标注**, select P001, and click **生成 AI 标注建议**. The model should produce a reliability suggestion and an exact quotation, but its output is variable; inspect it rather than promising a fixed answer. Click **载入表单审核**, optionally edit evidence, add a note, and confirm. Show that the model suggestion and the human decision remain distinct.

## 1:15 — Historical versus current reasons

Select P006. The excerpt says service improved and the current reason is an office move. Review its suggestion. If no current label applies, explicitly confirm zero labels and explain why in the note. Do not claim every model run gets this boundary right.

## 1:45 — Rule refinement

After saving a meaningful reviewer note, click **根据纠正建议规则**. Inspect its proposed replacement. On **标签与版本**, load it into the editor, review the diff, and publish only if the change is justified. Show how prior decisions move into the stale-review queue. Do not change a rule merely to make the demonstration succeed.

## 2:30 — Traceability

Confirm a relevant annotation under the current version. Open **主题汇总**, click its evidence card, and return to the source paragraph. Show that a segment count is not a population estimate.

## 3:00 — Honest engineering summary

“I built a local research workflow that keeps model proposals separate from human decisions, validates evidence, and preserves rule versions. The synthetic benchmark did not show a label-accuracy advantage over direct prompting. Independent annotation and review-time measurement are still needed.”

## Demo recovery

If AI is not configured, the manual workflow remains usable. If generation fails, show the failure and existing confirmed material; do not substitute fake output. After a rule change, old confirmed results disappear from the current summary until reviewed again—this is expected behavior.
