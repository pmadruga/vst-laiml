"""PyMuPDF helpers shared by the extract steps: words with fonts, lines, rules, arrows, footer numbers, links."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import pymupdf

FOOTER_BAND = 30.0  # points from the bottom edge: running footer and page number (footer top is at height - 28.3 here)
LINE_TOL = 2.5


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    font: str  # weight suffix: "Medium", "Standard", "Headline", ...


def open_pdf(path) -> pymupdf.Document:
    return pymupdf.open(str(path))


def words(page: pymupdf.Page, drop_footer: bool = True) -> list[Word]:
    """Words with exact boxes and font, built from the raw character stream."""
    out: list[Word] = []
    limit = page.rect.height - FOOTER_BAND if drop_footer else page.rect.height + 1
    for block in page.get_text("rawdict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                font = span["font"].rsplit("-", 1)[-1]
                size = float(span["size"])
                buf: list[dict] = []

                def flush():
                    if not buf:
                        return
                    text = "".join(c["c"] for c in buf).replace(" ", "").replace("\xa0", "").strip()
                    if text:
                        x0 = min(c["bbox"][0] for c in buf); x1 = max(c["bbox"][2] for c in buf)
                        top = min(c["bbox"][1] for c in buf); bottom = max(c["bbox"][3] for c in buf)
                        if top <= limit:
                            out.append(Word(text, x0, x1, top, bottom, size, font))
                    buf.clear()

                for ch in span["chars"]:
                    c = ch["c"]
                    if c.isspace() or not c.isprintable():  # icon placeholders come through as control chars
                        flush()
                    else:
                        buf.append(ch)
                flush()
    return out


def lines(ws: Iterable[Word]) -> list[list[Word]]:
    """Group words into lines by vertical position; each line left to right."""
    ordered = sorted(ws, key=lambda w: (w.top, w.x0))
    out: list[list[Word]] = []
    for w in ordered:
        if out and abs(out[-1][0].top - w.top) <= LINE_TOL:
            out[-1].append(w)
        else:
            out.append([w])
    for ln in out:
        ln.sort(key=lambda w: w.x0)
    return out


def text_of(lns: list[list[Word]]) -> str:
    return re.sub(r"\s+", " ", " ".join(" ".join(w.text for w in ln) for ln in lns)).strip()


def plain_text(page: pymupdf.Page) -> str:
    return page.get_text("text")


def printed_page_number(page: pymupdf.Page) -> int | None:
    """The number in the page footer (bottom-right corner), if any."""
    cands = [w for w in words(page, drop_footer=False) if w.top > page.rect.height - FOOTER_BAND and re.fullmatch(r"\d{1,3}", w.text)]
    if not cands:
        return None
    return int(max(cands, key=lambda w: w.x1).text)


def horizontal_rules(page: pymupdf.Page, min_width: float = 100.0) -> list[tuple[float, float, float]]:
    """(y, x0, x1) of horizontal rules drawn as lines or thin rectangles."""
    out = []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 1 and abs(it[2].x - it[1].x) >= min_width:
                out.append((round(it[1].y, 1), min(it[1].x, it[2].x), max(it[1].x, it[2].x)))
            elif it[0] == "re" and it[1].height < 1.5 and it[1].width >= min_width:
                out.append((round(it[1].y0, 1), it[1].x0, it[1].x1))
    return sorted(set(out))


def arrow_markers(page: pymupdf.Page, x_lo: float, x_hi: float) -> list[tuple[float, str]]:
    """(y, 'opportunity'|'risk') for every circle-with-arrow icon whose left edge lies in [x_lo, x_hi].

    The arrow is a 10-segment closed path; vertex 2 is the chevron apex and vertex 7 the far end of the shaft.
    Apex above the shaft end means the arrow points up (opportunity); below means down (risk).
    """
    out = []
    for d in page.get_drawings():
        r = d["rect"]
        items = d["items"]
        if x_lo <= r.x0 <= x_hi and r.width < 8 and len(items) == 10 and all(it[0] == "l" for it in items):
            apex, tail = items[2][1].y, items[7][1].y
            out.append((r.y0, "opportunity" if apex < tail else "risk"))
    return sorted(out)


def toc_links(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, int]]:
    """(rect, destination page index) for every internal link on the page."""
    out = []
    for l in page.get_links():
        if l.get("page", -1) is not None and l.get("page", -1) >= 0 and l.get("kind") in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED):
            out.append((l["from"], int(l["page"])))
    return out
