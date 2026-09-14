# Grounding checks: hand-rolled regex against spaCy (2026-09-14)

*What this is:* a measured comparison of the two implementations of the T4 grounding checks, and the decision it supports. DESIGN.md › Where the model is used, and where it is not, lists T4 as classical NLP; this is the test of whether a standard NLP library does that part better than the regex written for it.

## What was compared

The T4 checks on every record: the description has 2 to 3 sentences; each sentence shares at least 30 percent of its content words with the risk's own span; every number and name in it occurs in that text or on the page; a stated mitigation shares at least half its content words with the page. Thresholds and matching are identical in both backends. Only the language primitives differ:

| Primitive | `regex` (default) | `spacy` (`en_core_web_sm` 3.8) |
| --- | --- | --- |
| Sentences | split after `.!?` before a capital letter | the dependency parser's sentence boundaries |
| Content words | lower-cased surface forms, a fixed 40-word stop list | lemmas, spaCy's stop list |
| Names | capitalised words after the first word | entities labelled ORG, GPE, LOC, PERSON, NORP, LAW, PRODUCT, EVENT, FAC |
| Numbers | digit runs | tokens that look like numbers and contain a digit |

The backend is chosen with `etl.py --grounding {regex,spacy}` or `GROUNDING_NLP`, and recorded on the run record (`grounding_failures.nlp`) and in `run.json`.

## Method

`eval/compare_grounding.py` makes no model calls:

1. **Recorded output.** For each of the five recorded runs in `eval/runs/`, identify, describe, merge and enrich are replayed from the run's own recordings, and both backends check the same first-pass records, before any repair.
2. **Seeded cases**, on the baseline's nine records, each with a known answer. Must be flagged: an invented number appended, an invented name appended, an off-topic sentence appended. Must not be flagged: the span's own first two sentences with plural words made singular. A case counts when it adds a problem the unmodified record did not have.
3. **Sentence counting** on eight short texts with a known count, built around abbreviations and amounts.

A live end-to-end run with spaCy (`eval/runs/exp-grounding-spacy`) was recorded the same day as the baseline, with the same code, prompts and model.

## Results

**Recorded output: 45 first-pass records, the same verdict on all 45, the same problem list on 44.**

| Run | Records | Flagged by regex | Flagged by spaCy |
| --- | --- | --- | --- |
| baseline | 9 | 3 | 3 |
| reg-broken-parser | 9 | 2 | 2 |
| reg-prompt-no-mitigation | 9 | 3 | 3 |
| reg-weak-model | 9 | 5 | 5 |
| exp-grounding-spacy | 9 | 2 | 2 |

The one difference is the weak model's "Carbon taxes on GHG-intensive materials": regex also reports `name_not_in_text:GHG-intensive`, a capitalised compound rather than a name; spaCy does not. Both flag the record's second sentence as ungrounded, so the verdict is the same.

**Seeded cases: identical.**

| Case (9 records) | regex | spaCy |
| --- | --- | --- |
| Invented number, flagged | 9 | 9 |
| Invented name, flagged | 9 | 9 |
| Off-topic sentence, flagged | 6 | 6 |
| Singular forms, wrongly flagged | 0 | 0 |

The three off-topic misses are a limit of the check, not of either backend: the appended sentence shares enough ordinary words with a long span to clear the 30 percent floor. The same floor is why lemmas do not matter: turning plurals singular never moves a sentence below it.

**Sentence counting: 6 of 8 each, wrong on different texts.** Regex splits after "U.S." and "St." before a capital. spaCy's small model keeps "Costs could reach EUR 40m. This affects margins in 2027." as one sentence and splits after "approx.".

**End to end: the same records and scores.** Both live runs produced nine records with the corruption row pending review for an ungrounded second sentence, and the same five evaluator scores (1.00, 1.00, 0.89, 1.00, 1.00). The baseline made 17 calls (three repairs), the spaCy run 16 (two). Part 1 shows both backends flagged the same three first-pass records in the baseline and the same two in the spaCy run, so the difference in repairs is sampling variance between the two live runs, not the backend.

**Cost.** spaCy loads in 0.6 s and checks a record in 29 ms against 0.6 ms for regex, about fifty times slower but under a second per report against 35 s of model time. It adds about 190 MB of packages (spaCy 122 MB, blis 34 MB, thinc 15 MB, the model 15 MB); they sit in the `nlp` dependency group, which the Docker image does not install.

## Decision

The regex checks stay the default. On this report spaCy gives the same verdicts, catches the same seeded failures and counts sentences no better, for a large dependency and slower checks. It removes one kind of false flag (capitalised compounds read as names), seen once in 45 records. The spaCy backend stays in the code as a recorded, switchable attempt.

What the comparison does show is where T4 is actually weak: a sentence that reuses the span's vocabulary but states something the report does not say passes both backends. Word-level NLP, hand-rolled or spaCy, cannot see that; an entailment check against the span can, at the cost of a model per sentence.

What would change the decision: a second report where capitalised compounds or abbreviations cause real false flags; or named entities becoming part of the product (an `entities` table so clients can ask about exposure to a country or a regulation), where spaCy earns its place in T5 rather than in T4.

## Limits

One report and one spaCy model (the small one). The seeded cases and sentence texts are written by hand for this comparison, so they test the mechanics of the checks, not how often each failure occurs in real model output.

## Reproduce

```sh
uv sync                                                                                      # dev group, includes nlp
uv run python eval/compare_grounding.py eval/runs/baseline eval/runs/reg-weak-model eval/runs/reg-broken-parser eval/runs/reg-prompt-no-mitigation eval/runs/exp-grounding-spacy --out eval/grounding_comparison.json
uv run python etl.py --extract --transform --run-id my-spacy-run --grounding spacy           # live, with the model server
```
