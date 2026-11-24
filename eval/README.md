# Evaluation protocol

本目录是 **开发用合成基准**，不是独立人工标注集，也不是泛化性能证明。案例与参考标签由开发助手编写，存在设计偏差，公开后不再属于隐藏测试集。没有把原有 P001–P008 演示文本复制进新案例；但主题和边界由同一开发过程设计，因此不声称统计独立。

## Frozen inputs

- `codebook.json`：从本地项目复制的 v3 规则快照，评估时不读取活动项目规则。
- `cases.json`：16 份不同虚构访谈摘录，每个 interviewId 只有一个段落；预期标签及理由在模型运行前写定。
- `human-review-template.json`：不含参考标签和模型输出的人工标注模板。
- `run.py`：逐例运行 direct/workbench 两组，交替执行顺序，默认最多 32 次新请求。
- `results/synthetic-v1/`：冻结输入哈希、每次实际输入与输出及汇总报告。不含凭据和私人数据。

两组相同模型、材料、规则、上下文、结构化输出约束及输出 token 上限。direct 使用简短直接提示；workbench 使用实际产品提示。评估期间不调提示或规则，不根据模型输出更改参考标签。单次采样，没有盲测参与者，没有人工审核耗时数据。

## Run

在项目根目录运行：

```sh
python3 eval/run.py --live --max-calls 32
```

这会使用本地 .env 中的模型并产生 API 费用，不自动重试。相同输入的已保存结果会被复用；模型、代码、参考集或规则变化时必须指定新的 `--output eval/results/新的名称`。请求失败后停止，不假装成功；失败缓存留在记录中，不静默删除重跑。

只用已保存结果重建报告：

```sh
python3 eval/run.py
```

## Interpretation

F1 统计模型原始标签，不因引用校验失败而删除该案例。模型返回失败作为空预测计算漏标，段落完全匹配计失败；同时单独报告失败数、校验通过率、无标签样本准确率、引文原文匹配和唯一定位率。合法引文不等于支持该标签，语义支持需要独立人工复核。

## Independent human study — not yet conducted

1. 由至少两位参与者独立阅读同一份冻结 codebook，用各自模板标注，不先看助手参考标签或模型输出。
2. 每条记录填写标签、连续原文证据、歧义及理由；允许空标签，也允许保留分歧。
3. 记录原始独立标注，再讨论边界并形成评估参考；不能覆盖原始分歧。必要时修改规则，但修改后需要新的保留访谈。
4. 建立真实或经授权的访谈集合，按完整访谈划分开发/保留集合，避免段落级泄漏。
5. 计时比较人工操作、直接提示、工作台辅助：使用等难度材料并交叉平衡顺序，避免同一人先读过材料产生学习优势；同时记录最终质量，不能只比较时间。
6. 报告样本量、参与者背景、分歧、每类错误与不确定性。小样本不写显著性或普遍提效结论。

当前无需用户填表才能继续工程准备；独立研究者结论和人工耗时必须等真实参与后才能报告。

## 第二轮：多段上下文案例

`context-interviews.json` 保存 4 份各 444–482 字的虚构访谈，每份四段；`context-cases.json` 选取其中 8 个中间段落，输入前后相邻段落。同一访谈的两条记录不独立，不按 8 份访谈计算。参考标签在请求前固定，不依据结果修改。它们仍不是完整长访谈或人工金标准。

当前 `run.py` 默认运行第二轮，最多需要 16 次新请求：

```sh
python3 eval/run.py --live --max-calls 16
```

不调用模型、只复用缓存：`python3 eval/run.py`。

首轮脚本已原样冻结为 `run_v1.py`，以保留与首轮 manifest 中相同的脚本哈希。复现旧报告使用 `python3 eval/run_v1.py`；前面的首轮命令请将 run.py 替换为 run_v1.py。

新评分脚本额外计入未知标签误报，并有相应测试。两轮案例、脚本和报告分别保存，不覆盖首轮结果。[第二轮解读](context-findings.md)解释了重复标签拦截及其与准确率的区别。

## Long-distance context stress test (2026-11-16)

`long-cases.json` contains four assistant-authored Chinese stress fixtures, each about 2,650 characters. Repeated neutral background separates a target from decisive temporal or speaker information by 24 paragraph positions. These are controlled distance tests, not natural full-length interview transcripts. L01/L02 share identical target and adjacent context but differ in remote temporal framing; L03 checks speaker attribution; L04 is an explicit current-cost control.

