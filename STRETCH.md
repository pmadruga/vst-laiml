# STRETCH.md: what comes next with another week

*What this is:* everything that I'd implement right after, assuming there would be a longer timeline, a larger budget and higher number of resources. It answers the brief's question "What are you explicitly not solving here but would tackle next?"; PLAN.md points here.

## Next

I'd basically handle the trade-offs that couldn't be done, which is coverage and throughput.

1. **Identifying risks beyond the report's tables**, for generalisation to reports that disclose principal risks in prose. Trigger: the first report whose risk sections have no risk table (E3 and E8 find none), or whose prose names a principal risk its tables do not. On Vestas the tables miss at most one prose risk, and the identify prompt run over every in-scope page adds 12 impacts, duplicates and context passages alongside it ([comparison](documentation/stages/identify-all-pages.md)). So the model proposes quoted candidates on every page, each is typed as risk, impact, opportunity or context (from the report's own "Type of impact" label where the page has one), candidates are deduplicated against the tables and across pages, and prose-only records start as `pending_review`.
2. **A second report and year**, so that year-over-year status and the brief's second example question ("newly elevated") have data. Trigger: the 2024 report, which the extract phase already reads up to the section titles.
3. **Analyst review of flagged records, with corrections feeding the golden set.** Trigger: the share of `pending_review` records on a run.
4. **Layouts the coordinate parser does not know**, first through more title synonyms and table anchors, then Docling (detail under Deferred engineering).
5. **Alerting on new or elevated risks, then authentication and per-client scoping.** Trigger: the second year loaded, then the first external client.
6. **Semantic search and the citations API**, which need a vector index and a per-token model provider respectively (the citations API in detail under Deferred engineering).

## Deferred engineering

- **Citations API.** Anthropic's Messages API can return each sentence of a description with the exact source passage and page number it came from, which would turn the grounding check into a fact the model supplies; it needs a Console API key billed per token and cannot be combined with structured output, so the record's JSON would come from a second step.

- **Layout generalisation with Docling.** Trigger: the second report whose risk tables are not the two layouts the coordinate parser knows (the run record's E3/E8 failures say when). Docling's layout and table models reconstructed the p.51 three-column table correctly in a 2026-09-13 test, where PyMuPDF's table finder and pymupdf4llm dropped the third column; it costs a torch dependency, a ~1 GB model download and ~2.5 s per page on CPU, and it cannot see the risk/opportunity icon, so the icon read from the drawing layer, or the row text plus the topical "Type of impact" line, stays.
