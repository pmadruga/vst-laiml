# DESIGN.md - Structured Risk Intelligence pipeline

This contains the approach for the pipeline and for the API, divided in these two major sections.

Phase summaries are below; the per-step specification is in [SPECS.md](SPECS.md).

## High-level approach

The pipeline parses the provided PDF and reads the risks the report itself lists, with their page references (EXTRACT). The model never decides what is a risk; it only writes. For each risk the risk register lists, one call returns a standard description, one primary category from the brief's seven, and the mitigation as the report states it, taken from the risk register row or from the topical section that details the risk. Each record is validated against the page text before it is loaded into the database (TRANSFORM). An API serves that database (after LOAD).

This is an ETL pipeline. My approach starts small and simple on the provided report and measures what generalises: every step records the strategy it used and every validation point counts its failures, so a run on a second report shows where the pipeline held and where it did not.

A golden set is the expected output for a reference report, the fixture the regression tests run against; the Vestas 2025 report is the first, and a second is added only when a report exposes a layout the parser has not seen. Running it after a change to the model, the parser or the prompt shows which evaluator moved.

## How the pipeline measures itself

Every phase ends at a validation point (E3, E8, T6, A1) and every record passes a grounding check (T4). Each check has a severity rule, error stops the report and warning counts, and names what it caught. Every outcome lands in one run record, per run, report and check. Read across runs and reports, the counts say which step to improve next and whether the fix is engineering, a prompt, or a model call; nothing is skipped silently.

## Where the model is used, and where it is not

The rule: whatever must be checkable (where a risk is, which risks exist, how many, whether a sentence is on the page) is code; the model writes text and reads meaning, and each of its outputs is checked by code afterwards. The code side is classical NLP and layout analysis, hand-rolled today.

| Step | Technique | Model | Why |
| --- | --- | --- | --- |
| Locate sections (E1–E3) | TOC link annotations, title synonyms, landing-page check | no | A page index is a fact the check can confirm exactly |
| Parse the tables (E4–E8) | Word coordinates and font sizes for cells; the drawing layer for the risk or opportunity arrow; row-count checks | no | Which cell a sentence belongs to must be verifiable; read by a model it would be a claim |
| Identify (T1) | The report's risk register rows; a model proposes candidates from the section text, kept only when its quoted span is on the page | checker only | The company's own list gives a count to check against; the model's proposals measure agreement, they do not decide |
| Describe and categorise (T2) | One structured call per risk with the taxonomy's cause test in the prompt and the ESRS topic as a prior | yes | Several register rows are one sentence and the brief asks for two to three, so quoting cannot meet it; nine labelled records cannot train a classifier |
| Mitigation (T2, T5) | p.51: the "How we manage it" cell, condensed by the model; ESRS rows: the topical "Actions and resources" paragraph found by regex, quoted | partly | The report states it; the model only shortens a stated cell |
| Merge (T3) | Title similarity and keyword hints across the two registers | no | Deterministic and recorded |
| Validate (T4) | Regex sentence split, stop-word content overlap with the span, regex for numbers, capitalised names; one model retry with the problems attached | check no, repair yes | A check that uses the model cannot catch the model |
| Evaluate | Golden set and five deterministic evaluators | no | Same reason; scores are reproducible in replay |
| Load | SQL, FTS5 full-text search, regex for the review frequency on p.50 | no | Nothing to interpret |
| Question endpoint | One structured call parses the question into filters; our SQL and FTS5 run them | yes | Mapping a paraphrase to the taxonomy ("supplier concentration" to supply_chain) is where keyword rules break; the model never writes SQL |

spaCy was measured as the T4 backend (`--grounding spacy`; [comparison](documentation/stages/grounding-comparison.md)): the same verdict as the regex checks on all 45 recorded records and on every seeded failure, fifty times slower per record and about 190 MB of dependencies, so the regex checks stay. Its real use would be named entities as a product feature, not these checks. Not built: rules for the question fields they can fill (companies and sectors matched against the database, years, status words), leaving the model only the category.

## 1. Pipeline

Three phases of pure steps; each step reads the previous step's file and writes its own under `runs/<run_id>/`. Per-step detail is in [SPECS.md](SPECS.md).

### EXTRACT: find the sections, read them into blocks with provenance (E1–E8)

