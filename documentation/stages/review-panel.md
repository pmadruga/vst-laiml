# Review panel, 2026-09-13

Five independent reviews of the submission against the brief: brief compliance, code quality, product thinking, evaluation rigour, and a mock interview panel. This is the synthesis, ranked by how much each item would cost in the walkthrough. Nothing here has been changed yet.

## Must fix before submitting

1. **DESIGN.md lost the two things the brief names.** After the shortening passes it has no trade-offs section tracing to PLAN.md and no scaling section (latency, cost, throughput across many reports). The brief asks for both explicitly. Add a short trade-offs list (register-first vs model-first identification, coordinate parser vs Docling, local 20B vs hosted model, SQLite vs Postgres, one call per risk vs one per page), each naming the PLAN.md heading it serves, and a scaling paragraph with the measured numbers: about 20 calls, 15k tokens and 45 s per report on a local 20B model, so 200 reports in under three hours on one GPU, with parser coverage and review load as the real constraints, not tokens.
2. **`risk_status` can never say "new".** The view's `WHERE EXISTS` requires the same canonical risk in the prior year, which is exactly the case where the status is not "new". Brief question 2 silently drops every new risk. One-line SQL fix plus a two-report test fixture.
3. **Canonical ids come from the model's title.** The baseline and the weak-model run give different ids for the same risk, so year-over-year linking and the merge itself depend on model phrasing. Slug the register's verbatim title and taxonomy code instead; use title similarity only as a recorded fallback.
4. **The golden set is unconfirmed and partly post-hoc.** `labelled_by` still says "Pedro (to confirm)", and several aliases equal model titles from the runs. Review the nine entries, sign them with name and date, freeze them in a commit, and say in the README that the aliases were widened after the first run.
5. **Category and intent scores are partly circular.** The describe prompt's mapping rule names the hard cases of this report and their categories; the intent prompt encodes the five golden questions, and the run record shows intent going 0.40, 0.40, 1.00 as rules were added. State this plainly: category and intent are in-distribution compliance checks, and the next report is the held-out test. Better, add three or four risks and questions no prompt mentions.

## Should fix

6. **Mitigation is null for six of nine risks by construction**, while the brief offers p.118 and pp.85–92, which the pipeline parses and never uses. At minimum say so in DESIGN.md; better, a deterministic lookup of the cyber mitigation on p.118 with its own citation.
7. **The repair step grounds against model output.** It presents the model's own title and mitigation as "as printed" because the register's `stated_mitigation` and `verbatim_title` are dropped after merge; it also accepts a repair that still fails and swaps category without the vote. Carry the register fields on the record, require zero problems, keep category fixed on repair.
8. **The T6 count check is tautological** (merges computed as candidates minus records, then checked against it). Return the merge pairs from merge and count those.
9. **Evaluators are lenient in ways a wrong record can exploit.** Grounding searches key phrases across span and citations, which are parser output, so a fabricated description with a correct span scores 1.0. Score grounding on description plus mitigation only, use distinctive phrases, replace greedy matching with optimal assignment. State thresholds as "at most k of 9 misses" with a reason rather than ratios.
10. **The replay determinism check is misdescribed.** It replays the run's own recordings, so it proves the post-model code is deterministic, not the provider. Rename it "pipeline reproducibility" in SPECS.md.
11. **API robustness.** Unescaped quotes in FTS queries return a 500; `status` is a free string and errors inside the handler; `limit` is unbounded; exception text leaks on `/ask`. Small fixes each.
12. **Documents outrun the code.** SPECS.md promises evaluators inside T6, a query log, `record_schema_failures` and `api_schema_version` rows, and T5's third marker source; none exist. README cites `src/pipeline/schema.py` (now `src/shared/schema.py`); CLAUDE.md cites DESIGN.md sections that no longer exist. Mark each as deferred or implement it.
13. **PLAN.md wording.** Two users collapsed into "the same API" with no mention of the analyst review that the design builds; two assumptions are values or decisions; the optimisation target is hedged then retracted; the deferred section is only a link. The product review has a rewrite for each sentence. Also explain the two reversals from notes.md: multi-model consensus dropped, and who labels the golden set.
14. **STRETCH.md** has an empty "Human in the loop" heading and lacks the items DESIGN.md says are there (auth, scoping, alerting, writes). Fill it as a ranked list with triggers or delete the heading.
15. **Hygiene.** The shipped baseline `final.json` carries `repair_not_recorded`, revealing it was regenerated in replay; re-record it live once. The run record appends on every invocation, so extract rows appear three times. `identify.py` hardcodes the page list. The Dockerfile copies `src` before `uv sync`, defeating the cache.

## For the walkthrough

Lead with: the broken-parser run, where every internal check passes and only the golden set catches it; the rule that the model never touches the PDF, only blocks with provenance, and why the coordinate parser stays even though a page-fed model could supply page numbers; the record/replay client that makes every number reproducible offline; the run record as the generalisation detector, with the 2024 and 2023 trials as evidence of what it reports; and the weak-model result framed as movement, not failure.

Concede without being asked: single-report configuration; the golden set's authorship; the prompt containing this report's hard cases; six null mitigations; T5 not built; the commit history not preserving attempts.

The mock panel's fifteen questions with model answers are in the evaluation and interview reports produced by this review; the ones most likely to come first are the second-report question, golden-set authorship, and the mapping rule in the prompt.
