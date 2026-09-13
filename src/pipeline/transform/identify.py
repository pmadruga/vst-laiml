"""T1: candidate risks with verbatim spans (SPECS.md > TRANSFORM).

Two strategies, both run. The register strategy is deterministic: p.51 columns and the ESRS rows
whose marker is "risk". The LLM strategy proposes candidates from the section text against a
written definition; each proposal must quote a span that exists on the page. The register result
is what continues; the agreement between the two is recorded (T1 agreement).
"""

from __future__ import annotations

import difflib
import re

from shared.config import IDENTIFY_AGREEMENT_MIN
from shared.runrecord import RunRecord
from shared.schema import CandidateRisk, IdentifyResult, LLMCandidateList, ParseResult, Register
from shared.llm import LLMClient, load_prompt


def register_candidates(parsed: ParseResult) -> list[CandidateRisk]:
    out: list[CandidateRisk] = []
    for b in parsed.blocks:
        if b.marker != "risk" or b.source_register is None:
            continue
        if b.source_register == Register.ERM_MAIN_RISK:
            span = b.fields.get("description") or b.text
            out.append(CandidateRisk(candidate_id=b.block_id, strategy="register", source_register=b.source_register,
                                     section=b.section, page=b.page, pdf_index=b.pdf_index, verbatim_title=b.heading,
                                     verbatim_span=span, potential_impact=b.fields.get("potential_impact") or None,
                                     stated_mitigation=b.fields.get("how_we_manage_it") or None, prominence=1))
        else:
            out.append(CandidateRisk(candidate_id=b.block_id, strategy="register", source_register=b.source_register,
                                     section=b.section, page=b.page, pdf_index=b.pdf_index, source_taxonomy=b.source_taxonomy,
                                     sub_topic=b.sub_topic, verbatim_title=b.heading,
                                     verbatim_span=b.fields.get("description") or b.text, value_chain=b.value_chain, prominence=2))
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s.lower())).strip()


def llm_candidates(parsed: ParseResult, client: LLMClient, pages: tuple[int, ...] = (51, 71, 72, 73, 74)) -> list[CandidateRisk]:
    """Ask the model for principal risks per page; keep proposals whose span exists on the page."""
    system = load_prompt("identify", client.prompt_version)
    out: list[CandidateRisk] = []
    blocks_by_page: dict[int, list] = {}
    for b in parsed.blocks:
        blocks_by_page.setdefault(b.page, []).append(b)
    for page_no in pages:
        text = parsed.page_text.get(page_no)
        if not text:
            continue
        result, call_id = client.complete(f"identify-p{page_no}", system, f"Report page {page_no}:\n\n{text}", LLMCandidateList)
        page_norm = _norm(text)
        blocks = blocks_by_page.get(page_no, [])
        for k, c in enumerate(result.candidates):
            if _norm(c.span)[:80] not in page_norm:
                continue  # span not on the page: dropped, never trusted
            out.append(CandidateRisk(candidate_id=f"llm-p{page_no}-{k + 1}", strategy="llm", source_register=None,
                                     section=blocks[0].section if blocks else "unknown", page=page_no,
                                     pdf_index=blocks[0].pdf_index if blocks else 0, verbatim_title=c.title,
                                     verbatim_span=c.span, prominence=2))
    return out


def agreement(register: list[CandidateRisk], proposed: list[CandidateRisk]) -> tuple[float | None, list[tuple[str, str]]]:
    """A register candidate is matched when an LLM candidate on the same page shares its title (fuzzy) or its span."""
    if not register:
        return None, []
    matched = []
    for r in register:
        for c in proposed:
            if c.page != r.page:
                continue
            title_sim = difflib.SequenceMatcher(None, _norm(r.verbatim_title), _norm(c.verbatim_title)).ratio()
            span_hit = _norm(c.verbatim_span)[:60] in _norm(r.verbatim_span) or _norm(r.verbatim_span)[:60] in _norm(c.verbatim_span)
            if title_sim >= 0.6 or span_hit:
                matched.append((r.candidate_id, c.candidate_id))
                break
    return len(matched) / len(register), matched


def identify(parsed: ParseResult, record: RunRecord, client: LLMClient | None) -> IdentifyResult:
    reg = register_candidates(parsed)
    record.add("transform", "identify_register", "ok" if reg else "error", count=len(reg), strategy="register",
               erm=sum(c.prominence == 1 for c in reg), esrs=sum(c.prominence == 2 for c in reg))
    proposed: list[CandidateRisk] = []
    agree, matched = None, []
    if client is not None:
        proposed = llm_candidates(parsed, client)
        agree, matched = agreement(reg, proposed)
        record.add("transform", "identify_agreement",
                   "ok" if agree is not None and agree >= IDENTIFY_AGREEMENT_MIN else "warning",
                   count=len(matched), strategy="llm", agreement=None if agree is None else round(agree, 3),
                   proposed=len(proposed), threshold=IDENTIFY_AGREEMENT_MIN)
    return IdentifyResult(candidates=reg, llm_candidates=proposed, agreement=agree, matched=matched)