`python3 eval/long_context.py` performs preflight and reports cached/pending cases without model calls. `python3 eval/long_context.py --live --max-calls 8` runs at most eight new calls, sequentially, alternating context-arm order. Both arms use the same workbench prompt, model, codebook and output schema. Only context scope changes: adjacent paragraphs versus all paragraphs within a hard character budget. Neither reference labels nor decisive-context metadata is sent. Production still uses adjacent context; this is an experiment, not an automatic context expansion.

References depend on visible evidence. For ambiguous L01/L02 adjacent views, an empty label set plus a review/abstention signal is the intended conservative response. A full-context answer is not used to score a model that did not receive that context. Review signals are checked for presence only, not semantic quality. Label matching and validator acceptance are separate. Inspect saved outputs before interpreting matches; no significance or generalization claim is supported by four fixtures.

Resource bounds: 512,000 bytes per fixture/cache file, at most eight cases, 32,000 serialized input characters, one synchronous request at a time, 2,500 output-token budget and existing 2 MB HTTP-response read limit. Peak process RSS is checked before/after calls against 256 MiB. This is a checkpoint-based stop, not an OS-enforced allocation ceiling or a bound on total machine memory. Oversized context is rejected instead of silently truncated. A failed request stops the run without retry, and manifests prevent mixing changed inputs with earlier caches.

### Recorded first run

Eight sequential live calls completed using the configured model. Peak process RSS was 33.97 MiB. All eight outputs passed source/structure validation. Against the predefined, view-specific development references, adjacent context matched 2/4 and bounded full context matched 3/4. These tiny, partly paired stress cases do not estimate an accuracy uplift.

- L01/L02: identical adjacent inputs both received a reliability label without uncertainty. The conservative reference expected review because “那阵子” is temporally unresolved. With remote framing, the historical case was excluded and the current case retained. L02's adjacent label happens to match the full-interview label, but it did not recognize the missing temporal information.
- L03: both views labeled a transfer burden. The full-context reference excludes the colleague's experience from the interviewee's own reasons. The application research question does not explicitly name whose reasons count, so this is also a specification gap, not clean evidence of a model-only attribution failure. Next work should make the subject and time scope explicit, then retain these cases as regression fixtures.
- L04: both views correctly retained the explicit current cost reason.

The UI now explains the actual reading scope and directs reviewers to verify remote time/person references or mark ambiguity. No automatic full-interview expansion was enabled. Before changing production context selection, add explicit subject/time scope and a reviewer-selected context preview; measure the added scope using a fresh output directory and preserve this first run.

### Explicit-scope regression

Run `python3 eval/long_context.py --scope --live --max-calls 8 --output eval/results/long-context-scope-v2` only for a new live evaluation; omit `--live` to replay its cache. The `--scope` option adds the same proposed interviewee/current-time settings available in the version editor. Both input metadata and scope-specific instructions change relative to v1; this is a regression check, not a controlled attribution of improvement to one prompt component. Cases and references are unchanged, and were used during development rather than held out.

The recorded run completed eight sequential calls with a 34.30 MiB peak process RSS. All eight passed structural/source validation. Full-context references matched 4/4 (previously 3/4); the L03 response explicitly excluded the colleague's experience. Adjacent references remained 2/4: both temporal cases still received a reliability label without a review signal. L02 happens to have the correct eventual full-context label, but fails the conservative uncertainty policy for its incomplete view. Do not report these values as real-world accuracy or stable improvement.

Validation also includes 25 Python tests, 8 JavaScript tests, and an isolated-database browser walkthrough of scope preview, publication, persistence and stale-review queuing. No production project scope was changed by that walkthrough. The next unresolved product need is reviewer-selected additional context with a preview and explicit input limits; scope settings alone cannot recover unseen evidence.

## Viewpoint/stance regression (2026-11-19)

`python3 eval/stance_run.py` reuses recorded results; `--live` allows at most four sequential calls when caches are missing. Fixture/cache reads are capped at 512 KB and input at 32,000 serialized characters, with the existing response bound and 256 MiB peak-RSS checkpoints. No automatic retries. Manifests prevent mixing changed inputs/implementations.

Four assistant-authored, short cases use a test-specific living-standard label and distinguish explicit support, explicit rebuttal, neutral citation and uncertainty. All four recorded calls matched their intended stance and passed quote validation; peak evaluation-process RSS was 33.78 MiB. This does not assess natural academic articles, multi-source disagreements, irony, cross-paragraph rebuttals or independent human agreement. The test-specific label is not a newly implemented UI label-creation feature.

