# STRETCH.md: what comes next with another week

*What this is:* everything that I'd implement right after, assuming there would be a longer timeline, a larger budget and higher number of resources.

## Human in the loop

## Deferred product features

## Deferred engineering

- **Layout generalisation with Docling.** Trigger: the second report whose risk tables are not the two layouts the coordinate parser knows (the run record's E3/E8 failures say when). Docling's layout and table models reconstructed the p.51 three-column table correctly in a 2026-09-13 test, where PyMuPDF's table finder and pymupdf4llm dropped the third column; it costs a torch dependency, a ~1 GB model download and ~2.5 s per page on CPU, and it cannot see the risk/opportunity icon, so the icon read from the drawing layer, or the row text plus the topical "Type of impact" line, stays.
