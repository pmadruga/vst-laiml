"""E8: validate the extraction (SPECS.md > Validation points, E8 rows). Every check goes to the run record."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from shared.config import PAGE_COVERAGE_MIN, RUNS_DIR, SECTIONS
from shared.runrecord import RunRecord
from shared.schema import LocateResult, ParseResult
from . import pdf as P

WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in WORD.findall(text)]


def _ngram_fidelity(block_text: str, page_text: str, n: int = 3) -> float:
    """Share of the block's word n-grams that occur in the page's word sequence."""
    b, p = _tokens(block_text), _tokens(page_text)
    if len(b) < n:
        return 1.0 if " ".join(b) in " ".join(p) else 0.0
    grams = {" ".join(p[i:i + n]) for i in range(len(p) - n + 1)}
    hits = sum(1 for i in range(len(b) - n + 1) if " ".join(b[i:i + n]) in grams)
    return hits / (len(b) - n + 1)


def validate_extraction(pdf_path: Path, located: LocateResult, parsed: ParseResult, record: RunRecord) -> str:
    specs = {s.name: s for s in SECTIONS}
    by_section = Counter(b.section for b in parsed.blocks)

    # blocks per section
    for sec in located.sections:
        if sec.outcome == "error":
            continue
        n = by_section.get(sec.section, 0)
        record.add("extract", "blocks_per_section", "ok" if n else ("error" if sec.required else "warning"),
                   count=n, section=sec.section)

    # main-risks shape
    erm = [b for b in parsed.blocks if b.strategy == "main_risks_table"]
    if erm:
        rows = {k for b in erm for k, v in b.fields.items() if v}
        empty = [(b.heading, k) for b in erm for k, v in b.fields.items() if not v]
        ok = len(erm) == 3 and len(rows) == 3 and not empty
        record.add("extract", "main_risks_shape", "ok" if ok else "error", count=len(erm), rows=sorted(rows), empty=empty)

    # markers
    fin = [b for b in parsed.blocks if b.strategy == "esrs_table" and b.marker in ("risk", "opportunity", "immaterial")]
    missing = [b.block_id for b in fin if "marker_icon_missing" in b.quality_flags]
    disagree = [b.block_id for b in fin if any(f.startswith("marker_disagreement") for f in b.quality_flags)]
    record.add("extract", "marker_missing", "warning" if missing else "ok", count=len(missing), blocks=missing)
    record.add("extract", "marker_disagreement", "warning" if disagree else "ok", count=len(disagree), blocks=disagree,
               risks=sum(b.marker == "risk" for b in fin), opportunities=sum(b.marker == "opportunity" for b in fin))

    # fidelity and coverage per page
    doc = P.open_pdf(pdf_path)
    try:
        low_fidelity, low_coverage = [], []
        for page_no, text in parsed.page_text.items():
            page_blocks = [b for b in parsed.blocks if b.page == page_no]
            for b in page_blocks:
                if b.strategy == "plain_text":
                    continue
                f = _ngram_fidelity(b.text, text)
                if f < 0.95:
                    low_fidelity.append((b.block_id, round(f, 3)))
            idx = page_blocks[0].pdf_index if page_blocks else None
            if idx is None:
                continue
            page = doc[idx]
            content = [w.text.lower() for w in P.words(page) if 40 < w.top]
            block_words = Counter(t for b in page_blocks for t in _tokens(b.heading + " " + b.text))
            page_words = Counter(_tokens(" ".join(content)))
            covered = sum(min(c, block_words.get(t, 0)) for t, c in page_words.items())
            cov = covered / max(1, sum(page_words.values()))
            if all(b.strategy == "plain_text" for b in page_blocks):
                continue  # plain text pages are whole by construction
            if cov < PAGE_COVERAGE_MIN:
                low_coverage.append((page_no, round(cov, 3)))
        record.add("extract", "text_not_on_page", "error" if low_fidelity else "ok", count=len(low_fidelity), blocks=low_fidelity)
        record.add("extract", "page_coverage", "warning" if low_coverage else "ok", count=len(low_coverage), pages=low_coverage,
                   threshold=PAGE_COVERAGE_MIN)
    finally:
        doc.close()

    # ids unique, pages inside ranges
    ids = Counter(b.block_id for b in parsed.blocks)
    dup = [k for k, v in ids.items() if v > 1]
    ranges = {s.section: (s.first_page, s.last_page) for s in located.sections}
    outside = [b.block_id for b in parsed.blocks if not (ranges[b.section][0] <= b.page <= ranges[b.section][1])]
    record.add("extract", "block_ids_and_ranges", "error" if dup or outside else "ok", count=len(dup) + len(outside),
               duplicates=dup, outside=outside)

    # drift vs previous run of the same report
    counts = Counter((b.page, b.marker) for b in parsed.blocks)
    current = {f"{p}:{m}": n for (p, m), n in sorted(counts.items())}
    previous = _previous_counts(record)
    if previous is None:
        record.add("extract", "count_drift", "ok", count=0, note="no previous run", counts=current)
    else:
        changed = {k: (previous.get(k), current.get(k)) for k in set(previous) | set(current) if previous.get(k) != current.get(k)}
        record.add("extract", "count_drift", "warning" if changed else "ok", count=len(changed), changed=changed, counts=current)
    return record.status("extract")


def _previous_counts(record: RunRecord) -> dict | None:
    """Counts from the most recent earlier run of the same report, if any."""
    best = None
    for d in sorted(RUNS_DIR.glob("*/run_record.json")):
        if d.parent.name == record.run_id:
            continue
        try:
            rows = json.loads(d.read_text())
        except Exception:
            continue
        for r in rows:
            if r.get("report_id") == record.report_id and r.get("check_id") == "count_drift":
                best = r["detail"].get("counts")
    return best