Deterministic, no model, one library (PyMuPDF). Sections are found through the TOC's link annotations, which resolve straight to page indices, and verified on the landing page. Two pages are rebuilt from word coordinates because plain text breaks them: the three-column main-risks table on p.51, and the ESRS tables on pp.71–74, where risk versus opportunity is read from an arrow icon in the drawings and cross-checked against the row text. The phase ends with checks that nothing was invented, moved or dropped; a required section that fails stops the run for that report. The phase exists to turn pages into blocks whose provenance is a fact, not a claim: every block names the section and page it came from, and every later step reads blocks, never the PDF. A model fed page by page could supply the page number just as well; the coordinate parser stays for what sits below the page: which cell a sentence belongs to, which icon marks a row, and a fixed count of risk register rows that identification can be checked against.

### TRANSFORM: turn blocks into comparable, validated records (T1–T6)

The model's phase; every call is recorded for replay. Candidates come from the report's own risk registers, with a model-proposed set run alongside only to measure agreement. One structured call per risk writes the description, the categories from the brief's seven, and the mitigation as stated or null. Duplicates across risk registers merge into one record with all citations. Each record is grounded in its page text, with one retry, then flagged. The phase ends with set-level checks and, where a golden set exists, the evaluators; a failing evaluator stops the load. The phase turns a report's own words into records that can be compared across companies and years, and it refuses to load any record it cannot ground in the page.

### LOAD: store the records, serve the questions (L1–L6)

SQLite, one transaction per report: risk instances with citations, categories, canonical ids and lineage; indexes and full-text search; a status view per canonical risk and year; the three brief questions as a query file; review states whose corrections feed the golden set. The run record collects every validation outcome from all phases, so a second report shows which step to generalise next. The phase exists to make the records queryable and accountable: every row carries its citations and lineage, and the run record says how it got there.

## 2. API

A read-only service over the SQLite file that LOAD writes, sharing only the `src/shared/` contract with the pipeline (schema, configuration, run record, model client, the three brief queries) and running as its own process. Structured endpoints take filters (company, year, category, risk register, status, sector) and answer the three brief questions; a sector is resolved to the sectors stored for companies before it filters (same words after normalising, shared word stems, or a close spelling), so "renewable-energy" in a question finds "renewable energy", and one that matches no stored sector returns nothing with an empty `sector_matched`; a question endpoint first parses a natural-language question into those same filters with one recorded model call, using the taxonomy and mapping rule of T2, then runs our SQL with full-text search over any leftover words and returns the parsed intent alongside the records. Every record carries citations, quality flags, review state and lineage; authentication, per-client scoping, alerting and semantic search are in STRETCH.md.

## Trade-offs

Each follows from what PLAN.md optimises for: correctness of identification and provenance first, measured; coverage of the in-scope sections second; cost as a constraint.

| Choice | Alternative not taken | Why, in PLAN.md's terms | What it costs |
| --- | --- | --- | --- |
| The report's risk registers identify the risks; the model only writes the record | The model proposes the risks from the section text | Identification becomes a count to check, not a judgement to trust; the risk register is the company's own list (assumption 2) | A risk disclosed only in prose is missed; a report without a risk register needs the model path, which is built but only measured today |
| Coordinate parser for the two known table layouts | Docling, or a model reading page text | Provenance below the page (cell, icon, fixed row count) is a fact the checks can verify (EXTRACT) | Every new layout costs engineering time; the run record says when |
| Local 20B model through an OpenAI-compatible server | A hosted frontier model | Cost as a constraint, public inputs, and the same server for tests through record and replay | Weaker categorisation on hard cases; one request at a time |
| One structured call per risk, temperature 0 | One call per page returning all risks | Each record is grounded and repaired on its own; a bad call spoils one record | 16 to 17 calls per report instead of four |
| SQLite in a file, read by the API | Postgres | One report, one analyst, no server to run; the schema is the same SQL | Single writer; the API must be restarted when the file is replaced |
| Flagged records are served with a flag | Human review before load | Assumption 6: consumers accept flags; nothing stalls on a reviewer | Wrong records can reach a client, marked; one of nine records is flagged for review on the baseline, the share that triggers analyst review (STRETCH.md) |

## Scaling

One report costs 16 to 17 model calls (the number of repairs varies between runs) and 36 seconds on one local GPU, almost all of it the model, so a quarter of 200 reports runs in about two hours; the measurements, token costs and extrapolation are in [SCALABILITY.md](SCALABILITY.md).

## 3. Deployment

Both parts run in Docker. One image per part: `pipeline` runs `etl.py` as a batch job, one container per report, and writes `runs/<run_id>/` and the SQLite file to a mounted volume; `api` serves that file read-only from the same volume. A compose file defines the two services and the volume; the model key comes from the environment and is needed only for the transform phase and the question endpoint, so replay runs and the structured endpoints need none. Staging is the same compose file pointed at a separate volume holding the golden reports.
