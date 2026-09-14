# Results of the recorded runs

The four runs ship in `eval/runs/` with their model recordings (`runs/` itself is git-ignored working output), so every number below can be reproduced in replay mode, for example `uv run python etl.py --extract --transform --run-id check --replay ../eval/runs/baseline`. Model: gpt-oss 20B through llama-swap, prompt v1, temperature 0. The prompts are generic: they name categories and a cause test, not this report's rows, and the nine golden questions include four the intent prompt never mentions.

| Run | identification | provenance | grounding | category | fields | evaluators failed | what the run record adds |
|---|---|---|---|---|---|---|---|
| `baseline` | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | none; intent 1.00 on nine questions | 10 risk register candidates, model agreement 1.0 on identification, 9 records after merging cyber, one mitigation taken from the climate section for the carbon-taxes risk, 1 record flagged for review |
| `reg-broken-parser`: p.51 read in naive text order, well-shaped but text under the wrong risk | 1.00 | 1.00 | 0.78 | 0.89 | 0.78 | grounding, fields | the pipeline's own checks all pass, because every word is still on the page; the golden set catches it: project execution and cyber carry the wrong text, project execution is mis-categorised, mitigations are wrong |
| `reg-prompt-no-mitigation`: describe prompt with mitigation removed | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | fields | the three risks whose mitigation the report states come back with none |
| `reg-weak-model`: ministral 14B instead of gpt-oss 20B | 1.00 | 1.00 | 1.00 | 0.89 | 1.00 | none | movement, not failure: one category wrong (geopolitics as supply chain), 4 grounding flags instead of 2 |

The weaker model stays above the category threshold, one miss in nine. That is the honest result on this report: a 14B model is not weak enough to fail this golden set, and the run record is what shows the degradation. The baseline record flagged for review is the corruption row, where the model's second sentence restates the consequence in words the text does not use; it is loaded with `review_state = pending_review`. The carbon-taxes record carries a note, not a flag, saying its mitigation was taken from p.86.

Tests: `uv run pytest` runs 19 tests in about 20 seconds, no model server needed.
