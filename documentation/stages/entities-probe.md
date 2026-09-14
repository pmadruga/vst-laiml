# Named entities probe (2026-09-14)

*What this is:* what spaCy's named-entity recogniser finds in this report's risk text, to decide whether an entities step (SPECS.md › T5) is worth building now. It follows the [grounding comparison](grounding-comparison.md), which concluded that named entities, not the grounding checks, would be spaCy's real use.

## Method

spaCy `en_core_web_sm` 3.8, no model calls, over two inputs from the recorded baseline run:

1. Each record's own text: the register span and the potential impact. This is the text an entities step would tag, since it carries a page citation and does not change when the model rephrases.
2. The topical pages the brief offers: pp.85–92 (climate change) and p.118 (cyber security), counted by label.

```sh
uv run python eval/probe_entities.py eval/runs/baseline
```

## Results

**The risk records: one of nine gets entities a query could use.**

| Record | Entities found | Useful for a query |
| --- | --- | --- |
| Geopolitics and regulatory framework | 2025, Vestas ×3, Ukraine, the Middle East, EU, China, USA | Ukraine, the Middle East, EU, China, USA |
| Project execution | Vestas ×2, "Success" as an organisation | none; "Success" is a mislabel |
| Cyber attacks | Vestas ×7 | none |
| Carbon taxes and tariffs | "GHG" as an organisation | none; a mislabel |
| Injuries in own workforce | none | none |
| Injuries to contractors and sub-contractors | none | none |
| Fines related to forced or child labour | Vestas | none |
| Insufficient market conditions | none | none |
| Risk of corruption and bribery | Vestas | none |

The reporting company's own name is most of what is found, and it is useless as a filter on its own report.

**The topical pages: mislabels dominate the labels that matter.** Distinct values per label: 136 cardinal numbers, 72 organisations, 50 dates, 39 percentages, 23 people, 20 products, 19 quantities, 10 countries, 6 locations.

- Organisations, most frequent first: "NA" (108, the table filler), "GHG" (74), Vestas (65), "Financial", "EUR", "CAPEX".
- People: "kg CO2e", "Scope 3", "OPEX", "EU Taxonomy".
- Products: "Scope 3" (37), "Scope 1" (31), "Scope 2" (12).
- Countries: "OPEX" and "Milestones" among Poland, Finland, Sweden, Spain, the UK, the US and the EU.
- Useful when filtered: countries and regions (Poland, Finland, Sweden, Spain, the UK, the US, the EU, the North Sea, the Baltic Sea, the Americas, Asia Pacific), frameworks (the Paris Agreement, the GHG Protocol, the EU Taxonomy), organisations (Global Wind Energy Council, MHI, the Science Based Targets).

## Findings

1. On this report an entities step would enrich one record in nine. None of the brief's three example questions needs entities.
2. The small model's labels are unreliable on sustainability reporting: reporting codes, units and table fillers come back as organisations, people and products. Used alone it would add wrong filters. It needs a gazetteer (spaCy's `EntityRuler`) mapping countries and regions to standard names and naming the regulations that matter (CBAM, CSRD, the EU Taxonomy, the Paris Agreement), and a filter that drops the reporting company, ESRS and Scope codes, units and "NA".
3. Many terms a risk question turns on are common nouns, not named entities: steel, tariffs, grid, auctions, permits. Full-text search and the category already cover them.

## Decision

Not built now. The trigger to build it would be the second or third report loaded, or the first client question about geographic or regulatory exposure ("which companies cite China or CBAM as a risk"). Where it would go: T5 on the merged records, tagging only the report's own text (register span, potential impact, quoted mitigation), never the model's description, before T4; each entity stored with its page in a `risk_entity` table and served through an `entity` filter on the API.

## Limits

One report, the small spaCy model, no gazetteer, and counts of distinct surface forms rather than a labelled evaluation. The transformer model (`en_core_web_trf`) was not tried.
