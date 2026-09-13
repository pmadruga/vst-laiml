"""E4-E7: read the located pages into blocks with provenance (SPECS.md > EXTRACT).

E4  words with box, font and size; rules and drawings; footer dropped; lines by vertical tolerance.
E5  p.51 main-risks table: heading x-positions define columns, row labels define rows.
E6  pp.71-74 ESRS tables: one per "Sub-topic" header; rows between rules per column; names in the
    Medium font; risk vs opportunity from the arrow icon, cross-checked with the row text.
E7  persist blocks; other pages as one plain-text block each, flagged.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pymupdf

from shared.config import SECTIONS, SectionSpec
from shared.schema import LocateResult, Marker, ParseResult, Register, SectionBlock
from . import pdf as P


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# --- E5: main-risks table -------------------------------------------------------------------


def parse_main_risks_table(page: pymupdf.Page, page_no: int, pdf_index: int, section: str) -> list[SectionBlock]:
    ws = P.words(page)
    heads = [w for w in ws if 11 <= w.size <= 13]
    row_labels = P.lines([w for w in heads if w.x0 < 200])
    col_heads = [w for w in heads if w.x0 >= 200]
    if not row_labels or not col_heads:
        return []
    first_label_top = min(ln[0].top for ln in row_labels)
    col_heads = [w for w in col_heads if w.top < first_label_top]

    cols: list[list[P.Word]] = []
    for w in sorted(col_heads, key=lambda w: w.x0):
        if cols and (w.x0 - max(x.x1 for x in cols[-1]) < 40 or abs(w.x0 - min(x.x0 for x in cols[-1])) < 5):
            cols[-1].append(w)
        else:
            cols.append([w])
    col_left = [min(w.x0 for w in c) for c in cols]
    col_titles = [P.text_of(P.lines(c)) for c in cols]

    labels = sorted(row_labels, key=lambda ln: ln[0].top)
    row_tops = [ln[0].top for ln in labels] + [page.rect.height]
    row_names = [_slug(P.text_of([ln])) for ln in labels]

    body = [w for w in ws if w.size < 10 and w.x0 >= col_left[0] - 15 and w.top >= row_tops[0] - 4]
    cells: dict[tuple[int, int], list[P.Word]] = defaultdict(list)
    for w in body:
        c = max(i for i, left in enumerate(col_left) if w.x0 >= left - 15)
        r = max(i for i, top in enumerate(row_tops[:-1]) if w.top >= top - 4)
        cells[(c, r)].append(w)

    blocks = []
    for c, title in enumerate(col_titles):
        fields = {row_names[r]: P.text_of(P.lines(cells[(c, r)])) for r in range(len(row_names))}
        blocks.append(SectionBlock(
            block_id=f"p{page_no}-erm-{c + 1}", section=section, page=page_no, pdf_index=pdf_index,
            source_register=Register.ERM_MAIN_RISK, heading=title, fields=fields,
            text=" ".join(v for v in fields.values() if v), marker="risk", marker_source="n/a",
            strategy="main_risks_table"))
    return blocks


# --- E6: ESRS tables -----------------------------------------------------------------------

TOPIC_CODE = re.compile(r"^[ESG]\d$")


def lexical_marker(text: str) -> Marker:
    t = text.lower()
    if "immaterial" in t:
        return "immaterial"
    if "opportunit" in t and "risk" not in t.split("opportunit")[0][-40:]:
        return "opportunity"
    return "risk"


def parse_esrs_tables(page: pymupdf.Page, page_no: int, pdf_index: int, section: str) -> list[SectionBlock]:
    ws = P.words(page)
    height = page.rect.height
    content_end = height - P.FOOTER_BAND
    legend = [w for w in ws if w.text == "materiality" and w.top > height * 0.8]
    if legend:
        content_end = min(w.top for w in legend) - 4

    headers = sorted({round(w.top, 1) for w in ws if w.text == "Sub-topic" and w.size >= 11})
    topic_heads = P.lines([w for w in ws if 17 <= w.size <= 19])
    rules = P.horizontal_rules(page)
    blocks: list[SectionBlock] = []

    for i, h_top in enumerate(headers):
        header_words = [w for w in ws if abs(w.top - h_top) <= P.LINE_TOL and w.size >= 11]
        sub_x = min(w.x0 for w in header_words if w.text == "Sub-topic")
        imp_x = min((w.x0 for w in header_words if w.text == "Impacts"), default=sub_x + 100)
        fin_x = min((w.x0 for w in header_words if w.text == "Financial"), default=imp_x + 340)
        vc_x = sorted(w.x0 for w in ws if h_top < w.top <= h_top + 24 and w.text == "Value")
        imp_vc_x = next((x for x in vc_x if imp_x < x < fin_x), fin_x - 60)
        fin_vc_x = next((x for x in vc_x if x > fin_x), page.rect.width - 60)

        table_end = content_end
        if i + 1 < len(headers):
            nxt = [ln[0].top for ln in topic_heads if h_top < ln[0].top < headers[i + 1]]
            table_end = min(nxt) - 2 if nxt else headers[i + 1] - 2
        above = [ln for ln in topic_heads if ln[0].top < h_top]
        topic_line = max(above, key=lambda ln: ln[0].top) if above else None
        code = next((w.text for w in topic_line if TOPIC_CODE.match(w.text)), None) if topic_line else None
        topic = P.text_of([[w for w in topic_line if not TOPIC_CODE.match(w.text)]]) if topic_line else None

        in_table = [w for w in ws if h_top + 24 < w.top < table_end]
        markers = P.arrow_markers(page, fin_x - 2, fin_x + 12)

        def col_rules(x_left: float) -> list[float]:
            return sorted({y for (y, x0, _) in rules if abs(x0 - x_left) < 6 and h_top < y < table_end})

        def entries(x_lo: float, vc_lo: float, vc_hi: float, seps: list[float], kind: str) -> None:
            bounds = seps + [table_end]
            for j in range(len(bounds) - 1):
                t0, t1 = bounds[j], bounds[j + 1]
                cell = [w for w in in_table if x_lo - 4 <= w.x0 < vc_lo - 4 and t0 <= w.top < t1]
                if not cell:
                    continue
                groups: list[list[list[P.Word]]] = []
                for ln in P.lines(cell):
                    is_name = all(w.font == "Medium" for w in ln)
                    if is_name or not groups:
                        groups.append([ln])
                    else:
                        groups[-1].append(ln)
                sub = P.lines([w for w in in_table if w.x0 < imp_x - 4 and t0 <= w.top < t1])
                if not sub:
                    prev = [w for w in in_table if w.x0 < imp_x - 4 and w.top < t0]
                    if prev:
                        last_top = max(w.top for w in prev)
                        sub = P.lines([w for w in prev if w.top >= last_top - 40])
                sub_text = P.text_of(sub)
                mat = re.match(r"^((?:Double|Impact|Financial) materiality)\s*(.*)$", sub_text)
                materiality, sub_topic = (mat.group(1), mat.group(2)) if mat else (None, sub_text)
                vc = P.text_of(P.lines([w for w in in_table if vc_lo - 4 <= w.x0 < vc_hi and t0 <= w.top < t1]))
                for g_idx, g in enumerate(groups):
                    name_lines = [ln for ln in g if all(w.font == "Medium" for w in ln)]
                    desc_lines = [ln for ln in g if ln not in name_lines]
                    name, desc = P.text_of(name_lines), P.text_of(desc_lines)
                    text = f"{name} {desc}".strip()
                    flags: list[str] = []
                    if kind == "financial":
                        g_top = min(w.top for ln in g for w in ln) - 3
                        g_bot = max(w.bottom for ln in g for w in ln)
                        icon = next((m for (y, m) in markers if g_top <= y <= g_bot), None)
                        lexical = lexical_marker(text)
                        if icon is None:
                            marker, source = lexical, "text"
                            if lexical != "immaterial":
                                flags.append("marker_icon_missing")
                        else:
                            marker = icon
                            source = "icon+text" if icon == lexical else "icon"
                            if icon != lexical:
                                flags.append(f"marker_disagreement:icon={icon},text={lexical}")
                        register = Register.ESRS_FINANCIAL_RISK if marker == "risk" else None
                    else:
                        marker, source, register = "impact", "n/a", None
                        if "immaterial" in text.lower():
                            marker = "immaterial"
                    ap = re.search(r"\((?:[^()]*,\s*)?(actual|potential)\)", name)
                    suffix = chr(97 + g_idx) if len(groups) > 1 else ""
                    blocks.append(SectionBlock(
                        block_id=f"p{page_no}-{code or 'x'}-{kind}-{j + 1}{suffix}", section=section, page=page_no,
                        pdf_index=pdf_index, source_register=register, source_taxonomy=code, sub_topic=sub_topic or None,
                        heading=name or desc[:60],
                        fields={k: v for k, v in {"name": name, "description": desc, "topic": topic or "", "materiality": materiality or ""}.items() if v},
                        text=text, marker=marker, marker_source=source, value_chain=vc or None,
                        actual_or_potential=ap.group(1) if ap else None, strategy="esrs_table", quality_flags=flags))

        entries(imp_x, imp_vc_x, fin_x, col_rules(imp_x - 4), "impact")
        entries(fin_x, fin_vc_x, page.rect.width, col_rules(fin_x - 4), "financial")
    return blocks


# --- E7: plain pages and entry point -----------------------------------------------------


def plain_block(page: pymupdf.Page, page_no: int, pdf_index: int, section: str) -> SectionBlock:
    text = P.plain_text(page)
    lns = [ln for ln in text.splitlines() if ln.strip()]
    heading = lns[1] if len(lns) > 1 else (lns[0] if lns else "")
    return SectionBlock(block_id=f"p{page_no}-text", section=section, page=page_no, pdf_index=pdf_index, heading=heading[:80],
                        text=re.sub(r"\s+", " ", text).strip(), marker="none", marker_source="n/a", strategy="plain_text",
                        quality_flags=["layout_unreconstructed"])


LAYOUT_PARSERS = {"main_risks_table": parse_main_risks_table, "esrs_table": parse_esrs_tables}


def parse(pdf_path: Path, located: LocateResult, sections: tuple[SectionSpec, ...] = SECTIONS,
          only: set[str] | None = None) -> ParseResult:
    specs = {s.name: s for s in sections}
    doc = P.open_pdf(pdf_path)
    try:
        blocks: list[SectionBlock] = []
        page_text: dict[int, str] = {}
        for sec in located.sections:
            if sec.outcome == "error" or (only and sec.section not in only):
                continue
            spec = specs[sec.section]
            for page_no in range(sec.first_page, sec.last_page + 1):
                idx = sec.pdf_index + (page_no - sec.first_page)
                if not 0 <= idx < len(doc):
                    continue
                page = doc[idx]
                page_text[page_no] = P.plain_text(page)
                parser = LAYOUT_PARSERS.get(spec.layout) if spec.layout and page_no in spec.layout_pages else None
                got = parser(page, page_no, idx, sec.section) if parser else []
                if not got:
                    b = plain_block(page, page_no, idx, sec.section)
                    if parser:
                        b.quality_flags.append("table_reconstruction_found_nothing")
                    got = [b]
                blocks.extend(got)
        return ParseResult(pdf=str(pdf_path), blocks=blocks, page_text=page_text)
    finally:
        doc.close()
