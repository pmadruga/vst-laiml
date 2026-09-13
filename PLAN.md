# PLAN.md - Structured Risk Intelligence pipeline

*What this is:* It answers the five questions in the brief; it's about what is being built, for whom, what it is optimised for, and what is deferred. DESIGN.md says how it is built and cites the sections below.

Quick recap, after my raw initial [notes](/documentation/self/notes.md) taken when reading the brief the first time. The product is a queryable risk database with search, filter and trend over time. This pipeline turns one report (Vestas Annual Report 2025) into structured risk records with provenance, and evaluates itself.

## Who is the user, and how will they consume the output?

The consumers are the firm's analysts and its clients, asset managers and compliance teams. Both use the same API to search, filter and trend risks across companies and years; the three example questions in the brief are the kind of query it serves. This pipeline produces what that API serves: one JSON record set per report, loaded as rows into a relational database with exact provenance, so any consumer can open the cited page and check a record themselves.

## Roughly what does the product surface look like?

Two surfaces. A batch ingestion pipeline runs per report as reports arrive each quarter and writes to the database. A read-only query API in front of the database serves analysts and clients, taking a natural-language question that the API first parses into the same filters, category included, before querying. Alerting is a stretch goal.

## What are you optimizing for: correctness, coverage, cost, throughput?

I'm aware that the consumers of the pipeline/API have to analyse several documents per year. The approach is to start "small and simple" while evaluating what generalises and what doesn't.

So, I'm going for a cost-conscious correctness, while determining what generalises and what doesn't.

### Correctness

The user needs to find the data they want. That data needs to be correctly inferred from what the user queries the serving API with, that means the risks need to be properly identified. The found data needs to have provenance. Everything from searching, filtering and trending needs to be delivered to the user. I'm prioritizing evaluation to ensure correctness, but starting with a deterministic one.

### Cost, coverage and throughput

Infrastructure stays simple as long as the evaluation pipelines are "green". There is no human evaluation in my approach: the golden set is the expected output for the reference report, written from the report's own registers before any model output, and the evaluators are deterministic. Reports the pipeline processes do not need one; only the few reference reports do.

The target of my approach, in order: identification and provenance correctness on this report; then coverage of the four in-scope sections, which the brief requires. Cost and throughput are not targets at about ten pages per report. Coverage of the corpus (other reports and years) and throughput (reports per hour) are stretch goals; I start with the provided report and iterate from there.

The determinism is at a high-level, meaning that it's only when strictly necessary that an LLM is used as a fallback in order to keep the costs down. Each phase ends in a validation point whose outcomes are counted per run; those counts, not intuition, decide where the next hour or the next model call goes.

## What assumptions are you making?

- The users are very interested in the factuality provided by the API. An API returning wrong results (or lack of provenance) would erode the users' trust in the system, thus removing the value-proposition of this system.
- There's an ingestion pipeline and there's an API to serve the results (where the user can search, filter, and look at trends). I chose to keep them separate.
- There's only one document being parsed and indexed for now, so it doesn't generalize to other documents just yet, but potentially to other years (if there's time, it will be detailed in the [STRETCH.md](/STRETCH.md)).
- This approach assumes a born-digital PDF with a text layer and the sections at the brief's pages; other layouts are deferred.
- Sections are located by their title in the table of contents; reports without a matching TOC entry are flagged and deferred.
- The provided reports already include the risks as well as a starting fixed taxonomy.

## What are you explicitly not solving here but would tackle next?

Detailed in [STRETCH.md](/STRETCH.md)
