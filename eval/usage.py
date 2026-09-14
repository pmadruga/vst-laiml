"""Model calls, tokens, time and hosted-equivalent cost of a recorded run, per step; the source of SCALABILITY.md's model figures.

    uv run python eval/usage.py eval/runs/baseline                 # one run, per step
    uv run python eval/usage.py eval/runs/baseline --reports 10 20 50 200

Reads <run_dir>/llm/*.json (usage and elapsed_s as recorded live). Calls are grouped by the step prefix of their
call_id; `intent` calls belong to the API question endpoint, not the pipeline, and are reported apart.
The model runs locally, so cost is what the same token counts would cost at a hosted provider's list price.
Token counts are the local tokenizer's; another model's tokenizer and reasoning length change them.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

# USD per million tokens (input, output), OpenRouter list prices read from openrouter.ai/api/v1/models on 2026-09-14.
PRICES_AS_OF = "2026-09-14"
PRICES: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-20b": (0.03, 0.13),         # the same weights as the local gpt-oss, hosted
    "mistralai/ministral-14b-2512": (0.20, 0.20),  # the same weights as the local weak-model regression, hosted
    "openai/gpt-5-mini": (0.25, 2.00),          # a small hosted proprietary model
    "anthropic/claude-sonnet-5": (2.00, 10.00),  # a frontier model; its batch tier is half this
}
PIPELINE_STEPS = ("identify", "describe", "repair")


def usage(run_dir: Path) -> dict[str, dict]:
    steps: dict[str, dict] = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0, "seconds": 0.0, "models": set()})
    for f in sorted((run_dir / "llm").glob("*.json")):
        rec = json.loads(f.read_text())
        u = rec.get("usage") or {}
        s = steps[rec["call_id"].split("-")[0]]
        s["calls"] += 1
        s["in"] += u.get("prompt_tokens", 0)
        s["out"] += u.get("completion_tokens", 0)
        s["seconds"] += rec.get("elapsed_s") or 0.0
        s["models"].add(rec["model"])
    return dict(steps)


def cost(tokens_in: int, tokens_out: int, model: str) -> float:
    p_in, p_out = PRICES[model]
    return (tokens_in * p_in + tokens_out * p_out) / 1e6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--reports", type=int, nargs="*", default=[])
    args = ap.parse_args()

    steps = usage(args.run_dir)
    models = list(PRICES)
    head = f"{'step':<10}{'calls':>6}{'in':>9}{'out':>8}{'time s':>8}" + "".join(f"{m.split('/')[1]:>30}" for m in models)
    print(f"{args.run_dir}  (cost in USD at OpenRouter list prices of {PRICES_AS_OF})\n{head}")

    def line(name: str, s: dict) -> None:
        print(f"{name:<10}{s['calls']:>6}{s['in']:>9,}{s['out']:>8,}{s['seconds']:>8.1f}"
              + "".join(f"{cost(s['in'], s['out'], m):>30.5f}" for m in models))

    total = {"calls": 0, "in": 0, "out": 0, "seconds": 0.0}
    for name in PIPELINE_STEPS:
        if name in steps:
            line(name, steps[name])
            for k in total:
                total[k] += steps[name][k]
    line("pipeline", total)
    for name, s in steps.items():
        if name not in PIPELINE_STEPS:
            line(name, s)
            per = {k: (v / s["calls"] if k != "models" else v) for k, v in s.items()}
            print(f"{'  per call':<10}{1:>6}{per['in']:>9,.0f}{per['out']:>8,.0f}{per['seconds']:>8.1f}"
                  + "".join(f"{cost(per['in'], per['out'], m):>30.5f}" for m in models))
    print("models recorded:", sorted({m for s in steps.values() for m in s["models"]}))

    if args.reports:
        print(f"\n{'reports':<10}{'calls':>7}{'in':>12}{'out':>10}{'model h':>9}" + "".join(f"{m.split('/')[1]:>30}" for m in models))
        for n in args.reports:
            print(f"{n:<10}{total['calls'] * n:>7}{total['in'] * n:>12,}{total['out'] * n:>10,}{total['seconds'] * n / 3600:>9.2f}"
                  + "".join(f"{cost(total['in'] * n, total['out'] * n, m):>30.2f}" for m in models))


if __name__ == "__main__":
    main()
