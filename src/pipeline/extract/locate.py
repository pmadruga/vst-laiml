"""E1-E3: find the target sections and validate them (SPECS.md > EXTRACT).

E1  TOC links: the TOC page's link annotations resolve each entry to a page index; the dotted
    entries give the printed number. Fallback without links: footer numbers give the offset.
E2  Match titles: configured titles (plus synonyms) against normalised TOC titles, three grades.
E3  Validate sections: match grade x required/optional -> outcome; landing page must carry the
    title and the expected footer number. Every outcome goes to the run record.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from pathlib import Path

import pymupdf

from shared.config import SECTIONS, TITLE_SYNONYMS, SectionSpec
from shared.runrecord import RunRecord
from shared.schema import LocateResult, Outcome, SectionRange, TocEntry
from . import pdf as P

# leader dots come out of the text layer as "." or as control/replacement glyphs: any run of 3+ non-word, non-space chars
TOC_ENTRY = re.compile(r"(?P<title>[A-Z][^\n]{2,80}?)\s*[^\w\s]{3,}\s*(?P<page>\d{1,3})\b")
TOC_SCAN_PAGES = 12
MIN_TOC_ENTRIES = 5
SIMILARITY_FLOOR = 0.85


def normalise(s: str) -> str:
    s = s.lower().replace("–", "-").replace("’", "'")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --- E1 ------------------------------------------------------------------------------------


def find_toc_pages(doc: pymupdf.Document, scan: int = TOC_SCAN_PAGES) -> list[int]:
    hits = []
    for i in range(min(scan, len(doc))):
        if len(TOC_ENTRY.findall(P.plain_text(doc[i]))) >= MIN_TOC_ENTRIES:
            hits.append(i)
    return hits


def toc_entries(doc: pymupdf.Document, toc_pages: list[int]) -> list[TocEntry]:
    entries: list[TocEntry] = []
    for i in toc_pages:
        page = doc[i]
        links = P.toc_links(page)
        ws = P.words(page, drop_footer=False)
        for ln in P.lines(ws):
            text = " ".join(w.text for w in ln)
            for m in TOC_ENTRY.finditer(text):
                title, printed = m.group("title").strip(), int(m.group("page"))
                # the link whose rect overlaps this line and starts at or before the title's x
                title_x = next((w.x0 for w in ln if w.text.startswith(title.split()[0])), ln[0].x0)
                y = (ln[0].top + ln[0].bottom) / 2
                dest = None
                for rect, idx in links:
                    if rect.y0 - 2 <= y <= rect.y1 + 2 and rect.x0 - 3 <= title_x <= rect.x1:
                        dest = idx
                        break
                entries.append(TocEntry(title=title, printed_page=printed, pdf_index=dest))
    return entries


def measure_offset(doc: pymupdf.Document, printed_pages: list[int], max_probe: int = 6) -> tuple[int | None, list[str]]:
    """Fallback for a PDF without links: pdf_index - (printed - 1), voted across sections."""
    votes: Counter[int] = Counter()
    notes = []
    for p in printed_pages:
        found = None
        for step in range(max_probe):
            idx = p - 1 + step
            if not 0 <= idx < len(doc):
                break
            n = P.printed_page_number(doc[idx])
            if n is not None:
                cand = idx - (n - 1)
                check = p - 1 + cand
                if 0 <= check < len(doc) and P.printed_page_number(doc[check]) == p:
                    found = cand
                break
        if found is None:
            notes.append(f"offset_unverified_for_printed_page:{p}")
        else:
            votes[found] += 1
    if not votes:
        return None, notes
    off, _ = votes.most_common(1)[0]
    if len(votes) > 1:
        notes.append(f"offset_disagreement:{dict(votes)}")
    return off, notes


# --- E2 ------------------------------------------------------------------------------------


def match_title(spec: SectionSpec, entries: list[TocEntry]) -> tuple[TocEntry | None, str, float]:
    """Best TOC entry for a configured title: (entry, grade, score)."""
    wanted = [normalise(t) for t in TITLE_SYNONYMS.get(spec.toc_title, (spec.toc_title,))]
    best: tuple[TocEntry | None, str, float] = (None, "none", 0.0)
    for e in entries:
        t = normalise(e.title)
        for w in wanted:
            if t == w:
                grade, score = "exact", 1.0
            elif t.startswith(w + " ") or w.startswith(t + " "):
                grade, score = "variant", 0.95
            else:
                score = difflib.SequenceMatcher(None, w, t).ratio()
                grade = "similarity" if score >= SIMILARITY_FLOOR else "none"
            if score > best[2]:
                best = (e, grade, score)
    if best[1] == "none":
        return None, "none", best[2]
    return best


# --- E3 ------------------------------------------------------------------------------------


def _outcome(required: bool, failed: bool, soft: bool = False) -> Outcome:
    if not failed:
        return "ok"
    if soft:
        return "warning"
    return "error" if required else "warning"


def locate(pdf_path: Path, record: RunRecord, sections: tuple[SectionSpec, ...] = SECTIONS) -> LocateResult:
    doc = P.open_pdf(pdf_path)
    try:
        toc_pages = find_toc_pages(doc)
        entries = toc_entries(doc, toc_pages)
        record.add("extract", "toc_pages", "ok" if toc_pages else "warning", count=len(entries), pages=toc_pages,
                   links=sum(e.pdf_index is not None for e in entries))
        printed_sorted = sorted({e.printed_page for e in entries})

        matches = {s.name: match_title(s, entries) for s in sections}
        linked = [m[0] for m in matches.values() if m[0] and m[0].pdf_index is not None]
        if linked:
            offsets = Counter(e.pdf_index - (e.printed_page - 1) for e in linked)
            page_offset = offsets.most_common(1)[0][0]
            source = "toc_link"
        else:
            probe = [m[0].printed_page for m in matches.values() if m[0]] or [s.first_page for s in sections]
            off, notes = measure_offset(doc, probe)
            page_offset = off if off is not None else 0
            source = "toc_footer" if off is not None else "config"
            record.add("extract", "page_offset", "ok" if off is not None else "warning", strategy=source, offset=page_offset, notes=notes)

        ranges: list[SectionRange] = []
        for spec in sections:
            entry, grade, score = matches[spec.name]
            flags: list[str] = []
            if entry is None:
                first, last = spec.first_page, spec.last_page
                pdf_index = first - 1 + page_offset
                sec_source, matched = "config", None
                flags.append(f"toc_title_not_found:{spec.toc_title!r}")
            else:
                first = entry.printed_page
                later = [p for p in printed_sorted if p > first]
                toc_last = (later[0] - 1) if later else first
                last = min(toc_last, spec.last_page) if first == spec.first_page else toc_last
                pdf_index = entry.pdf_index if entry.pdf_index is not None else first - 1 + page_offset
                sec_source, matched = ("toc_link" if entry.pdf_index is not None else source), entry.title
                if grade == "variant":
                    flags.append(f"toc_title_variant:{entry.title!r}")
                elif grade == "similarity":
                    flags.append(f"toc_title_similarity:{score:.2f}:{entry.title!r}")
                if first != spec.first_page:
                    flags.append(f"toc_page_differs_from_config:toc={first},config={spec.first_page}")
            match_outcome = _outcome(spec.required, entry is None, soft=False) if grade != "similarity" else "warning"
            record.add("extract", "section_match_grade", match_outcome, strategy=grade, section=spec.name,
                       score=round(score, 3), matched=matched)

            # landing page: title present, footer equals printed number
            landing_ok = 0 <= pdf_index < len(doc)
            title_ok = footer_ok = False
            footer = None
            if landing_ok:
                page = doc[pdf_index]
                title_ok = normalise(spec.toc_title) in normalise(P.plain_text(page)) or any(
                    normalise(s) in normalise(P.plain_text(page)) for s in TITLE_SYNONYMS.get(spec.toc_title, ()))
                footer = P.printed_page_number(page)
                footer_ok = footer == first
            if not title_ok:
                flags.append(f"heading_not_on_first_page:{first}")
            if not footer_ok:
                flags.append(f"printed_page_mismatch:footer={footer},expected={first}")
            landing_outcome = _outcome(spec.required, not (title_ok and footer_ok))
            record.add("extract", "landing_page_ok", landing_outcome, section=spec.name, page=first, pdf_index=pdf_index,
                       title_ok=title_ok, footer=footer)

            outcome: Outcome = "error" if "error" in (match_outcome, landing_outcome) else (
                "warning" if "warning" in (match_outcome, landing_outcome) else "ok")
            ranges.append(SectionRange(section=spec.name, required=spec.required, toc_title=spec.toc_title, matched_title=matched,
                                       match_grade=grade, match_score=round(score, 3), first_page=first, last_page=last,
                                       pdf_index=pdf_index, source=sec_source, outcome=outcome, quality_flags=flags))
        status = "error" if any(r.outcome == "error" for r in ranges) else (
            "warnings" if any(r.outcome == "warning" for r in ranges) else "ok")
        return LocateResult(pdf=str(pdf_path), page_count=len(doc), toc_pages=toc_pages, page_offset=page_offset,
                            sections=ranges, status=status)
    finally:
        doc.close()
