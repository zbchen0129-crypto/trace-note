# TraceNote

An evidence-linked qualitative research workbench with AI coding suggestions, human review, and versioned codebooks.

TraceNote helps researchers examine interview, paper and book excerpts, define coding boundaries, review model suggestions, and trace a theme back to the original text. The working demo uses fictional interviews about leaving public transportation.

[中文说明](README.zh-CN.md) · [Architecture](docs/architecture.md) · [Demo walkthrough](docs/demo.md) · [Evaluation protocol](eval/README.md)

![TraceNote workbench with a reviewed AI suggestion](docs/images/workbench.png)

## What works

- Import TXT or pasted text; preserve paragraphs and stable source IDs.
- Assign multiple labels with exact source quotations and character offsets.
- Review viewpoint attribution and author/speaker stance; keep supporting, opposing, mentioned, unclear and legacy evidence in separate summary groups.
- Generate structured AI suggestions through a server-side OpenAI Responses adapter.
- Accept, modify, or reject suggestions; unreviewed suggestions do not enter confirmed summaries.
- Propose codebook changes from reviewer notes, inspect a diff, and explicitly publish a new version.
- Queue older decisions for review after a rule change; preserve previous decisions and versions.
- Define the research subject and time scope in a codebook version; preview and publish changes before they affect model requests.
- Store project snapshots in SQLite with revision conflict protection.
- Export JSON; restore the manual research records while retaining the pre-restore database snapshot.

This is a local, single-user prototype. The UI is primarily Chinese. The initial question has four editable labels. Up to 20 research questions can share the corpus, with separate rules, annotations, suggestions and summaries. New questions start with one user-defined label; the version editor supports adding, renaming and removing labels, with 1–8 active labels per question.

## Run locally

Requires Python 3.10+. The server uses the standard library; no Python packages or frontend build are required.

```sh
python3 server.py
```

Open **http://localhost:8767/**. Run from the extracted repository directory. The server binds to loopback only. Do not start it with a static HTTP server: the UI requires its API.

On first use, an empty database imports the current browser's legacy TraceNote project if available; otherwise it starts with the fictional demo. Data is stored in `data/tracenote.sqlite3`, which is excluded from the source package.

### Optional model configuration

Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY` and `TRACENOTE_MODEL` locally. Use a model available to your account that supports Responses structured outputs. Restart the server after configuration changes.

Manual coding works without credentials. Model buttons remain disabled until both values are set. Clicking Generate sends the current paragraph, adjacent context, and codebook to OpenAI. Rule suggestions additionally use the relevant reviewer note and prior suggestion. Requests set `store: false`; credentials remain server-side and are not included in database snapshots or exports.

## Tests

Requires Node.js 18+ for the frontend domain tests.

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/domain.test.js
```

The current suite contains 58 Python tests and 16 JavaScript tests. It covers source evidence validation, Unicode offsets, immutable history, stale versions, conflicting writes, suggestion decisions, HTTP boundaries, and evaluation scoring. Backend tests inject a clearly named fake model; there is no production fake-model mode.

## Evaluation and evidence

The first benchmark used **16 assistant-authored synthetic cases**, with one response per case and arm. Direct prompting and the workbench prompt both matched all reference label sets; each arm's 14 quotations passed exact-source and unique-location checks. **No accuracy advantage was observed.**

- [Original results, including raw inputs and outputs](eval/results/synthetic-v1/report.md)
- [Multi-paragraph follow-up](eval/results/context-v2/report.md) and [interpretation](eval/context-findings.md)
- [Methodology and independent-review plan](eval/README.md)

These are development benchmarks, not independent human gold labels or evidence of real-world accuracy. Exact quotation matching does not establish semantic support. Researcher agreement, human review time, and generalization to real interviews have not been measured. Results from repeated paragraphs in one interview must not be treated as statistically independent.

A real browser walkthrough has verified model generation, acceptance, edited acceptance, codebook suggestion publication, stale-review queuing, and summary-to-source navigation. The displayed screenshot contains fictional demo material and development-review decisions.

## Engineering decisions

The domain logic is separate from the UI. Server-side validation rejects unknown labels, invalid source offsets, and fabricated or non-unique model quotations. A model response remains attached to the codebook version used for its request. Review decisions are appended rather than silently overwriting history.

