"""T3: the same risk in two registers becomes one record with all citations (SPECS.md > TRANSFORM)."""

from __future__ import annotations

import difflib
import re

from shared.config import COMPANY, REPORT
from shared.runrecord import RunRecord
from shared.schema import CandidateRisk, Citation, DescribedRisk, RiskRecord

MERGE_TITLE_SIM = 0.55
KEYWORD_HINTS = {"cyber": {"cyber"}, "corruption": {"corruption", "bribery"}}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower())


def _same_risk(a: CandidateRisk, da: DescribedRisk, b: CandidateRisk, db: DescribedRisk) -> bool:
    if a.source_register == b.source_register:
        return False  # only cross-register duplicates merge
    ta, tb = _norm(da.output.title), _norm(db.output.title)
    if difflib.SequenceMatcher(None, ta, tb).ratio() >= MERGE_TITLE_SIM:
        return True
    va, vb = _norm(a.verbatim_title), _norm(b.verbatim_title)
    return any(k <= set(va.split()) and k <= set(vb.split()) for k in KEYWORD_HINTS.values())


def merge(candidates: list[CandidateRisk], described: list[DescribedRisk], record: RunRecord, run_id: str,
          model: str, prompt_version: str) -> list[RiskRecord]:
    by_id = {c.candidate_id: c for c in candidates}
    desc = {d.candidate_id: d for d in described}
    ordered = sorted(candidates, key=lambda c: (c.prominence, c.page, c.candidate_id))  # ERM first: it keeps the record
    used: set[str] = set()
    records: list[RiskRecord] = []
    merges: list[tuple[str, str]] = []
    n = 0
    for c in ordered:
        if c.candidate_id in used:
            continue
        used.add(c.candidate_id)
        d = desc[c.candidate_id]
        citations = [Citation(section=c.section, page=c.page, source_register=c.source_register, span=c.verbatim_span)]
        for o in ordered:
            if o.candidate_id in used:
                continue
            if _same_risk(c, d, o, desc[o.candidate_id]):
                used.add(o.candidate_id)
                merges.append((c.candidate_id, o.candidate_id))
                citations.append(Citation(section=o.section, page=o.page, source_register=o.source_register, span=o.verbatim_span))
        n += 1
        title = d.output.title
        records.append(RiskRecord(
            id=f"{REPORT['id']}-r{n:02d}", report_id=REPORT["id"], canonical_risk_id=f"{COMPANY['id']}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}",
            title=title, description=d.output.description, category=d.output.category,
            secondary_categories=d.output.secondary_categories, source_register=c.source_register, source_taxonomy=c.source_taxonomy,
            section=c.section, page=c.page, citations=citations, potential_impact=c.potential_impact,
            mitigation=d.output.mitigation, prominence=c.prominence, verbatim_span=c.verbatim_span,
            confidence=d.output.confidence, poor_fit=d.output.poor_fit,
            quality_flags=[f"poor_fit:{d.output.poor_fit_reason}"] if d.output.poor_fit else [],
            model=model, prompt_version=prompt_version, run_id=run_id))
    record.add("transform", "merge", "ok", count=len(merges), merged=merges, records=len(records), candidates=len(candidates))
    return records
