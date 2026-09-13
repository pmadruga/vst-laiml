# DESIGN.md - Structured Risk Intelligence pipeline

ETL where T is a language model. Every step is a pure function whose output is written to disk per run, and every output records which strategy produced it and any flags raised. Phase summaries are below; the per-step specification is in [SPECS.md](SPECS.md).

## High-level approach

The pipeline parses the provided PDF and reads the risks the report itself lists, with their page references (EXTRACT). An LLM then turns each risk into a comparable record: a standard description, a category from the fixed taxonomy in the brief, the stated mitigation. Each record is validated against the page text before it is loaded into the database (TRANSFORM). An API serves that database (after LOAD).

This is an ETL pipeline. My approach starts small and simple on the provided report and measures what generalises: every step records the strategy it used and every validation point counts its failures, so a run on a second report shows where the pipeline held and where it did not.

A hand-labelled golden set for this report checks that the records are true, and catches regressions when the model, the parser or the prompt changes.

## 1. Pipeline

Three phases of pure steps; each step reads the previous step's file and writes its own under `runs/<run_id>/`. Per-step detail is in [SPECS.md](SPECS.md).

### EXTRACT: find the sections, read them into blocks with provenance (E1–E8)

Deterministic, no model, one library (PyMuPDF). Sections are found through the TOC's link annotations, which resolve straight to page indices, and verified on the landing page. Two pages are rebuilt from word coordinates because plain text breaks them: the three-column main-risks table on p.51, and the ESRS tables on pp.71–74, where risk versus opportunity is read from an arrow icon in the drawings and cross-checked against the row text. The phase ends with checks that nothing was invented, moved or dropped; a required section that fails stops the run for that report. The phase exists to turn pages into blocks whose provenance is a fact, not a claim: every block names the section and page it came from, and every later step reads blocks, never the PDF.

### TRANSFORM: turn blocks into comparable, validated records (T1–T6)

The model's phase; every call is recorded for replay. Candidates come from the report's own registers, with a model-proposed set run alongside only to measure agreement. One structured call per risk writes the description, the categories from the brief's seven, and the mitigation as stated or null. Duplicates across registers merge into one record with all citations. Each record is grounded in its page text, with one retry, then flagged. The phase ends with set-level checks and, where a golden set exists, the evaluators; a failing evaluator stops the load. The phase turns a report's own words into records that can be compared across companies and years, and it refuses to load any record it cannot ground in the page.

### LOAD: store the records, serve the questions (L1–L6)

SQLite, one transaction per report: risk instances with citations, categories, canonical ids and lineage; indexes and full-text search; a status view per canonical risk and year; the three brief questions as a query file; review states whose corrections feed the golden set. The run record collects every validation outcome from all phases, so a second report shows which step to generalise next. The phase exists to make the records queryable and accountable: every row carries its citations and lineage, and the run record says how it got there.

## 2. API

A read-only service over the SQLite file that LOAD writes, sharing only the schema with the pipeline and running as its own process. Structured endpoints take filters (company, year, category, register, status) and answer the three brief questions; a question endpoint first parses a natural-language question into those same filters with one recorded model call, using the taxonomy and mapping rule of T2, then runs our SQL with full-text search over any leftover words and returns the parsed intent alongside the records. Every record carries citations, quality flags, review state and lineage; authentication, per-client scoping, writes, alerting and semantic search are in STRETCH.md.

## 3. Deployment

Both parts run in Docker. One image per part: `pipeline` runs `etl.py` as a batch job, one container per report, and writes `runs/<run_id>/` and the SQLite file to a mounted volume; `api` serves that file read-only from the same volume. A compose file defines the two services and the volume; the model key comes from the environment and is needed only for the transform phase and the question endpoint, so replay runs and the structured endpoints need none. Staging is the same compose file pointed at a separate volume holding the golden reports.