SQLite stores complete JSON snapshots for transparent history and simple conflict handling. This trades storage efficiency for implementation simplicity and is not a large-corpus design. Model calls are synchronous with a 60-second timeout; persisted task states and request IDs prevent simple duplicate submissions. Failed paid calls are not automatically retried.

See [architecture and known limits](docs/architecture.md) for details.

## Repository map

```text
backend/        validation, SQLite, model adapter, suggestion lifecycle
web/            browser UI and standalone domain logic
server.py       local HTTP API and static assets
tests/            backend, HTTP, scoring and browser-domain tests
eval/           frozen synthetic cases, runners and recorded results
docs/           architecture, demo and product plan
scripts/        curated source-package builder
```

## Next work

Independent blind annotation and adjudication; full-length interview evaluation; controlled review-time study; stronger project recovery and corpus management; a separately designed public demo with authentication and usage limits. The source is maintained in the public GitHub repository `zbchen0129-crypto/trace-note`. There is no public hosted deployment.

## Design evolution

[Decision history and interview narrative](docs/design-decisions.md) records user questions, failures, design tradeoffs, measured results, and unfinished plans. [Stance regression protocol](eval/README.md) explains the four-case check; it is not an independent accuracy benchmark.

Cross-paragraph evidence: select up to four extra paragraphs from the same document, preview the request before sending, and link a stance quotation to its source paragraph. Requests are capped at 40,000 serialized payload characters. Suggestions retain the request snapshot. Four sequential live calls on two synthetic paired cases matched stance/source references (33.94 MiB peak RSS), with inconsistent missing-context warnings. This is not real-world accuracy evidence; see eval/results/cross-context-v1 and eval/README.md.

Multiple questions: use “新增研究问题” to provide a question and initial label. Switching questions changes review progress, codebook history and evidence summaries without copying source text. Existing records belong to the original transport question. A rule update invalidates only reviews for its own question. Question wording is immutable; create another question when its meaning changes.

Label changes are drafts until previewed and published. Removal can be undone within the draft and does not delete historical evidence. Renaming retains identity; a published, removed label ID cannot be reused. A later new label—even with a similar name—requires fresh review. The preview includes definitions and inclusion/exclusion rules for added/removed labels.


Source metadata: TXT/paste imports can be typed as interview, paper, book or other, with optional author, date/year, HTTP(S) URL and excerpt-level chapter/page range. These records appear beside source text and confirmed evidence and survive backup restore; model request snapshots include them. Metadata is researcher-supplied, not verified. Ranges apply to the whole imported excerpt, not individual paragraphs. Source corrections are available with an append-only history; PDF extraction, OCR and URL fetching are not implemented.

Use “更正来源信息” beside source text to correct metadata with a required reason. Original metadata and earlier corrections remain available. Current citations use the latest correction; Historical human classifications are retained, but any source correction marks earlier reviews as source-stale across all questions sharing that document. They are excluded from summaries until reconfirmed. Unreviewed AI suggestions based on earlier source revisions cannot be accepted.

Evidence export: “导出当前分组证据 JSON” exports only the active question and selected stance under current codebook/source revisions. The report includes original paragraph text, quotations, UTF-16 offsets, cross-paragraph stance evidence, source metadata and human review references. It is not a project backup. Export is capped at 5,000 evidence rows and approximately 1,000,000 serialized characters; no model call is made. Legacy reviews without a source revision are treated as revision 0.

A [real public-domain book walkthrough](docs/real-material-walkthrough.md) now demonstrates two questions, concession versus final stance, source correction, selective reconfirmation and evidence export. Its reproducible offline acceptance run uses isolated SQLite and no model calls; it does not measure model accuracy.

Generic stance labels now read “支持该观点 / 反对该观点”; stored stance IDs and transport demo content remain unchanged. A [real-paper attribution walkthrough](docs/paper-attribution-walkthrough.md) separates a cited author's claim from the paper authors' sample-bound response. Offline checks validate record keeping, not automated semantic accuracy.

A reference-blind pilot packet is ready for two independent human reviewers: `python3 eval/blind_review.py build`. It contains three tasks on two existing real sources and excludes developer references/model outputs. No human submissions have been collected. The [coordinator protocol](eval/review-coordinator/README.md) explains independent collection, validation and disagreement review; send only the reviewer ZIP, not the source repository.
