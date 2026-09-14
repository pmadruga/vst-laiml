"""L1-L6 and A1-A5 against a database built from the recorded baseline run."""

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.load.sqlite import connect, load
from shared.queries import named_queries
from shared.runrecord import RunRecord
from shared.schema import ParseResult, RiskExtraction


@pytest.fixture(scope="module")
def db_path(baseline_run):
    final = RiskExtraction.model_validate_json((baseline_run / "final.json").read_text())
    parsed = ParseResult.model_validate_json((baseline_run / "parse.json").read_text())
    d = Path(tempfile.mkdtemp())
    rec = RunRecord("load-test", "vestas-2025", d)
    path = d / "risk.db"
    status = load(final, rec, path, parsed.page_text.get(50, ""), {"pdf": "x", "phases": ["load"]})
    assert status != "error"
    return path


def test_rows_and_views(db_path):
    conn = connect(db_path, readonly=True)
    assert conn.execute("SELECT COUNT(*) FROM risk_instance").fetchone()[0] == 9
    assert conn.execute("SELECT COUNT(*) FROM risk_citation").fetchone()[0] == 11  # cyber has two registers, carbon taxes an enriched mitigation page
    assert conn.execute("SELECT review_frequency FROM report").fetchone()[0] == "every six months"
    assert conn.execute("SELECT COUNT(*) FROM risk_status").fetchone()[0] == 0  # one report: nothing to compare
    assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == "0.1"
    assert conn.execute("SELECT COUNT(*) FROM run_record").fetchone()[0] >= 1


def test_brief_queries(db_path):
    conn = connect(db_path, readonly=True)
    q = named_queries()
    assert set(q) == {"top_enterprise_risks", "newly_elevated_risks", "companies_with_category"}
    top = conn.execute(q["top_enterprise_risks"], {"company": "vestas", "year": None, "category": None, "sector": None}).fetchall()
    assert len(top) == 3 and all(r["review_frequency"] == "every six months" for r in top)
    elevated = conn.execute(q["newly_elevated_risks"], {"company": None, "year": None, "category": None, "sector": None}).fetchall()
    assert elevated == []
    cyber = conn.execute(q["companies_with_category"], {"company": None, "year": None, "category": "cyber", "sector": "renewable"}).fetchall()
    assert len(cyber) >= 1 and cyber[0]["company"].startswith("Vestas")


def test_api_structured_endpoints(db_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(db_path))
    import importlib
    from api import app as app_module
    importlib.reload(app_module)
    with TestClient(app_module.app) as client:
        assert client.get("/health").json()["status"] == "ok"
        r = client.get("/risks", params={"register": "erm_main_risk"}).json()
        assert r["count"] == 3 and all(x["source_register"] == "erm_main_risk" for x in r["records"])
        r = client.get("/risks", params={"category": "cyber"}).json()
        assert r["count"] == 1 and {c["page"] for c in r["records"][0]["citations"]} == {51, 74}
        r = client.get("/risks", params={"q": "tariffs"}).json()
        assert r["count"] >= 1
        r = client.get("/questions/top_enterprise_risks", params={"company": "vestas"}).json()
        assert r["count"] == 3
        assert client.get("/questions/nope").status_code == 404
        one = client.get(f"/risks/{r['rows'][0]['title'] and client.get('/risks').json()['records'][0]['id']}").json()
        assert one["citations"] and "quality_flags" in one


def test_api_refuses_schema_mismatch(db_path, monkeypatch, tmp_path):
    import shutil, sqlite3
    bad = tmp_path / "bad.db"
    shutil.copy(db_path, bad)
    with sqlite3.connect(bad) as conn:
        conn.execute("UPDATE meta SET value='9.9' WHERE key='schema_version'")
    monkeypatch.setenv("DB_PATH", str(bad))
    import importlib
    from api import app as app_module
    importlib.reload(app_module)
    with pytest.raises(RuntimeError, match="schema version mismatch"):
        with TestClient(app_module.app):
            pass


def test_status_view_with_two_years(baseline_run, tmp_path):
    """new = not in the prior year's report; removed = gone this year; elevated = moved into the ERM register."""
    import sqlite3
    final = RiskExtraction.model_validate_json((baseline_run / "final.json").read_text())
    parsed = ParseResult.model_validate_json((baseline_run / "parse.json").read_text())
    path = tmp_path / "two.db"
    rec = RunRecord("two-year", "vestas-2025", tmp_path)
    load(final, rec, path, parsed.page_text.get(50, ""), {"pdf": "x", "phases": ["load"]})
    # fake a 2024 report: the same risks except one dropped, one added, and cyber only in the ESRS register
    prev = final.model_copy(deep=True)
    prev.report.id, prev.report.fiscal_year = "vestas-2024", 2024
    dropped = prev.risks.pop()  # last risk absent in 2024 -> "new" in 2025
    for r in prev.risks:
        r.id = r.id.replace("2025", "2024"); r.report_id = "vestas-2024"
        if r.canonical_risk_id == "vestas-g1-cyber-security-risks":
            r.prominence = 2  # in 2024 cyber sat only in the ESRS register; in 2025 it is a main risk -> elevated
    extra = prev.risks[0].model_copy(update={"id": "vestas-2024-rX", "canonical_risk_id": "vestas-e1-old-risk", "title": "Old risk"})
    prev.risks.append(extra)
    load(prev, RunRecord("two-year-prev", "vestas-2024", tmp_path), path, "", {"pdf": "y", "phases": ["load"]})
    with sqlite3.connect(path) as c:
        rows = {(r[0], r[1]): r[2] for r in c.execute("SELECT canonical_risk_id, fiscal_year, status FROM risk_status")}
    assert rows[(dropped.canonical_risk_id, 2025)] == "new"
    assert rows[("vestas-e1-old-risk", 2025)] == "removed"
    assert rows[("vestas-g1-cyber-security-risks", 2025)] == "elevated"
    assert all(v == "continuing" for (cid, y), v in rows.items() if y == 2025 and cid not in (dropped.canonical_risk_id, "vestas-e1-old-risk", "vestas-g1-cyber-security-risks"))


def test_fts_query_with_quotes_does_not_500(db_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(db_path))
    import importlib
    from api import app as app_module
    importlib.reload(app_module)
    with TestClient(app_module.app) as client:
        assert client.get("/risks", params={"q": 'tariff"x'}).status_code == 200
        assert client.get("/risks", params={"status": "bogus"}).status_code == 422
        assert client.get("/risks", params={"limit": 0}).status_code == 422
