"""The five evaluators against the golden set (SPECS.md > Validation points, T6 evaluators; DESIGN.md).

identification  precision and recall of the record set against the golden risks (fuzzy title or alias match)
provenance      exact section and page for every matched record
grounding       every golden key phrase appears in the matched record's own text (description, span, mitigation)
category        primary category equals the golden category (or an acceptable alternative)
fields          2-3 sentence description; mitigation present iff the golden set says it is stated

Each evaluator returns a score in [0, 1] and a pass flag against its threshold, plus the items that failed.
Regressions the brief names map to evaluators that move: a broken parser fails grounding and provenance;
a weaker model fails category; a prompt that drops mitigation fails fields.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
THRESHOLDS = {"identification": 0.9, "provenance": 0.9, "grounding": 0.8, "category": 0.8, "fields": 0.8}


@dataclass
class EvalResult:
    name: str
    score: float
    passed: bool
    failures: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower().replace("’", "'"))).strip()


def load_golden(path: Path) -> dict:
    return json.loads(path.read_text())


def match_records(golden: dict, records: list[dict]) -> dict[str, dict | None]:
    """golden_id -> best matching record (fuzzy title/alias >= 0.6 or key phrases in the span), one record per golden risk."""
    taken: set[str] = set()
    out: dict[str, dict | None] = {}
    for g in golden["risks"]:
        names = [g["title"]] + g.get("aliases", [])
        best, best_score = None, 0.0
        for r in records:
            if r["id"] in taken:
                continue
            title_score = max(difflib.SequenceMatcher(None, _norm(n), _norm(r["title"])).ratio() for n in names)
            span_hits = sum(_norm(k) in _norm(r.get("verbatim_span", "")) for k in g["key_phrases"]) / max(1, len(g["key_phrases"]))
            citation_titles = [_norm(c.get("span", ""))[:40] for c in r.get("citations", [])]
            score = max(title_score, 0.6 * span_hits + 0.4 * title_score)
            if r.get("page") == g["page"] and span_hits >= 0.66:
                score = max(score, 0.85)
            if score > best_score:
                best, best_score = r, score
        if best is not None and best_score >= 0.6:
            out[g["golden_id"]] = best
            taken.add(best["id"])
        else:
            out[g["golden_id"]] = None
    return out


def evaluate(golden: dict, records: list[dict]) -> list[EvalResult]:
    matches = match_records(golden, records)
    n_gold = len(golden["risks"])
    matched = {k: v for k, v in matches.items() if v is not None}
    unmatched_records = [r["id"] for r in records if r["id"] not in {v["id"] for v in matched.values()}]

    recall = len(matched) / n_gold
    precision = len(matched) / max(1, len(records))
    f1 = 0.0 if not matched else 2 * precision * recall / (precision + recall)
    results = [EvalResult("identification", round(f1, 3), recall >= THRESHOLDS["identification"] and precision >= THRESHOLDS["identification"],
                          failures=[f"missing:{k}" for k, v in matches.items() if v is None] + [f"extra:{r}" for r in unmatched_records],
                          detail={"precision": round(precision, 3), "recall": round(recall, 3), "expected": n_gold, "records": len(records)})]

    gold_by_id = {g["golden_id"]: g for g in golden["risks"]}

    def per_match(name: str, check):
        fails, ok = [], 0
        for gid, rec in matched.items():
            g = gold_by_id[gid]
            problems = check(g, rec)
            if problems:
                fails.append((gid, problems))
            else:
                ok += 1
        score = ok / max(1, len(matched)) if matched else 0.0
        results.append(EvalResult(name, round(score, 3), score >= THRESHOLDS[name], failures=fails))

    def provenance(g, r):
        pages = {c["page"] for c in r.get("citations", [])} | {r["page"]}
        problems = []
        if g["page"] not in pages:
            problems.append(f"page:{r['page']}!={g['page']}")
        if r.get("section") != g["section"] and not any(c["section"] == g["section"] for c in r.get("citations", [])):
            problems.append(f"section:{r.get('section')}!={g['section']}")
        if g.get("also_on_page") and g["also_on_page"] not in pages:
            problems.append(f"missing_citation_page:{g['also_on_page']}")
        return problems

    def grounding(g, r):
        own = _norm(" ".join([r.get("description", ""), r.get("verbatim_span", ""), r.get("mitigation") or "",
                              " ".join(c.get("span", "") for c in r.get("citations", []))]))
        return [f"phrase_missing:{k}" for k in g["key_phrases"] if _norm(k) not in own]

    def category(g, r):
        return [] if r.get("category") in g.get("acceptable_categories", [g["category"]]) else [f"category:{r.get('category')}!={g['category']}"]

    def fields(g, r):
        problems = []
        n = len([s for s in SENTENCE.split((r.get("description") or "").strip()) if s.strip()])
        if not 2 <= n <= 3:
            problems.append(f"sentences:{n}")
        has = bool(r.get("mitigation"))
        if has != g["mitigation_stated"]:
            problems.append(f"mitigation_present:{has}!={g['mitigation_stated']}")
        if has and g.get("mitigation_phrases"):
            m = _norm(r["mitigation"])
            if not any(_norm(p) in m for p in g["mitigation_phrases"]):
                problems.append("mitigation_phrases_missing")
        return problems

    per_match("provenance", provenance)
    per_match("grounding", grounding)
    per_match("category", category)
    per_match("fields", fields)
    return results


def evaluate_intents(golden: dict, parsed: list[dict]) -> EvalResult:
    """A3 intent: category and filter agreement, field by field, over the question golden set."""
    fails, ok = [], 0
    for q, got in zip(golden["questions"], parsed):
        exp = q["intent"]
        problems = []
        if set(got.get("categories", [])) != set(exp["categories"]):
            problems.append(f"categories:{got.get('categories')}!={exp['categories']}")
        for k in ("source_register", "status"):
            if (got.get(k) or None) != (exp.get(k) or None):
                problems.append(f"{k}:{got.get(k)}!={exp.get(k)}")
        if bool(exp.get("sector")) != bool(got.get("sector")):
            problems.append(f"sector:{got.get('sector')}!={exp.get('sector')}")
        if {c.lower() for c in got.get("companies", [])} != {c.lower() for c in exp["companies"]}:
            problems.append(f"companies:{got.get('companies')}!={exp['companies']}")
        if problems:
            fails.append((q["question"][:60], problems))
        else:
            ok += 1
    score = ok / max(1, len(golden["questions"]))
    return EvalResult("intent", round(score, 3), score >= 0.8, failures=fails)
