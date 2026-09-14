"""Identify on every in-scope page, tables and prose, against today's table-only identification (T1).

    uv run python eval/compare_identify.py --run-dir eval/runs/exp-identify-all

Today T1 keeps the risk-table rows (10 on the baseline) and asks the model only about the four table pages, to measure
agreement. This runs the same identify prompt and model on all 15 in-scope pages (pp.50-51, 71-74, 85-92, 118), keeps
proposals whose quoted span is on the page, and places each one: which table risk it matches, which parsed table row its
quote sits in (risk, impact, opportunity), and on prose pages the nearest "Type of impact" line above the quote.
Calls already recorded in the baseline are replayed; new pages are called live once and recorded under --run-dir,
so a second run replays everything and needs no model server.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

from pipeline.transform.identify import _norm, register_candidates
from shared.config import EVAL_DIR
from shared.llm import LLMClient, ReplayMiss, load_prompt
from shared.schema import LLMCandidateList, ParseResult

PAGES = (50, 51, 71, 72, 73, 74, *range(85, 93), 118)
TYPE_LINE = re.compile(r"Type of impact:\s*([^\n]+)")


def propose(page: int, text: str, clients: list[LLMClient], live: LLMClient) -> tuple[LLMCandidateList, str]:
    system, user = load_prompt("identify"), f"Report page {page}:\n\n{text}"
    for client in clients:
        try:
            return client.complete(f"identify-p{page}", system, user, LLMCandidateList)[0], "replayed"
        except ReplayMiss:
            continue
    return live.complete(f"identify-p{page}", system, user, LLMCandidateList)[0], "live"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, default=EVAL_DIR / "runs" / "exp-identify-all")
    ap.add_argument("--baseline", type=Path, default=EVAL_DIR / "runs" / "baseline")
    args = ap.parse_args()

    parsed = ParseResult.model_validate_json((args.baseline / "parse.json").read_text())
    tables = register_candidates(parsed)
    args.run_dir.mkdir(parents=True, exist_ok=True)
    clients = [LLMClient(args.run_dir, replay_dir=args.baseline), LLMClient(args.run_dir, replay_dir=args.run_dir)]
    live = LLMClient(args.run_dir)

    rows, pages = [], {}
    for page in PAGES:
        text = parsed.page_text.get(page, "")
        result, how = propose(page, text, clients, live)
        page_norm = _norm(text)
        kept = dropped = 0
        for c in result.candidates:
            if _norm(c.span)[:80] not in page_norm:
                dropped += 1
                continue
            kept += 1
            span_n = _norm(c.span)
            match, how_matched = None, None
            for t in tables:
                source = _norm(" ".join(filter(None, [t.verbatim_span, t.potential_impact or "", t.verbatim_title or ""])))
                if span_n[:60] in source or _norm(t.verbatim_span)[:60] in span_n:
                    match, how_matched = t, "quote"
                    break
            if match is None:
                best = max(tables, key=lambda t: difflib.SequenceMatcher(None, _norm(t.verbatim_title), _norm(c.title)).ratio())
                if difflib.SequenceMatcher(None, _norm(best.verbatim_title), _norm(c.title)).ratio() >= 0.8:
                    match, how_matched = best, "title"
            block = next((b for b in parsed.blocks if b.page == page and b.strategy == "esrs_table" and span_n[:60] in _norm(b.text)), None)
            pos = text.find(c.span[:40])
            type_line = None
            if pos > 0:
                found = list(TYPE_LINE.finditer(text[max(0, pos - 1500):pos + 1]))
                type_line = found[-1].group(1).strip() if found else None
            rows.append({"page": page, "title": c.title, "span": c.span, "calls": how,
                         "matches_table_risk": match.verbatim_title if match else None, "matched_by": how_matched,
                         "table_row": block.marker if block else None, "type_of_impact_above": type_line})
        pages[page] = {"calls": how, "proposed": len(result.candidates), "kept": kept, "dropped_quote_not_on_page": dropped}

    found = {r["matches_table_risk"] for r in rows if r["matches_table_risk"]}
    report = {"pages": pages, "table_risks": len(tables), "table_risks_found": sorted(found),
              "table_risks_missed": sorted({t.verbatim_title for t in tables} - found), "candidates": rows}
    (args.run_dir / "identify_all.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    print(f"{'page':>4} {'calls':<9} {'proposed':>8} {'kept':>5} {'dropped':>8}")
    for page, p in pages.items():
        print(f"{page:>4} {p['calls']:<9} {p['proposed']:>8} {p['kept']:>5} {p['dropped_quote_not_on_page']:>8}")
    print(f"\ntable risks found by the model: {len(found)} of {len(tables)}; missed: {report['table_risks_missed']}")
    print("\ncandidates")
    for r in rows:
        where = r["matches_table_risk"] and f"= table risk '{r['matches_table_risk']}' ({r['matched_by']})" or "NOT IN TABLES"
        print(f"  p.{r['page']:<3} {r['title'][:55]:<55} {where}")
        print(f"        table row: {r['table_row']}; type of impact above: {r['type_of_impact_above']}; quote: {r['span'][:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
