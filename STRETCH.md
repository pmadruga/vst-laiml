# STRETCH.md: what comes next with another week

*What this is:* everything that I'd implement right after, assuming there would be a longer timeline, a larger budget and higher number of resources.

## Human in the loop

Ranked by what each returns for the effort; each has the trigger that makes it worth building.

- **Review of flagged records.** Trigger: the share of `pending_review` records on a run, two of nine on the baseline. An analyst confirms or corrects the record; the correction lands in the `correction` table and flips `review_state`. Until then flagged records are served with their flag.
- **Corrections feeding the golden set.** Trigger: the first ten corrections. A corrected record on a reference report becomes the expected output for that risk, so the golden set grows from real disagreement rather than from labelling sessions.
- **Second labeller.** Trigger: a category dispute an analyst cannot settle from the prompt's cause test. Two people label the reference report blind; the agreement number becomes the floor for the category evaluator.

## Deferred product features

- **Alerting.** Trigger: the second fiscal year loaded, when `risk_status` first returns rows. "New or elevated risk in your portfolio" is a query over the status view joined to a client portfolio, sent by email or webhook after each batch.
- **Authentication and per-client scoping.** Trigger: the first external client. Keys per client; portfolios visible only to their owner; the read-only service otherwise unchanged.
- **Writes through the API.** Trigger: analysts reviewing in a tool rather than in SQL. A single endpoint that records a correction; the pipeline stays the only writer of records.

- **Vector database.** Embedding every block and record would let a question find risks by meaning rather than by shared words, so "supplier concentration" retrieves the geopolitics and project-execution risks even though neither uses those words. It would also give the pipeline a second way to locate sections and rows in a report whose titles and layouts the parser does not know, by similarity to the ones it does.

## Deferred engineering

- **Citations API.** Anthropic's Messages API can return each sentence of a description with the exact source passage and page number it came from, which would turn the grounding check into a fact the model supplies; it needs a Console API key billed per token and cannot be combined with structured output, so the record's JSON would come from a second step.

- **Layout generalisation with Docling.** Trigger: the second report whose risk tables are not the two layouts the coordinate parser knows (the run record's E3/E8 failures say when). Docling's layout and table models reconstructed the p.51 three-column table correctly in a 2026-09-13 test, where PyMuPDF's table finder and pymupdf4llm dropped the third column; it costs a torch dependency, a ~1 GB model download and ~2.5 s per page on CPU, and it cannot see the risk/opportunity icon, so the icon read from the drawing layer, or the row text plus the topical "Type of impact" line, stays.
