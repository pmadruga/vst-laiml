# STRETCH.md: what comes next with another week

*What this is:* everything that I'd implement right after, assuming there would be a longer timeline, a larger budget and higher number of resources. It answers the brief's question "What are you explicitly not solving here but would tackle next?"; PLAN.md points here.

## Next

I'd basically handle the trade-offs that couldn't be done, which is coverage and throughput.

1. **Finding risks written in paragraphs.** Today only rows in the report's risk tables count, so a company that describes its risks in text would show none. A model would quote possible risks from every page, and each would be checked against the tables and reviewed ([tried on Vestas](documentation/stages/identify-all-pages.md)).
2. **A second report and year.** With one year loaded, nothing can show how a risk changed, so "newly elevated" returns nothing. The 2024 Vestas report is next.
3. **Analysts reviewing flagged records.** About one record in nine is flagged, but nobody reviews them yet; each correction would also improve the answers the pipeline is tested against.
4. **Reports laid out differently.** The table reader follows Vestas's layout; other companies need more section names and table markers, then a layout library such as Docling.
5. **Alerts, then logins.** Tell clients when a risk appears or grows, once a second year is loaded; add logins with the first external client.
6. **Many reports at once.** Run a full quarter side by side; the model server sets the pace, and one failing report should not stop the rest.
7. **Search by meaning, and source quotes from the model.** Search that matches meaning, not just words, would let "supplier concentration" find risks worded differently; the citations API is below.

## Considered, not built

- **Citations API.** The model would point to the exact passage behind each sentence it writes, but it is billed per use and cannot be combined with the fixed JSON format the pipeline asks the model for.
- **Docling.** It rebuilt the p.51 table correctly, but adds a large dependency and about 2.5 seconds per page, and cannot see the arrows that mark a row as a risk or an opportunity.
