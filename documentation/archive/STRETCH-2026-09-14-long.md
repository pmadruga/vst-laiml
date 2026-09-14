# STRETCH.md: what comes next with another week

*What this is:* everything that I'd implement right after, assuming there would be a longer timeline, a larger budget and higher number of resources. It answers the brief's question "What are you explicitly not solving here but would tackle next?"; PLAN.md points here.

## Next

I'd basically handle the trade-offs that couldn't be done, which is coverage and throughput.

1. **Finding risks written in paragraphs, not only in tables.** Today a risk counts only if it is a row in one of the report's risk tables. Many companies describe their risks in running text instead, and the pipeline would find none of them. A model would read every page and quote possible risks, which are then sorted from impacts and background, checked against the tables for duplicates, and reviewed by an analyst ([how that looks on the Vestas report](documentation/stages/identify-all-pages.md)).
2. **A second report, and a second year.** With only the 2025 report loaded, the database cannot show how a risk changed over time, so the brief's question about "newly elevated" risks returns nothing. The 2024 Vestas report is the natural next one; the pipeline already finds its sections, but not yet its tables.
3. **Analysts reviewing flagged records.** Records that fail a check are marked for review (one in nine today), but nobody reviews them yet. Analysts would confirm or correct them, and each correction would improve the reference answers the pipeline is tested against.
4. **Reports laid out differently.** The table reader is built around how Vestas lays out its pages, and other companies will differ. First by teaching it more section names and table markers, then with Docling, a library that recognises table layouts.
5. **Alerts, then logins.** Once a second year is loaded, clients could be told when a new or growing risk appears in a company they follow. Logins and per-client access come with the first external client.
6. **Processing many reports at once.** The pipeline takes one report per run. When a full quarter of reports arrives, they should run side by side; the model server sets the pace, and one failing report should not stop the rest.
7. **Search by meaning, and source quotes from the model.** Search today matches words; a vector index would let "supplier concentration" find risks worded differently. The citations API is described below.

## Deferred engineering

- **Citations API.** The model would return, for each sentence it writes, the exact passage and page it came from, replacing our own word-matching check. It is billed per token and cannot be combined with the structured JSON output the pipeline uses, so it would need a second step.
- **Docling.** In a test it rebuilt the three-column risk table on p.51 correctly where the current PDF library's table tool did not. It adds a large dependency, a ~1 GB model and about 2.5 seconds per page, and it cannot see the small arrows that mark a row as a risk or an opportunity.
