# PLAN.md - Structured Risk Intelligence pipeline

*What this is:* It answers the five questions in the brief; it's about what is being built, for whom, what it is optimised for, and what is deferred. DESIGN.md says how it is built and cites the sections below.

Quick recap, after my raw initial [notes](/documentation/self/notes.md) taken when reading the brief the first time. The product is a queryable risk database with search, filter and trend over time. This pipeline turns one report (Vestas Annual Report 2025) into structured risk records with provenance, and evaluates itself.

## Who is the user, and how will they consume the output?

Two consumers, one API. The firm's analysts use it twice: to look at records the pipeline flagged for review, and to search, filter and trend like anyone else. Clients, asset managers and compliance teams, use it to query; compliance teams need the citation trail, asset managers need the cross-company filter. This pipeline produces what the API serves: one JSON record set per report, loaded as rows into a relational database with exact provenance, so any consumer can open the cited page and check a record themselves.

## Roughly what does the product surface look like?

Two surfaces (ETL pipeline and API), kept as two separate parts of the codebase with one shared contract. A batch ingestion pipeline runs per report as reports arrive each quarter and writes to the database. A read-only query API in front of the database serves analysts and clients, taking a natural-language question that the API first parses using an LLM into the same filters, category included, before querying. Alerting is a stretch goal, although pipeline runs store logs so the firm's analysts and developers can use it to evaluate and potentially improve the pipeline (thus the API too, of course).

## What are you optimizing for: correctness, coverage, cost, throughput?

Correctness of identification and provenance, on one report, measured. The model stays out of extraction because a deterministic step can be checked exactly; that it is also the cheapest path at 200 reports a quarter is a consequence, not the reason. The approach starts small on the provided report and measures what generalises, so the second report tells me where the pipeline held and where it did not. Then it can be scaled to more reports.

### Correctness

Correct means three things: every risk the report lists is found, every record cites the page it came from, and every description uses the report's own words. Each has its own evaluator, and a record that fails a check is served with a flag rather than dropped.

### Cost, coverage and throughput

Infrastructure stays simple as long as the evaluation pipelines are "green". There is no human evaluation in my approach: the golden set is the expected output for the reference report, written from the report's own risk registers before any model output, and the evaluators are deterministic.

The target of my approach, in order: identification and provenance correctness on the provided report; then coverage of the four in-scope sections, which the brief requires. Coverage of the corpus (other reports and years) and throughput (reports per hour) are stretch goals; I start with the provided report and iterate from there.

Two things are settled without the model: which risks exist and where they came from. Everything else, the description, the category, the reading of a question, is model output, and that is fine because each piece is checked against the page or returned for the reader to see. Each phase ends in a validation point whose outcomes are counted per run; those counts, not intuition, decide where the next hour or the next model call goes.

## What assumptions are you making?

- A wrong record with a page citation costs more trust than a missing record. If that is false, recall should outweigh grounding and the validation step should warn instead of flagging records for review.
- The report's own risk registers list its principal risks: the main-risks table and the ESRS rows marked as financial risks. The pipeline finds what the company chose to list, not risks the company omitted; the model-proposed candidates only measure agreement with the risk register. This is also why I dropped the multi-model consensus my first notes proposed: a fixed risk register gives a count to check against, which is cheaper and more auditable than agreement between models.
- The brief's seven categories are the client's taxonomy and each risk has one primary cause. Injuries, labour fines and bribery fit it only through a written cause test; if the client wants finer categories, the enum and the golden set change together.
- The reports are born-digital PDFs with a text layer and a table of contents. Other layouts are detected, flagged and deferred, not parsed silently.
- One reference report labelled from its risk registers is enough to catch regressions in the parser, the prompt and the model. My notes assumed domain experts would curate the golden set; here it is written from the report's risk registers, which settle identification, so what an expert would still contest is category, and that enters later through reviewed corrections.
- Analysts and clients accept records that carry a quality flag. Nothing is held back for a human before it is served.

## What are you explicitly not solving here but would tackle next?

In order of what I would build next, each detailed with its trigger in [STRETCH.md](/STRETCH.md):

1. A second report and year, so that year-over-year status and the second example question have data. Trigger: the 2024 report, which the extract phase already reads up to the section titles.
2. Analyst review of flagged records, with corrections feeding the golden set.
3. Layouts the coordinate parser does not know, first through more title synonyms and table anchors, then Docling. Trigger: E3 and E8 failures on the run record.
4. Alerting on new or elevated risks, then authentication and per-client scoping. Trigger: the second year, then the first external client.
5. Semantic search and the citations API, which need a vector index and a per-token model provider respectively.
