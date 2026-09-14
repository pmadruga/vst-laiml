"""What spaCy's named-entity recogniser finds in the risk text (documentation/stages/entities-probe.md). No model calls.

    uv run python eval/probe_entities.py eval/runs/baseline

1. Entities in each record's own text: the register span and the potential impact.
2. Entities on the topical pages the brief offers (pp.85-92, p.118), distinct values counted per label.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import spacy  # the nlp dependency group

from shared.config import SPACY_MODEL

TOPICAL_PAGES = (*range(85, 93), 118)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--top", type=int, default=18, help="most frequent values shown per label")
    args = ap.parse_args()

    nlp = spacy.load(SPACY_MODEL)
    final = json.loads((args.run_dir / "final.json").read_text())
    parse = json.loads((args.run_dir / "parse.json").read_text())

    print("entities in each record's own text (register span and potential impact)")
    for r in final["risks"]:
        text = " ".join(filter(None, [r["verbatim_span"], r.get("potential_impact") or ""]))
        print(f"  {r['id']} {r['verbatim_title'][:40]:<40} {[(e.text, e.label_) for e in nlp(text).ents]}")

    counts: Counter = Counter()
    for page in TOPICAL_PAGES:
        for e in nlp(parse["page_text"].get(str(page), "")).ents:
            counts[(e.label_, " ".join(e.text.split()))] += 1
    by_label: dict[str, list[str]] = defaultdict(list)
    for (label, text), n in counts.most_common():
        by_label[label].append(f"{text} ({n})")
    print(f"\nentities on pp.85-92 and p.118: distinct values per label, the {args.top} most frequent shown")
    for label, values in sorted(by_label.items(), key=lambda kv: -len(kv[1])):
        print(f"  {label} [{len(values)}]: {', '.join(values[:args.top])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
