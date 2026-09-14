# Results of the recorded runs

The five runs ship in `eval/runs/` with their model recordings, recorded live on 2026-09-14 (`runs/` at the top level is git-ignored working output), so every number below reproduces in replay mode, for example `uv run python etl.py --extract --transform --run-id check --replay baseline`. Model: gpt-oss 20B through llama-swap, prompt v1, temperature 0, grounding checks in regex unless the run says otherwise. Each run's `run.json` lists every invocation that produced it.

| Run | identification | provenance | grounding | category | fields | evaluators failed | pending review | what the run record adds |
|---|---|---|---|---|---|---|---|---|
| `baseline` | 1.00 | 1.00 | 0.89 | 1.00 | 1.00 | none; intent 0.89 on nine questions | 1 | 10 risk register candidates, model agreement 1.0 on identification, 9 records after merging cyber, the carbon-taxes mitigation taken from the p.86 actions paragraph; the cyber description does not use "critical infrastructure"; question 5 does not keep "tariffs" as search text |
| `reg-broken-parser`: p.51 read in naive text order, well-shaped but text under the wrong risk | 1.00 | 1.00 | 0.67 | 0.89 | 0.78 | grounding, fields | 1 | the pipeline's own checks all pass, because every word is still on the page; the golden set catches it: project execution is described and categorised as a cyber threat with no mitigation, and the geopolitics mitigation is wrong |
| `reg-prompt-no-mitigation`: describe prompt with mitigation removed | 1.00 | 1.00 | 0.89 | 1.00 | 0.67 | fields | 1 | the three risks whose mitigation the report states come back with none |
| `reg-weak-model`: ministral 14B instead of gpt-oss 20B | 1.00 | 1.00 | 0.11 | 0.89 | 1.00 | grounding | 3 | identification agreement drops to 0.8; geopolitics categorised as supply chain; eight of nine descriptions paraphrase the report's terms ("cyber threats", "compensation obligations", "delays in permit issuance") instead of using them; three records pending review |
| `exp-grounding-spacy`: T4 checks on spaCy instead of regex | 1.00 | 1.00 | 0.89 | 1.00 | 1.00 | none | 1 | the same records and scores as the baseline; see [stages/grounding-comparison.md](stages/grounding-comparison.md) |

The baseline record pending review is the corruption row, where the model's second sentence restates the consequence in words the text does not use. The carbon-taxes record carries a note, not a review flag, saying its mitigation was taken from p.86.

## What changed on 2026-09-14

The evaluators were made able to fail on what they claim to measure, after the second review panel:

- **Grounding** now searches only what the model wrote, the description and the mitigation, and flags any number in the description that is not on the record's cited pages. It used to search the copied span and citation spans as well, which are page text, so a fabricated description with a correct span scored 1.0. A test now proves it fails.
- **Intent** now compares every field of the parsed question, including years and search text, with sector compared normalised. It used to ignore years and search text and compare sector only by presence.

The carbon-taxes mitigation had been a quoted cross-reference picked up by the enrichment regex; it is now the paragraph under the "Actions and resources" heading. The four runs were re-recorded live so that each run's provenance is complete. The recordings of 2026-09-13 are kept unchanged in `eval/attempts/2026-09-13/`. Scored with the stricter evaluators they give: baseline grounding 0.89 and intent 0.89; broken parser grounding 0.78, category 0.89, fields 0.78; prompt without mitigation fields 0.67; weaker model grounding 0.11 and category 0.89. With the old evaluators the baseline had scored 1.00 everywhere and the weaker model had passed.

## Reading the scores

The weaker model is the result that moved most. Under the old grounding evaluator it passed, and I described it as movement rather than failure. Under the stricter one it fails, not because it invents facts but because it rewrites the report's terms in its own words; that is the failure PLAN.md › Correctness names, "every description uses the report's own words". Its one category miss in nine still does not fail the category evaluator.

Nine records mean a threshold of 0.8 allows one miss, so these scores are a regression smoke test, not an accuracy estimate. Category and intent are in-distribution checks: the prompts state the cause test the hard cases need, and the next report is the held-out test.

Tests: `uv run pytest` runs 30 tests in a few seconds, no model server needed.
