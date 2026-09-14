"""T4 validate and repair per record; T6 validate the transform as a set (SPECS.md > Validation points)."""

from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from pathlib import Path

from shared.config import GROUNDING_PASS_MIN
from shared.runrecord import RunRecord
from shared.schema import Category, DescribeOutput, ParseResult, RiskRecord
from shared.llm import LLMClient, ReplayMiss, load_prompt

STOP = set("the a an and or of to in on for with by as at from that this these those is are be may can could might our we its it their they which such also than more not no into over across".split())
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
NUMBER = re.compile(r"\b\d[\d.,%]*\b")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace("’", "'"))).strip()


def _content_words(s: str) -> set[str]:
    return {w for w in _norm(s).split() if w not in STOP and len(w) > 2}


def grounding_problems(rec: RiskRecord, page_text: str, citation_text: str = "") -> list[str]:
    """T4 grounding: span on page; sentences share content with the span; numbers and names in the span; mitigation matches."""
    problems = []
    page_norm = _norm(page_text)
    if _norm(rec.verbatim_span)[:100] not in page_norm:
        problems.append("span_not_on_page")
    context = _norm(" ".join(filter(None, [rec.verbatim_span, rec.potential_impact or "", " ".join(c.span for c in rec.citations)])))
    context_words = set(context.split())
    sentences = [s for s in SENTENCE.split(rec.description.strip()) if s.strip()]
    if not 2 <= len(sentences) <= 3:
        problems.append(f"sentence_count:{len(sentences)}")
    for k, s in enumerate(sentences):
        words = _content_words(s)
        if words and len(words & context_words) / len(words) < 0.3:
            problems.append(f"sentence_{k + 1}_ungrounded")
        for num in NUMBER.findall(s):
            if _norm(num) and _norm(num) not in context and _norm(num) not in page_norm:
                problems.append(f"number_not_in_text:{num}")
        for name in [w.strip(",.;:()") for w in s.split()[1:] if w[:1].isupper() and len(w.strip(",.;:()")) > 2]:
            if _norm(name) and _norm(name) not in context and _norm(name) not in page_norm:
                problems.append(f"name_not_in_text:{name}")
    if rec.mitigation:
        words = _content_words(rec.mitigation)
        pool = set(page_norm.split()) | set(_norm(citation_text).split())
        if words and len(words & pool) / len(words) < 0.5:
            problems.append("mitigation_not_in_text")
    return problems


def validate_and_repair(records: list[RiskRecord], parsed: ParseResult, record: RunRecord, client: LLMClient | None) -> list[RiskRecord]:
    """T4: check every record; on failure retry the describe call once with the problems attached; then flag."""
    system = load_prompt("describe", client.prompt_version) if client else ""
    out: list[RiskRecord] = []
    failures, repaired = [], []
    for rec in records:
        page_text = parsed.page_text.get(rec.page, "")
        citation_text = " ".join(parsed.page_text.get(c.page, "") for c in rec.citations)
        problems = grounding_problems(rec, page_text, citation_text)
        if problems and client is not None:
            printed_title = rec.verbatim_title or rec.title
            retry_user = (f"Your previous record for the risk '{printed_title}' failed these checks: {', '.join(problems)}. "
                          f"Rewrite it so that every sentence, number and name is supported by the text below, and write exactly 2 to 3 sentences. Keep the category as it was.\n\n"
                          f"Title as printed: {printed_title}\nDescription as printed:\n{rec.verbatim_span}\n"
                          + (f"\nPotential impact as printed:\n{rec.potential_impact}\n" if rec.potential_impact else "")
                          + (f"\nHow we manage it, as printed:\n{rec.stated_mitigation}\n" if rec.stated_mitigation else "\nThe text states no mitigation.\n"))
            try:
                fixed, _ = client.complete(f"repair-{rec.id}", system, retry_user, DescribeOutput)
            except ReplayMiss:  # checks changed since the recording: keep the record, say so, do not crash a replay
                problems = problems + ["repair_not_recorded"]
                fixed = None
            candidate = rec if fixed is None else rec.model_copy(update={"title": fixed.title, "description": fixed.description,
                                               "mitigation": fixed.mitigation if rec.stated_mitigation else rec.mitigation})
            new_problems = grounding_problems(candidate, page_text, citation_text) if fixed is not None else problems
            if fixed is not None and not new_problems:  # a repair counts only when nothing is left to flag
                rec, problems = candidate, new_problems
                repaired.append(rec.id)
        if problems:
            rec = rec.model_copy(update={"quality_flags": rec.quality_flags + [f"grounding:{p}" for p in problems],
                                         "review_state": "pending_review"})
            failures.append((rec.id, problems))
        out.append(rec)
    rate = 1 - len(failures) / max(1, len(records))
    record.add("transform", "grounding_failures", "ok" if rate >= GROUNDING_PASS_MIN else "warning", count=len(failures),
               failures=failures, repaired=repaired, pass_rate=round(rate, 3), threshold=GROUNDING_PASS_MIN)
    return out


def validate_transform(records: list[RiskRecord], candidates: int, merges: list, parsed: ParseResult, record: RunRecord,
                       replay_records: list[RiskRecord] | None = None) -> str:
    """T6: set-level checks and pipeline reproducibility. Evaluators run separately (eval/run_eval.py) and write eval_scores."""
    problems = []
    if len(records) != candidates - len(merges):
        problems.append(f"count:{len(records)}!={candidates}-{len(merges)}")
    ids = Counter(r.canonical_risk_id for r in records)
    dup = [k for k, v in ids.items() if v > 1]
    if dup:
        problems.append(f"duplicate_canonical_ids:{dup}")
    for r in records:
        if not any(_norm(c.span)[:100] in _norm(parsed.page_text.get(c.page, "")) for c in r.citations):
            problems.append(f"no_citation_on_page:{r.id}")
        if r.category not in set(Category):
            problems.append(f"category_not_in_enum:{r.id}")
    record.add("transform", "transform_set_checks", "error" if problems else "ok", count=len(problems), problems=problems,
               records=len(records))
    if replay_records is not None:
        same = json.dumps([r.model_dump(mode="json") for r in records], sort_keys=True) == json.dumps(
            [r.model_dump(mode="json") for r in replay_records], sort_keys=True)
        record.add("transform", "pipeline_reproducibility", "ok" if same else "error", count=0 if same else 1,
                   note="the post-model code replayed over this run's own recordings gives the same records; provider variance is not measured here")
    return record.status("transform")
