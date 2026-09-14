"""T5 (deterministic part): mitigation for ESRS risks from the topical sections the brief offers (p.118, pp.85-92).

The ESRS register rows state no mitigation. The topical sections describe each IRO in a fixed pattern:
"<IRO name> ... Type of impact: ... Description: ..." followed on the same or next page by an
"Actions and resources" paragraph (the MDR-A disclosure). When a record's register name is found in
one of those blocks, the actions paragraph becomes the record's mitigation, with its own page citation
and a quality flag saying where it came from. Nothing is inferred; text is quoted from the page.
"""

from __future__ import annotations

import re

from shared.runrecord import RunRecord
from shared.schema import Citation, ParseResult, Register, RiskRecord

ACTIONS = re.compile(r"Actions and resources\s*(?P<body>.+?)(?=(?:\n[A-Z][^\n]{0,60}\n(?:Type of impact|MDR-|[EGS]\d-\d))|\Z)", re.S)
MAX_CHARS = 700


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace("’", "'"))).strip()


def _actions_paragraph(text: str) -> str | None:
    m = ACTIONS.search(text)
    if not m:
        return None
    body = " ".join(m.group("body").split())
    body = re.sub(r"\s*-\s(?=[a-z])", "", body)  # re-join words hyphenated at line ends
    if len(body) > MAX_CHARS:
        cut = body[:MAX_CHARS]
        body = cut[: cut.rfind(". ") + 1] or cut
    return body.strip() or None


def enrich_mitigations(records: list[RiskRecord], parsed: ParseResult, record: RunRecord) -> list[RiskRecord]:
    topical = [b for b in parsed.blocks if b.strategy == "plain_text"]
    by_page = {b.page: b for b in topical}
    out, enriched = [], []
    for rec in records:
        if rec.mitigation or rec.source_register != Register.ESRS_FINANCIAL_RISK:
            out.append(rec)
            continue
        candidates = [rec.verbatim_title or "", rec.title]  # the register's own heading first, the model's title second
        found = None
        for b in topical:
            page_norm = _norm(parsed.page_text.get(b.page, b.text))
            for cand in candidates:
                key = _norm(cand)
                if key and key in page_norm and "type of impact" in page_norm:
                    found = b
                    break
            if found:
                break
        if not found:
            out.append(rec)
            continue
        para = None
        for page in (found.page, found.page + 1):
            blk = by_page.get(page)
            if blk:
                para = _actions_paragraph(parsed.page_text.get(page, blk.text))
                if para:
                    page_used = page
                    break
        if not para:
            out.append(rec)
            continue
        out.append(rec.model_copy(update={
            "mitigation": para,
            "citations": rec.citations + [Citation(section=found.section, page=page_used, source_register=Register.ESRS_FINANCIAL_RISK, span=para[:200])],
            "quality_flags": rec.quality_flags + [f"mitigation_from_topical_section:p{page_used}"],
        }))
        enriched.append((rec.id, page_used))
    record.add("transform", "mitigation_enriched", "ok", count=len(enriched), records=enriched, strategy="topical_actions_paragraph")
    return out
