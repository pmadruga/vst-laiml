# CLAUDE.md: working rules for this repository

Deliverables are PLAN.md (½-page product plan, one section per question in the brief), DESIGN.md, STRETCH.md and README. SPECS.md holds the per-step specification (what, how, example) behind DESIGN.md › 1. Pipeline; step numbers E/T/L are shared. The brief and the source report are in `documentation/baseline/`; Pedro's own notes are in `documentation/self/`. Stage reports go to `documentation/stages/`.

## Rules

- **Current stage: 0**: only Pedro edits this line. Work only on the current stage; do not start the next one.
- Every substantive implementation choice cites a PLAN.md section or a DESIGN.md section. Housekeeping choices (formatter, lint, pytest options, packaging metadata) are exempt; list them in the stage report. If a substantive choice has no PLAN.md section, stop and ask Pedro.
- End each stage with `documentation/stages/stage-<n>-report.md`: what was built, deviations from PLAN.md or DESIGN.md, open questions. Then stop.
- No time constraint per stage: correctness and completeness of the current stage over speed. PLAN.md › Optimising for still records the cut order because the brief grades cut reasoning.
- Never edit `documentation/self/*` or `documentation/baseline/*`. Never edit PLAN.md, DESIGN.md or this file unless Pedro asks; propose changes in the stage report.
- Keep every attempt: no force-pushes, no deleting failed experiments, the brief wants unsuccessful attempts kept for discussion.
- Commits: the first commit (Pedro's notes and the baseline documents) is Pedro's own work and carries no co-author. Every commit made with Claude Code from then on ends with a co-author trailer naming the model, e.g. `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Commit only when Pedro asks.
- Tooling: uv, Python 3.12, pytest. PDF library: PyMuPDF only (links, words with fonts, drawings); it opens the AES-256 file with its empty user password without extra packages. Docling is deferred (STRETCH.md).
- LLM calls never run live inside tests. Tests and the eval use replay mode over `runs/<run_id>/llm/*.json`. No provider key is present on the dev machine; Pedro supplies one before Stage 3 and names the primary and weaker model.

## Stages (Pedro advances them one at a time; layout and step names per DESIGN.md › Layout)

Grouped by the brief's four task steps. Stage numbers are stable; the reports use them.

### Brief step 1: Ingest the PDF
0. **Scaffold**: uv project, `schema.py`, `config.py`, `extract/ transform/ load/` packages with stub steps, `etl.py` with `--help` and `--list`, smoke test that opens the encrypted PDF and reads p.51, a `Dockerfile` for the pipeline image and a compose file with the shared volume (DESIGN.md › 3. Deployment). No LLM call.
1. **Parse**: `extract/locate.py`, `extract/parse.py`; a test that fails on naive p.51 text order and passes on the reconstruction; exactly the 7 ESRS financial-risk rows kept and the 3 opportunity rows excluded, with a test.

### Brief step 2: Extract the principal risks
2. **Identify and freeze the golden set**: `transform/identify.py` yields 3 + 7 candidates; Pedro confirms the count and writes `eval/golden.json` now, before any model output exists. Frozen from here.
3. **Describe**: `transform/llm.py` with record/replay, `prompts/v1/` including the taxonomy rule, `transform/describe.py` one call per risk; a replay run reproduces `describe.json` byte-for-byte.
4. **Merge, validate, repair**: `transform/merge.py`, `transform/validate.py` grounding against the risk's own verbatim span, one repair retry, `quality_flags`; `final.json` with 9 records.

### Brief step 3: Return a structured object
No stage of its own: `final.json` from Stage 4 is the `RiskExtraction` object (DESIGN.md › Schema), the contract that eval, load and the API all read.

### Brief step 4: Evaluate itself
6. **Eval**: `eval/evaluators.py` with the five evaluators from DESIGN.md › Evaluation, `eval/run_eval.py`, a baseline run and three regression runs (weaker model, naive p.51 text order, prompt with mitigation removed), all reproducible in replay mode.

### Beyond the brief: the product surface (this is the cut line)
5. **Load**: `load/sqlite.py` per DESIGN.md › Schema, `queries.sql`; the three brief questions run, two return empty by design.
5b. **Query API**: `src/api/` read-only REST/JSON over the database: filter by company, year, category, register; full-text search; the three brief questions as endpoints; a question endpoint with the query-understanding step from DESIGN.md › Serving API and its own golden set of questions; citations and `quality_flags` on every record; no auth; its own image and compose service reading the pipeline's volume. Endpoints match `queries.sql`; tests run against a database built from a recorded run, query understanding in replay mode.
7. **Enrichment (optional)**: embedding disagreement detector feeding `confidence`, `risk_embedding` table, spaCy NER → `entities`, enrichment from p.118 and pp.85–92 with provenance. Eval scores unchanged or better.

### Deliverables
8. **Docs and walkthrough**: DESIGN.md revised to what was built, STRETCH.md revised against what was built, README with run, replay and eval instructions, walkthrough notes ordered by the PLAN.md sections.
