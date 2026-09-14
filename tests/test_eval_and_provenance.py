"""Evaluators that must be able to fail, run provenance, enrichment anchoring and the removed status."""

import importlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.load.sqlite import load
from pipeline.transform.enrich import _actions_paragraph
from shared.config import EVAL_DIR
from shared.runrecord import RunRecord
from shared.schema import ParseResult, RiskExtraction

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses look their module up while the class is built
    spec.loader.exec_module(mod)
    return mod


evaluators = _module("evaluators", EVAL_DIR / "evaluators.py")


def test_grounding_evaluator_fails_an_invented_description(baseline_run):
    golden = evaluators.load_golden(EVAL_DIR / "golden.json")
    final = json.loads((baseline_run / "final.json").read_text())
    parse = json.loads((baseline_run / "parse.json").read_text())
    page_text = {int(k): v for k, v in parse["page_text"].items()}
    invented = [dict(r, description="The company expects losses of EUR 470m by 2031. Nothing else is known.", mitigation=None)
                for r in final["risks"]]
    scores = {r.name: r for r in evaluators.evaluate(golden, invented, page_text)}
    assert scores["grounding"].score == 0.0  # correct spans and citations no longer rescue a fabricated description
    assert any(p.startswith("invented_number") for _, problems in scores["grounding"].failures for p in problems)


def test_intent_evaluator_compares_every_field():
    golden = evaluators.load_golden(EVAL_DIR / "golden.json")
    q = next(q for q in golden["questions"] if q["intent"]["free_text"])
    one = {"questions": [q]}
    assert evaluators.evaluate_intents(one, [q["intent"]]).score == 1.0
    assert evaluators.evaluate_intents(one, [dict(q["intent"], free_text="")]).score == 0.0
    assert evaluators.evaluate_intents(one, [dict(q["intent"], years=[2024])]).score == 0.0
    s = next(q for q in golden["questions"] if q["intent"]["sector"])
    assert evaluators.evaluate_intents({"questions": [s]}, [dict(s["intent"], sector="Renewable-energy")]).score == 1.0
    assert evaluators.evaluate_intents({"questions": [s]}, [dict(s["intent"], sector="utilities")]).score == 0.0


def test_actions_paragraph_is_the_heading_not_a_cross_reference(parsed):
    para = _actions_paragraph(parsed.page_text[86])
    assert para.startswith("Our transition plan is structured around the two overarching decarbonisation levers")
    assert para.endswith("as well as with our suppliers.")
    assert "stakeholders" in para and "Decarbonisation levers:" not in para


def test_run_json_keeps_every_invocation(tmp_path):
    etl = _module("etl_under_test", ROOT / "etl.py")
    etl.write_run_json(tmp_path, "r", {"phases": ["extract", "transform"], "model": "weak", "prompt_version": "v1", "replay": None})
    meta = etl.write_run_json(tmp_path, "r", {"phases": ["load"], "model": "default", "prompt_version": "v1", "replay": None})
    assert meta["phases"] == ["extract", "transform", "load"]
    assert meta["model"] == "weak"  # the invocation whose calls are recorded, not the later load
    assert [i["phases"] for i in json.loads((tmp_path / "run.json").read_text())["invocations"]] == [["extract", "transform"], ["load"]]


@pytest.fixture()
def two_company_db(baseline_run, tmp_path):
    """Vestas 2024 and 2025 (one risk dropped in 2025), and a second company with a 2024 report only."""
    final = RiskExtraction.model_validate_json((baseline_run / "final.json").read_text())
    parsed = ParseResult.model_validate_json((baseline_run / "parse.json").read_text())
    path = tmp_path / "two.db"
    load(final, RunRecord("y2025", "vestas-2025", tmp_path), path, parsed.page_text.get(50, ""), {"pdf": "x", "phases": ["load"]})
    prev = final.model_copy(deep=True)
    prev.report.id, prev.report.fiscal_year = "vestas-2024", 2024
    for r in prev.risks:
        r.id = r.id.replace("2025", "2024")
    prev.risks.append(prev.risks[0].model_copy(update={"id": "vestas-2024-rX", "canonical_risk_id": "vestas-e1-old-risk", "title": "Old risk"}))
    load(prev, RunRecord("y2024", "vestas-2024", tmp_path), path, "", {"pdf": "y", "phases": ["load"]})
    other = final.model_copy(deep=True)
    other.company.id, other.company.name = "acme", "Acme Wind"
    other.report.id, other.report.company_id, other.report.fiscal_year = "acme-2024", "acme", 2024
    for r in other.risks:
        r.id, r.canonical_risk_id = r.id.replace("vestas-2025", "acme-2024"), r.canonical_risk_id.replace("vestas", "acme")
    load(other, RunRecord("acme", "acme-2024", tmp_path), path, "", {"pdf": "z", "phases": ["load"]})
    return path


def test_removed_is_scoped_to_the_company(two_company_db):
    with sqlite3.connect(two_company_db) as c:
        removed = {r[0] for r in c.execute("SELECT canonical_risk_id FROM risk_status WHERE status = 'removed'")}
    assert removed == {"vestas-e1-old-risk"}  # Acme has no 2025 report, so none of its 2024 risks is removed


def test_api_returns_removed_risks(two_company_db, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(two_company_db))
    from api import app as app_module
    importlib.reload(app_module)
    with TestClient(app_module.app) as client:
        r = client.get("/risks", params={"status": "removed"}).json()
        assert [x["title"] for x in r["records"]] == ["Old risk"] and r["records"][0]["fiscal_year"] == 2024
        assert client.get("/risks", params={"status": "removed", "year": 2025}).json()["count"] == 1
        assert client.get("/risks", params={"status": "removed", "year": 2024}).json()["count"] == 0

