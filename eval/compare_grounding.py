"""Compare the two T4 grounding backends, regex (hand-rolled) and spaCy, on the same model output. No model calls.

    uv run python eval/compare_grounding.py eval/runs/baseline eval/runs/reg-weak-model --out eval/grounding_comparison.json

1. Recorded output: for each run, the first-pass records (identify, describe, merge and enrich replayed from the run's
   own recordings, before any repair) are checked by both backends; problems are listed per record.
2. Seeded cases on the first run's records, each with a known answer. Must be flagged: an invented number, an invented
   name, an off-topic sentence. Must not be flagged: the span's own sentences with plural words made singular.
3. Sentence counting on short texts with a known count (abbreviations, amounts), since the brief asks for 2 to 3 sentences.

The seeded cases and sentence texts are written by hand for this comparison: they measure the checks' mechanics,
not how often each failure occurs in real model output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

from pipeline.transform.describe import describe
from pipeline.transform.enrich import enrich_mitigations
from pipeline.transform.identify import identify
from pipeline.transform.merge import merge
from pipeline.transform.validate import SENTENCE, get_nlp, grounding_problems
from shared.llm import LLMClient
from shared.runrecord import RunRecord
from shared.schema import ParseResult, RiskRecord

BACKENDS = ("regex", "spacy")

SENTENCE_CASES = [  # (text, sentences)
    ("Tariffs imposed by the U.S. Government raise costs. Margins fall.", 2),
    ("Costs could reach EUR 40m. This affects margins in 2027.", 2),
    ("Steel prices rise, e.g. for towers and nacelles. Suppliers pass on costs. Margins fall.", 3),
    ("Vestas Wind Systems A/S operates in 80 countries. Its exposure to St. Louis is limited.", 2),
    ("Delays of approx. 6 months are possible. They raise costs.", 2),
    ("Revenue was EUR 17.3bn in 2025. Growth slowed. Orders rose 5.2 percent.", 3),
    ("Cyber attacks may disrupt operations. No. 1 priority is prevention. Controls are tested.", 3),
    ("The risk is reviewed by the Board. It is also reviewed by the Audit Committee.", 2),
]

INVENTED = {
    "invented_number": " This could cost EUR 470 million by 2031.",
    "invented_name": " Siemens Gamesa and the Brazilian government are named as the main counterparties.",
    "off_topic_sentence": " Management also expects strong growth in its solar panel and battery storage business.",
}


def first_pass_records(run_dir: Path) -> tuple[list[RiskRecord], ParseResult]:
    parsed = ParseResult.model_validate_json((run_dir / "parse.json").read_text())
    meta = json.loads((run_dir / "run.json").read_text())
    d = Path(tempfile.mkdtemp(prefix="grounding-compare-"))
    rec = RunRecord("compare", "vestas-2025", d)
    client = LLMClient(d, model=meta["model"], prompt_version=meta["prompt_version"], replay_dir=run_dir)
    ident = identify(parsed, rec, client)
    described = describe(ident, rec, client)
    records, _ = merge(ident.candidates, described, rec, "compare", meta["model"], meta["prompt_version"])
    return enrich_mitigations(records, parsed, rec), parsed


def check(rec: RiskRecord, parsed: ParseResult, backend: str) -> list[str]:
    citation_text = " ".join(parsed.page_text.get(c.page, "") for c in rec.citations)
    return grounding_problems(rec, parsed.page_text.get(rec.page, ""), citation_text, get_nlp(backend))


def kinds(problems: list[str]) -> set[str]:
    return {re.sub(r"^(sentence)_\d+_", r"\1_", p.split(":")[0]) for p in problems}


def singularise(text: str) -> str:
    return re.sub(r"\b([a-z]{4,}[^su])s\b", r"\1", text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    t0 = time.perf_counter()
    get_nlp("spacy")
    report: dict = {"spacy_load_s": round(time.perf_counter() - t0, 2), "runs": {}, "seeded": {}, "sentences": {}}
    timings = {b: 0.0 for b in BACKENDS}
    checks = 0

    # 1. recorded output
    base_records, base_parsed = None, None
    for run_dir in args.runs:
        records, parsed = first_pass_records(run_dir)
        base_records, base_parsed = (records, parsed) if base_records is None else (base_records, base_parsed)
        rows = []
        for r in records:
            row = {"id": r.id, "title": r.title}
            for b in BACKENDS:
                t = time.perf_counter()
                row[b] = check(r, parsed, b)
                timings[b] += time.perf_counter() - t
            checks += 1
            rows.append(row)
        report["runs"][str(run_dir)] = {
            "records": len(rows),
            "flagged": {b: sum(bool(x[b]) for x in rows) for b in BACKENDS},
            "same_verdict": sum(bool(x["regex"]) == bool(x["spacy"]) for x in rows),
            "same_problems": sum(sorted(x["regex"]) == sorted(x["spacy"]) for x in rows),
            "rows": rows,
        }

    # 2. seeded cases on the first run's records
    seeded = {name: {b: 0 for b in BACKENDS} for name in [*INVENTED, "singular_forms_false_flag"]}
    cases = 0
    for r in base_records:
        for b in BACKENDS:
            before = kinds(check(r, base_parsed, b))
            for name, extra in INVENTED.items():
                bad = r.model_copy(update={"description": r.description.rstrip() + extra})
                if kinds(check(bad, base_parsed, b)) - before:
                    seeded[name][b] += 1
        span_sentences = [s for s in SENTENCE.split(r.verbatim_span.strip()) if s.strip()][:2]
        if len(span_sentences) < 2 and r.potential_impact:
            span_sentences.append([s for s in SENTENCE.split(r.potential_impact.strip()) if s.strip()][0])
        plain = r.model_copy(update={"description": " ".join(span_sentences)})
        singular = r.model_copy(update={"description": singularise(" ".join(span_sentences))})
        if singular.description == plain.description:
            continue
        cases += 1
        for b in BACKENDS:
            if kinds(check(singular, base_parsed, b)) - kinds(check(plain, base_parsed, b)):
                seeded["singular_forms_false_flag"][b] += 1
    report["seeded"] = {"records": len(base_records), "singular_cases": cases, "counts": seeded}

    # 3. sentence counting
    for b in BACKENDS:
        nlp = get_nlp(b)
        got = [len(nlp.sentences(text)) for text, _ in SENTENCE_CASES]
        report["sentences"][b] = {"correct": sum(g == n for g, (_, n) in zip(got, SENTENCE_CASES)), "cases": len(SENTENCE_CASES),
                                  "wrong": [(text, n, g) for g, (text, n) in zip(got, SENTENCE_CASES) if g != n]}
    report["ms_per_record"] = {b: round(1000 * timings[b] / max(1, checks), 1) for b in BACKENDS}

    print(f"spaCy load {report['spacy_load_s']} s; check time per record: " + ", ".join(f"{b} {v} ms" for b, v in report["ms_per_record"].items()))
    print("\nrecorded output (first pass, before repair)")
    for run, r in report["runs"].items():
        print(f"  {run}: {r['records']} records; flagged regex {r['flagged']['regex']}, spacy {r['flagged']['spacy']}; "
              f"same verdict {r['same_verdict']}, same problems {r['same_problems']}")
        for row in r["rows"]:
            if row["regex"] != row["spacy"]:
                print(f"    {row['id']} {row['title'][:40]:<40} regex {row['regex']}\n{'':>50}spacy {row['spacy']}")
    print(f"\nseeded cases on {report['seeded']['records']} records ({cases} singular-form cases)")
    for name, c in seeded.items():
        print(f"  {name:<26} regex {c['regex']:>2}  spacy {c['spacy']:>2}")
    print("\nsentence counting")
    for b, s in report["sentences"].items():
        print(f"  {b}: {s['correct']}/{s['cases']} correct; wrong: {s['wrong']}")
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
