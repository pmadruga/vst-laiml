"""Run the five evaluators on a run's final.json against eval/golden.json; write the scores to the run record.

    uv run python eval/run_eval.py --run-id <id>              # score one run
    uv run python eval/run_eval.py --run-id <id> --intents    # also score the question golden set (needs runs/<id>/llm intents or a live model)

Regression runs (brief step 4) are produced by etl.py with a different model, prompt version or a broken
parser, then scored here; see README.md > Evaluation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluators import THRESHOLDS, evaluate, evaluate_intents, load_golden  # noqa: E402

from shared.config import EVAL_DIR, RUNS_DIR  # noqa: E402
from shared.runrecord import RunRecord  # noqa: E402


def score_run(run_id: str, golden_path: Path = EVAL_DIR / "golden.json", intents: bool = False) -> dict:
    run_dir = RUNS_DIR / run_id
    if not (run_dir / "final.json").exists():
        rr = run_dir / "run_record.json"
        errors = [r["check_id"] for r in json.loads(rr.read_text()) if r["outcome"] == "error"] if rr.exists() else []
        raise SystemExit(f"{run_id}: no final.json, the run stopped before the transform phase; errors on the run record: {errors}")
    final = json.loads((run_dir / "final.json").read_text())
    golden = load_golden(golden_path)
    parse_path = run_dir / "parse.json"
    page_text = {int(k): v for k, v in json.loads(parse_path.read_text())["page_text"].items()} if parse_path.exists() else None
    results = evaluate(golden, final["risks"], page_text)
    record = RunRecord(run_id, final["report"]["id"], run_dir)
    scores = {r.name: r.score for r in results}
    failed = [r.name for r in results if not r.passed]
    record.add("transform", "eval_scores", "error" if failed else "ok", count=len(failed), scores=scores, failed=failed,
               thresholds=THRESHOLDS, failures={r.name: r.failures for r in results if r.failures})
    report = {"run_id": run_id, "scores": scores, "failed": failed, "results": [r.__dict__ for r in results]}
    if intents:
        from shared.llm import LLMClient, ReplayMiss, load_prompt
        from shared.schema import QueryIntent
        replay = LLMClient(run_dir, replay_dir=run_dir)  # recorded intents first; a miss (new prompt) goes live and is recorded
        live = None
        parsed = []
        for q in golden["questions"]:
            key = "".join(ch for ch in q["question"].lower() if ch.isalnum())[:40]
            try:
                intent, _ = replay.complete(f"intent-{key}", load_prompt("intent"), f"Question: {q['question']}", QueryIntent)
            except ReplayMiss:
                live = live or LLMClient(run_dir)
                intent, _ = live.complete(f"intent-{key}", load_prompt("intent"), f"Question: {q['question']}", QueryIntent)
            parsed.append(intent.model_dump(mode="json"))
        ir = evaluate_intents(golden, parsed)
        record.add("api", "intent_agreement", "ok" if ir.passed else "warning", count=len(ir.failures), score=ir.score, failures=ir.failures)
        report["intent"] = ir.__dict__
    (run_dir / "eval").mkdir(exist_ok=True)
    (run_dir / "eval" / "report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--golden", type=Path, default=EVAL_DIR / "golden.json")
    ap.add_argument("--intents", action="store_true")
    a = ap.parse_args(argv)
    rep = score_run(a.run_id, a.golden, a.intents)
    print(f"run {a.run_id}")
    for r in rep["results"]:
        mark = "pass" if r["passed"] else "FAIL"
        print(f"  {r['name']:<15} {r['score']:.2f}  {mark}" + (f"  {r['failures']}" if r["failures"] else ""))
    if "intent" in rep:
        i = rep["intent"]
        print(f"  {'intent':<15} {i['score']:.2f}  {'pass' if i['passed'] else 'FAIL'}" + (f"  {i['failures']}" if i["failures"] else ""))
    return 1 if rep["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
