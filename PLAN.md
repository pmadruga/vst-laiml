# PLAN.md — Structured Risk Intelligence pipeline

*What this is:* It answers the five questions in the brief; it's about what is being built, for whom, what it is optimised for, and what is deferred. DESIGN.md says how it is built and cites the sections below.

Quick recap, after my raw initial [notes](/documentation/self/notes.md) taken when reading the brief the first time. The product is a queryable risk database with search, filter and trend over time. This pipeline turns one report (Vestas Annual Report 2025) into structured risk records with provenance, and evaluates itself. DESIGN.md cites the sections below.

## Who is the user, and how will they consume the output?

The consumers are the firm's analysts and its clients, asset managers and compliance teams. Both use the same API to search, filter and trend risks across companies and years; the three example questions in the brief are the kind of query it serves. This pipeline produces what that API serves: one JSON record set per report, loaded as rows into a relational database with exact provenance, so any consumer can open the cited page and check a record themselves.

## Roughly what does the product surface look like?

Two surfaces. A batch ingestion pipeline runs per report as reports arrive each quarter and writes to the database. A read-only query API in front of the database serves analysts and clients, taking a natural-language question that the API first parses into the same filters, category included, before querying. Alerting is a stretch goal.

## What are you optimizing for: correctness, coverage, cost, throughput?

"Cost-conscious correctness" is what I'd call it here. I want to make sure that the pipeline provides value to the users from day one.  Coverage and throughput are stretch goals.

Correctness: the user need to find the data they want. That data needs to be correctly infered from what the user queries the serving API with, that means the risks need to be properly identified. The found data needs to have provenance. Everything from searching, filtering and trending needs to be delivered to the user. I'm prioritizing evaluation, but starting with a deterministic one.

Cost: trying to keep infrastructure simple as long as the evaluation pipelines are "green". If the cost allows, there will be human evals to support correctness as much as possible.

I'll start with a low throughput (just the report provided) as well as low coverage ()

## What assumptions are you making?

- The users are very interested in the factuality provided by the API. An API returning wrong results (or lack of provenance) would erode the users' trust in the system, thus removing the value-proposition of this system.
- There's an ingestion pipeline and there's an API to serve the results (where the user can search, filter, and look at trends). I chose to keep them separate.
- There's only one document being parsed and indexed for now, so it doesn't generalize to other documents (if there's time, it will be detailed in the [STRETCH.md](/STRETCH.md)).
- The PDF is always well-structured as the one from the example.
- The evaluation is the most important part of this. However, it assumes that there are no resources for doing human evaluation of the pipeline.

## What are you explicitly not solving here but would tackle next?

Detailed in [STRETCH.md](/STRETCH.md)
