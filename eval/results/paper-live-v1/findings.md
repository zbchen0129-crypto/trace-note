# Real-paper context check — 2026-11-24

Two sequential calls completed with the configured `gpt-5.6-terra` model, using the production adapter. No prompt or fixture changes were made between calls. Peak process RSS was 34.05 MiB under a 256 MiB checkpoint budget; zero retries. Payloads contained 1,102 and 1,636 serialized characters respectively. Actual request payloads and raw model outputs are preserved beside the frozen manifest and report.

| View | Observed stance | Stance evidence | Attribution |
|---|---|---|---|
| Cited sentence only | unclear | Empty quotation; P007 | Priem & Costello (2010) |
| Same sentence plus paper authors' results | opposes | Full supplied results excerpt, P008 | Priem & Costello (2010) |

Both outputs passed the production structure and literal-evidence validator. The incomplete view explicitly explained that the paper authors' evaluation was absent; it did not treat a cited claim as their endorsement. With the results paragraph, the output retained the cited authors as the claim holder and used the paper authors' results as the opposition evidence. The selected evidence includes the minority exception, rather than clipping the passage to an absolute claim that no tweets ever reflect engagement.

Developer inspection: attribution and evidence-source selection match the reference for this narrow question. The output gives no independent explanation of its second judgment beyond the selected excerpt, so this should not be described as comprehensive reasoning verification. The reference interpretation concerns the studied dentistry-paper tweet sample; it does not establish that Twitter never supports conversation or independently adjudicate the cited study.

Limitations: one paper, one sample per view, non-contiguous excerpts selected by the developer, and assistant-authored reference interpretations. Citation attribution is explicitly supplied in the locator and research scope in both views. This tests response to available author-evaluation context, not recovery of an unidentified speaker. The scope and codebook also supply interpretive framing. No blinded human study, review-time measurement, statistical accuracy estimate, or comparison against a prior prompt was conducted.

These are direct adapter evaluation calls, not saved reviews in the user's application database. Automatic validation establishes source/format consistency, not semantic truth. Do not report this as “100% accuracy.”

Reproduce from cached results: `python3 eval/paper_live.py` (same configured model identity and frozen files). `--live` permits at most the two missing calls; existing completed, failed, or interrupted records are not overwritten or retried. Changed inputs require a separately designed run, not deletion of this directory.
