# Multi-paragraph follow-up findings

Four fictional interviews contain 444–482 Chinese characters each, with four paragraphs per interview. Eight middle paragraphs were scored, using only the preceding and following paragraphs as context, matching the application's context window. These are expanded multi-paragraph fixtures, **not full-length interview transcripts**. Two scored paragraphs from the same interview are correlated.

Both arms matched all eight assistant-authored reference label sets. The direct arm passed the application's structural/evidence validator in 7/8 cases; the workbench arm passed in 8/8. This is one sample per case, not a stable comparative performance estimate.

## Observed rejection: I02-P3 / direct

The direct response emitted `reliability` once and `transfer` twice, with different quotations. Its label set was correct, and all quotations were literal substrings. The application permits one evidence span per label, so it rejected the duplicate `transfer` entry. This is a data-contract violation, not a label-accuracy error or fabricated quotation. A future product could legitimately support multiple evidence spans per label; its validator and tests would then need to change together.

The scorer retains raw labels even for rejected suggestions. That is why F1 remains 1.0 while acceptance coverage is 87.5%. This separation prevents rejection-based filtering from artificially improving the reported label metrics.

No cost-label positives occur in this follow-up. Its undefined per-label F1 is reported as null and excluded from macro F1; refer to `report.json` for support counts. The earlier synthetic set includes cost-label positives.

## What remains unmeasured

Full-length interviews with evidence beyond adjacent context; independent human judgments of semantic evidence support; inter-researcher disagreement; review time; repeated-run stability. These fixtures and references remain assistant-authored and are not an independent held-out human benchmark.
