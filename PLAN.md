# PLAN.md - Structured Risk Intelligence pipeline

This pipeline turns one annual report (Vestas 2025) into structured, cited risk records, serves them through an API, and evaluates itself.

## Who is the user, and how will they consume the output?

Analysts and clients, through one API. Analysts review the records the pipeline flags, then search like everyone else. Compliance teams need the citation trail; asset managers need to filter across companies. Every record cites its page, so anyone can check it.

## Roughly what does the product surface look like?

A batch pipeline runs once per report as reports arrive and writes to a database. A read-only API serves it: filters such as company, year and category, plus a way to ask a plain-English question, which a model turns into those same filters.

## What are you optimizing for: correctness, coverage, cost, throughput?

Correctness. The two risk analysts I spoke with both said they prefer factuality. Correct means every risk the report lists is found, every record cites its page, and every description uses the report's own words; each has its own automatic check, and a record that fails one is served with a flag. Which risks exist and where they come from is settled by code, not the model, because code can be checked exactly. Coverage of more reports and throughput come once the first report is right; cost is a constraint, not the goal.

## What assumptions are you making?

- Risks come from the report's risk tables, which is a limitation in itself.
- The brief's seven categories are the ones clients use, and each risk has one main cause.
- Reports are digital PDFs, not scans, with a table of contents; a report laid out differently is flagged, not read silently.
- One report, with expected answers written from its tables, is enough to catch a drop in quality when the parser, the prompt or the model changes.
- Analysts and clients accept records that carry a quality flag.

## What are you explicitly not solving here but would tackle next?

The ranked list, and why each item matters, is in [STRETCH.md](/STRETCH.md).
