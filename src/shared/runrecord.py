"""The run record (L6): every validation outcome and strategy choice, per run, report and check.

Written incrementally to runs/<run_id>/run_record.json by every phase; loaded into SQLite by the load phase.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import Outcome, RunCheck


class RunRecord:
    def __init__(self, run_id: str, report_id: str, run_dir: Path):
        self.run_id = run_id
        self.report_id = report_id
        self.path = run_dir / "run_record.json"
        self.rows: list[RunCheck] = []
        if self.path.exists():
            self.rows = [RunCheck.model_validate(r) for r in json.loads(self.path.read_text())]

    def add(self, phase: str, check_id: str, outcome: Outcome, count: int = 0, strategy: str | None = None, **detail) -> RunCheck:
        row = RunCheck(run_id=self.run_id, report_id=self.report_id, phase=phase, check_id=check_id,
                       outcome=outcome, count=count, strategy=strategy, detail=detail)
        self.rows.append(row)
        self.save()
        return row

    def save(self) -> None:
        self.path.write_text(json.dumps([r.model_dump(mode="json") for r in self.rows], indent=2) + "\n")

    def outcomes(self, phase: str | None = None) -> list[RunCheck]:
        return [r for r in self.rows if phase is None or r.phase == phase]

    def status(self, phase: str | None = None) -> str:
        rows = self.outcomes(phase)
        if any(r.outcome == "error" for r in rows):
            return "error"
        if any(r.outcome == "warning" for r in rows):
            return "warnings"
        return "ok"

    def summary(self, phase: str | None = None) -> str:
        lines = []
        for r in self.outcomes(phase):
            mark = {"ok": "ok ", "warning": "WARN", "error": "ERR "}[r.outcome]
            extra = f" ({r.strategy})" if r.strategy else ""
            det = ", ".join(f"{k}={v}" for k, v in r.detail.items() if not isinstance(v, (list, dict)))
            lines.append(f"  [{mark}] {r.check_id:<22} count={r.count}{extra} {det}")
        return "\n".join(lines)