Unlike earlier label-only experiments, the task now retains candidate explanations that are opposed or merely mentioned. Therefore do not compare earlier label-set scores with new candidate labels as though the target definition were unchanged. Inspect attribution and full stance evidence in per-case files; automatic matching checks stance enum only, not whether the holder or rationale is semantically correct.


## Cross-paragraph paired check (2026-11-19)

`python3 eval/cross_context.py` replays the frozen cache; `--live` permits at most four missing calls, sequentially. Two assistant-authored cases share identical target/adjacent text, but have opposite remote conclusions. Both arms keep the same prompt and test-specific label; only the remote P004 context changes. References were fixed before calls: adjacent allows mentions/unclear, while extra requires the appropriate supports/opposes stance and P004 source. Quote validity is checked separately. Holder correctness is not automatically scored.

Limits: 8,000 serialized input characters, four calls, 2,500 output tokens, existing 2 MB response read limit, 512 KB cache reads and 256 MiB peak-RSS checks before/after calls. Checkpoints are not a hard OS memory limit. No retries or local model. Changed manifests reject cache mixing.

Recorded results in `results/cross-context-v1/`: all four passed structural/quote checks and their view-specific stance/source references. Adjacent outputs were both mentions; extra outputs were opposes and supports respectively, both citing P004. Peak evaluation-process RSS: 33.94 MiB. Manual inspection found holder=甲研究 throughout, consistent with the attributed initial claim; stance separately describes the current author's treatment.

The identical adjacent inputs differed in uncertainty signaling: rebuttal-adjacent supplied neither reviewReasons nor abstainReason, whereas endorsement-adjacent explicitly stated the missing later evaluation in both. Both meet the permissive mentions reference, so 4/4 does **not** mean stable uncertainty handling. Current summaries group both as mentions; reviewers must still inspect missing context. Tiny synthetic examples, one sample each, no independent annotators or real academic corpus; no general accuracy claim. This script exercises the adapter, not the production service/UI, whose linkage/preview behavior is tested separately.

## Real-source offline workflow acceptance (2026-11-23)

`real-source.json` preserves two consecutive sentences from Darwin's 1860 public-domain book with provenance and a text hash. `python3 eval/real_workflow.py --node /path/to/node` runs the actual JS domain workflow and Python persistence/source service sequentially in a temporary database. It checks two-question isolation, stance filtering, source-change invalidation, selective reconfirmation, evidence export and backup restore. Outputs are regenerated in `results/real-workflow-v1/`; they are development workflow artifacts, not frozen model results. No model calls or credentials are used. Interpretations are assistant-authored, not independent annotations. See [walkthrough](../docs/real-material-walkthrough.md) for scope, limits and measured memory.

## Real-paper attribution fixture (2026-11-23)

`paper-attribution.json` records two non-contiguous excerpts from Robinson-Garcia et al. (2017), with locators, hashes, attribution and assistant-authored references. `node eval/paper_attribution.js` checks quotation-only versus author-response review states using actual domain/export functions, without models or user data. Outputs in `results/paper-attribution-v1/` are regenerable development artifacts, not model measurements. See [interpretation and limits](../docs/paper-attribution-walkthrough.md). The generic viewpoint prompt changed in this iteration; earlier live caches remain historical and must not be presented as validation of the new prompt.

## Two live calls on the real-paper fixture (2026-11-24)

`paper_live.py` freezes payloads and code hashes before transmission and allows at most two sequential calls. It persists an in-flight marker before each request; failed/interrupted records stop execution without retry. `python3 eval/paper_live.py` reads existing results without new requests. The completed run returned `unclear` for the citation-only view and `opposes` with P008 evidence when author results were provided. Both retained Priem & Costello as the claim holder. Peak RSS was 34.05 MiB. See [results and limitations](results/paper-live-v1/findings.md). Explicit attribution was supplied in both views; this is not an independent accuracy estimate or a speaker-discovery test.

## Reference-blind reviewer packet (2026-11-24)

`python3 eval/blind_review.py build` creates `artifacts/review/tracenote-blind-review-v1.zip` containing instructions, source materials/questions and a blank response template only. Three tasks share two real sources; no new model calls are made. `validate response.json` checks completeness and literal source evidence; `compare a.json b.json` preserves both interpretations without adjudicating truth. See [coordinator protocol](review-coordinator/README.md), which must not be included when sending the reviewer archive. There are currently zero real submissions; unit-test answers are not research data. This is a small reference-blind pilot, not an independent accuracy benchmark or a double-blind study.
