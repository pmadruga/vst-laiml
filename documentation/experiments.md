# Experiments kept

Each experiment was cheap to run because of how the pipeline is built ([DESIGN.md › 1. Pipeline](/DESIGN.md), Built for experiments): one flag changes one thing, the model calls replay offline, and the new run is scored against the same golden set.

One row per hypothesis test. Sources: `documentation/stages/*.md`, `documentation/results.md`, `STRETCH.md`, `eval/attempts/2026-09-13/`, `eval/runs/exp-*`.

| Phase | Experiment | What was tried | Result | Decision | Where |
| --- | --- | --- | --- | --- | --- |
| E | Table libraries on p.51 | PyMuPDF's table finder, pymupdf4llm and Docling on the three-column main-risks table | The first two dropped the third column; Docling was correct but costs torch, a ~1 GB model and ~2.5 s per page, and cannot see the risk/opportunity icon | Coordinate parser stays; Docling deferred to the first unknown layout | STRETCH.md › Considered, not built |
| E | Broken parser, first version | Naive text order as the regression | Caught at E8 before any record was written, so it tested nothing downstream | Rebuilt so the output is well-shaped and only the golden set catches it | stages/build-report.md |
| T1 | Identify on every page | The identify prompt run on all 15 in-scope pages, prose included, compared with the 10 table risks | All 10 table risks found, plus 13 extras, 12 of them impacts, duplicates or context; at most one real prose risk missed | Tables identify; the model path is the STRETCH item for prose reports | stages/identify-all-pages.md, eval/runs/exp-identify-all |
| T4 | spaCy grounding | T4 checks on lemmas, spaCy sentences and NER instead of regex | Same verdict on all 45 first-pass records, same seeded-failure catches, sentence counting no better, about 50x slower, +190 MB | Regex stays; spaCy backend kept as a switch | stages/grounding-comparison.md, eval/runs/exp-grounding-spacy |
| T5 | Named entities | spaCy NER over each record's own text and the topical pages | 1 of 9 records gains a useful entity; codes, units and fillers mislabelled as organisations and people | Not built; trigger is the first geographic or regulatory client question | stages/entities-probe.md |
| T2 | Self-consistency vote | N samples and a majority vote when category confidence is low | Never triggered; gpt-oss reported confidence 0.8 to 1.0 on every risk | Kept in code, unexercised | stages/build-report.md |
| T5 | Carbon-taxes mitigation | Regex for the mitigation paragraph of an ESRS risk | First version took a quoted cross-reference | Anchored on the "Actions and resources" heading on its own line | results.md |
| T6 | Stricter evaluators | Grounding reads only the model's text; intent compares every field | Baseline 1.00 became 0.89; the weak model went from passing to grounding 0.11 | Kept; 2026-09-13 recordings kept unchanged in eval/attempts | results.md, stages/review-panel-2.md |
| T2 | Prompt without mitigation | Describe prompt with the mitigation instruction removed | fields 0.67; the three stated mitigations come back as none | Regression run kept | results.md |
| T2 | Weaker model | ministral 14B instead of gpt-oss 20B | grounding 0.11: eight of nine descriptions paraphrase the report's terms; one category miss | Regression run kept | results.md |
| L | Intent prompt | Question parsed into filters before SQL | 0.40 on the first prompt, 1.00 after rewriting, 0.89 under the stricter evaluator | Kept | run_record.json eval_scores rows |
| L | Two-year status view | Synthetic second year to exercise new / continuing / removed / elevated | Logic works; "removed" had used the latest year across all companies, fixed with tests | Kept; needs the 2024 report for real data | tests/test_eval_and_provenance.py |
