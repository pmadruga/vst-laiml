# Identification on every in-scope page against table-only identification (2026-09-14)

*What this is:* today a risk exists only if it is a row in one of the report's risk tables (PLAN.md › Assumptions). This measures what that misses: the same identify prompt and model run on all 15 in-scope pages, prose included, and every proposal is compared with the 10 table risks.

## Method

`eval/compare_identify.py`, gpt-oss 20B, identify prompt v1, temperature 0. The four table pages replay the baseline's recorded calls, so their answers are exactly today's; the 11 other pages (p.50, p.72, pp.85–92, p.118) were called live once and recorded in `eval/runs/exp-identify-all/`, so the comparison replays without a model server. A proposal is kept only if its quoted sentence is on the page, as in T1. Each kept proposal is matched to a table risk by quote, or by title when similarity is at least 0.8, and located: which parsed table row holds the quote, and on prose pages the nearest "Type of impact" line. Labels for the unmatched proposals are mine, read against the page text quoted below.

## Results

**Per page.** 24 proposals, 23 kept, 1 dropped because its quote was not on the page.

| Pages | Proposals kept | What the pages are |
| --- | --- | --- |
| p.51, pp.71–74 (tables) | 14 | today's identify calls, replayed |
| p.50 | 2 | the risk management process |
| p.72 | 0 | ESRS table page with impacts and opportunities only |
| p.85 | 0 (1 dropped) | climate IRO descriptions |
| p.86 | 4 | climate resilience analysis and policies |
| p.87 | 1 | decarbonisation actions |
| pp.88–92 | 0 | GHG metrics tables and accounting policies |
| p.118 | 2 | cyber security IRO descriptions |

**Table risks: all 10 found**, the same as today's agreement check.

**The 13 proposals the tables do not have:**

| Page | Proposal | What it is in the report | Label |
| --- | --- | --- | --- |
| 73 | Risk of forced and child labour in the supply chain | an entry in the Impacts column (S2) | impact |
| 74 | Land-use restrictions during wind-farm construction | Impacts column (S3) | impact |
| 74 | Failure to respect indigenous peoples' rights | Impacts column (S3) | impact |
| 74 | Cyber security incidents | Impacts column (G1) | impact |
| 118 | Cyber security incidents (entity-specific) | the same G1 entry restated; "Type of impact: Potential, negative impact" | impact |
| 118 | Cyber security risks (entity-specific) | the table's G1 cyber risk restated; "Type of impact: Risk" | duplicate of a table risk |
| 86 | Significant investments required to align with climate targets | "mitigating financial impacts from carbon taxes and tariffs requires significant investments" | duplicate: elaborates carbon taxes |
| 86 | Immaturity of necessary solutions | the same sentence as the row above | duplicate: elaborates carbon taxes |
| 87 | Carbon taxes and tariffs on conventional steel | "upcoming carbon taxes and tariffs will increase costs for imported conventional steel" | duplicate of a table risk (title match missed across pages) |
| 50 | Operational, commercial, macroeconomic and regulatory challenges | "These risks include operational, commercial, macroeconomic, and regulatory challenges" | context, no specific risk |
| 50 | Climate change mitigation and responsible business conduct | a list of material sustainability topics | context |
| 86 | Uncertainties and assumptions in future analysis | a caveat on the scenario analysis | context |
| 86 | Dependence on political action | "Our business outlook also depends on political action; without supportive policies, our industry may struggle to meet global climate targets." | **a risk stated only in prose**; overlaps the table's geopolitics and regulatory framework and insufficient market conditions |

The dropped p.85 proposal was carbon taxes again: its quote joined "mate-rials", which the page breaks across a line, so the on-page check rejected it.

**Summary of the 23 kept proposals:**

| | Count |
| --- | --- |
| Table risks (all 10) | 10 |
| Duplicates or elaborations of a table risk | 4 |
| Impacts on people or society, not risks to the company | 5 |
| Context or caveats | 3 |
| A risk stated only in prose | 1 |

## Findings

1. **On this report the tables miss little.** The prose pages' own entries typed as risks are carbon taxes (p.85, "Financial transition risk") and cyber security risks (p.118, "Risk"), both already table risks. One sentence on p.86, dependence on political action, states a risk the tables do not name as such, and it overlaps two table risks.
2. **Model-first identification would add noise, not coverage, here.** Read over every page it proposes 13 extras, of which 12 are impacts, duplicates or context. Replacing the tables with it would need three extra steps: typing (risk, impact, opportunity, context), deduplication against the tables and across pages, and analyst review of what is left.
3. **The prose carries its own type label.** The topical sections state "Type of impact: Risk", "Financial transition risk" or "Potential, negative impact" for each entry. That text is the prose-page equivalent of the table's arrow icon, and a deterministic way to type prose candidates without trusting the model's reading.
4. **The quote check has a hyphenation gap.** A proposal quoting a word the page breaks across lines is rejected; normalising line-end hyphens in the check would keep it.

## What this means for the limitation

For Vestas 2025, table-only identification loses at most one prose risk, and that one overlaps table risks. The limitation matters for filers whose principal risks are written as headed prose rather than tables; there, the fix in the walkthrough applies: the model finds and quotes candidates on every page, the report's own "Type of impact" labels or the model types them, candidates are deduplicated against any tables, and prose-only records start as `pending_review`. This report is not the test of that path; a prose-style report is.

## Limits

One report, one model, one prompt, temperature 0 and a single live call per new page. The labels are mine. Whether "dependence on political action" is a principal risk is a judgement an analyst might make differently.

## Reproduce

```sh
uv run python eval/compare_identify.py --run-dir eval/runs/exp-identify-all   # replays the recorded calls; writes identify_all.json
```
