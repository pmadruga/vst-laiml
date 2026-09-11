# Preliminary study - not the PLAN.md

## What's in it

In these unstructured notes you can find my thoughts about the case. It's a document I typically start with when working or landing in a new project. It usually becomes a document that I revisit many times over the course of a project, and it allows me to check if I still have the same "north star" as in the beginning of the project, because focus is essential for any project, in my personal opinion. This is part of my "understanding" phase.

No AI has been used to generate this document other than for detecting typos.

## Intro

I need to build a pipeline for Structured Risk Intelligence. First, I'll do some research about Structured Risk Intelligence to make sure I have a good baseline understanding of the problem. After all, I want to understand the mind of the stakeholders so I can deliver a product (in this case, a pipeline) that generates the most value to the end-user and/or the company.

## About my (hypothetical) team

A small team at a research firm. This firm sells structured risk intelligence to asset managers and compliance teams.

## The problem

The analysts need to speed up the time to analyze corporate annual reports, per quarter, and determine several risks and their properties, such as:

- how the risks are disclosed
- how the category of these risks changes over each year
- which emerging risks appear

It's also important that different analysts typically report different risks. This means that not only is there a lack of consensus between humans on what constitutes a risk, but also that this pipeline needs to have a consensus mechanism (probably between different LLMs) for identifying risks.

As a reminder, the stakeholders are compliance and asset managers.

## Specification

### Infrastructure

- A structured, queryable risk database. It needs to be enriched for the provided [annual report](/documentation/baseline/VestasAnnualReport2025.pdf) as well as potential other documents similar to that one. This last part is a stretch goal.
- There needs to be an API serving this, otherwise the user is querying the database directly, which is not ideal from a security standpoint. The document doesn't recommend any specific tools, although I prefer gRPC over REST mostly due to the bidirectionality of data. I believe that in this case REST is simpler and a good starting point. It boils down to how the consumers will consume this database: directly or via another tool/application (like BI tools).
- It's a production deployment so scalability is important. Dockerization is almost a must here. It also leaves an open road to determine what goes into staging - is it the same data as production or are there differences?
- Cost control is also important. There's a tradeoff between the time spent building this pipeline, as well as infrastructure costs (such as token usage, ML models used/served to enrich the data, etc.).

### Data input

The data draws from the report [here](/documentation/baseline/VestasAnnualReport2025.pdf). But not all data is relevant. There are two levels of importance:

Level 1:

1. Risk management on pages 50 to 51.
2. Material impacts, risks, and opportunities on pages 71 to 74.

Level 2 (optional):
3. Cyber security on page 118
4. Climate Change on pages 85 to 92.

There is no need to process all 190 pages. As a nice-to-have, the pipeline would ingest the entire document and split it into the relevant parts beforehand. Only if I have the time and this would be something to be included in future improvements, if not possible to be done in the short term.

### Data outputs

It should support the examples provided in the [case](/documentation/baseline/Case_GenAIandNLPEngineer.pdf). These can be used as unit tests/evaluation data set.

There are several metadata fields that need to be indexed in order to answer the example questions, such as:

- risk identification: what constitutes a risk.
- risk categorization per risk: financial, operational, regulatory, market, climate, cyber and supply chain
- the section and page of the risk
- potential mitigation actions, per risk

The output should be JSON, Pydantic or other. I prefer Pydantic due to the safety of types.

### Confidentiality

Because these annual reports are public, there's a freedom in terms of using LLMs with lower levels of security, such as lack of Zero Data Retention and/or EU-hosted presence.

### Evaluation

Need to build a dataset to catch regressions that catches parsing errors, but also that allows for experimenting with weaker models and/or prompt modifications. What I'm missing to understand here is what a golden set + at least one evaluator would look like. In my current position, this dataset is done and curated by domain experts, but in this case I'm not one.

## Product requirements

In these notes, I have to have a good grasp of:

- Who is the user, and how will they consume the output?
- Roughly what does the product surface look like (batch API, interactive UI, alerting, …)?
- What are you optimizing for in this first slice: correctness, coverage, cost, throughput?
- What assumptions are you making?
- What are you explicitly not solving here but would tackle next?
