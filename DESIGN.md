# DESIGN.md - Structured Risk Intelligence pipeline

How the pipeline and the API are built. Step-by-step detail is in [SPECS.md](SPECS.md).

## Stack

Python 3.12 with uv; PyMuPDF for the PDF (words, fonts, drawings, links); Pydantic for the record schema; gpt-oss 20B on a local llama-server (llama.cpp) through its OpenAI-compatible API, replaceable by another server or a hosted provider through environment variables, with every call recorded for replay; SQLite with full-text search; FastAPI; pytest; Docker Compose.

## 1. Pipeline

Three phases. Each step reads the previous step's file and writes its own under `runs/<run_id>/`.

- **Extract, no model.** Sections are found through the table of contents links. The two risk tables (p.51 main risks, pp.71–74 sustainability-report risks) are rebuilt from word positions and font sizes, because plain text order mixes their columns; an arrow icon in each sustainability row marks it as a risk or an opportunity. Every piece of text keeps its section and page.
- **Transform, the model writes and code checks.** The table rows marked as risks become 10 candidates. One model call per risk writes the description, the category and the mitigation, and a risk found in both tables merges into one record. Each record is checked against its source text, retried once, then flagged. Automatic evaluators then compare the records with expected answers written from the report (the golden set), and a failure stops the records from being loaded.
- **Load.** SQLite, one report at a time: records with citations, full-text search, a view of how each risk changes from year to year, and a log of every check's outcome (the run record).

**Built for experiments.** Each step writes its output to a file, and every model call is recorded and can be replayed without the model server. So one change (`--model`, `--prompt-version`, `--grounding`, `--break-parser`) becomes a new run, scored against the same golden set and compared in the run record. That is how the regression runs and the experiments in [experiments.md](documentation/experiments.md) were made.

## Where the model is used, and where it is not

What must be checkable (where a risk is, which risks exist, how many, whether a sentence is on the page) is code. The model writes text and reads meaning, and code checks what it writes.

- **Code:** finding sections, rebuilding tables, choosing the risks, merging, checking descriptions against the report's text, evaluation, loading.
- **Model:** descriptions (table rows are often one sentence, the brief asks for two to three), categories (nine records cannot train a classifier), and turning a question into filters.
- **Measured:** reading every page, the model found the 10 risks plus 13 extras, and 12 of those were not new risks (impacts on people, duplicates or background). spaCy, a standard language library, gave the same results as the hand-written checks but ran fifty times slower.

## 2. API

Read-only FastAPI over the SQLite file, sharing only `src/shared/` with the pipeline. Filter endpoints narrow results by company, year, category, table, status and sector, and answer the brief's three questions. A question endpoint turns plain English into the same filters with one recorded model call; the model never writes SQL. Every record carries its citations, flags and review state.

## Trade-offs

Each traces back to PLAN.md.

| Choice | Instead of | Why, from PLAN.md | Cost |
| --- | --- | --- | --- |
| The risk tables decide which risks exist | The model reading the pages | Correctness: code can count and check them | Risks described only in paragraphs are missed |
| Rebuilding tables from word positions | Docling, or a model reading the text | Correctness: which cell and which arrow a sentence belongs to can be checked | Every new layout is engineering work |
| Local 20B model | A hosted frontier model | Cost is a constraint; the same server replays tests | Weaker on hard categories; one request at a time |
| One model call per risk | One call per page | Correctness: each record is checked and fixed on its own | 16 to 17 calls per report instead of 4 |
| Flagged records served with their flag | Review before loading | Assumption: users accept flagged records | A wrong record can reach a client, marked |

## Scaling

17 calls and 36 seconds per report on one local GPU, almost all of it model time: about 2 hours for 200 reports, 30 minutes with four model servers, and $0.16 a quarter at hosted gpt-oss-20b prices. The API answers a filter query in milliseconds; a plain-English question takes about a second. Measurements are in [SCALABILITY.md](SCALABILITY.md).

## 3. Deployment

Two Docker images from one Dockerfile: `pipeline` runs a report as a batch job, and `api` serves the database read-only from the same volume. The model is needed only for the transform and the question endpoint; replay runs and the filter endpoints work without it.
