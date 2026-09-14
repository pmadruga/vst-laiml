"""L1-L6: write records, indexes, views, the query file, review states and the run record to SQLite.

Schema (DESIGN.md > Schema, SPECS.md > LOAD): company, report, risk_instance (fact table), risk_citation,
risk_category, canonical_risk, correction, run, run_record; view risk_status; FTS5 over title + description.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from shared.config import COMPANY, REVIEW_BODIES, REVIEW_FREQUENCY_PATTERN
from shared.queries import named_queries
from shared.runrecord import RunRecord
from shared.schema import SCHEMA_VERSION, RiskExtraction

DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS company (id TEXT PRIMARY KEY, name TEXT NOT NULL, sector TEXT, country TEXT);
CREATE TABLE IF NOT EXISTS report (
  id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES company(id), fiscal_year INTEGER NOT NULL, file TEXT,
  review_bodies TEXT, review_frequency TEXT, page_offset INTEGER DEFAULT 0, run_id TEXT);
CREATE TABLE IF NOT EXISTS canonical_risk (id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES company(id), canonical_title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS risk_instance (
  id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES report(id), canonical_risk_id TEXT NOT NULL REFERENCES canonical_risk(id),
  title TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL, source_register TEXT NOT NULL, source_taxonomy TEXT,
  section TEXT NOT NULL, page INTEGER NOT NULL, potential_impact TEXT, mitigation TEXT, prominence INTEGER NOT NULL,
  verbatim_span TEXT NOT NULL, confidence REAL, poor_fit INTEGER DEFAULT 0, quality_flags TEXT, review_state TEXT NOT NULL,
  model TEXT, prompt_version TEXT, run_id TEXT);
CREATE TABLE IF NOT EXISTS risk_citation (risk_instance_id TEXT NOT NULL REFERENCES risk_instance(id), source_register TEXT NOT NULL,
  section TEXT NOT NULL, page INTEGER NOT NULL, span TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS risk_category (risk_instance_id TEXT NOT NULL REFERENCES risk_instance(id), category TEXT NOT NULL,
  is_primary INTEGER NOT NULL, PRIMARY KEY (risk_instance_id, category));
CREATE TABLE IF NOT EXISTS correction (id INTEGER PRIMARY KEY AUTOINCREMENT, risk_instance_id TEXT NOT NULL REFERENCES risk_instance(id),
  field TEXT NOT NULL, corrected_value TEXT, who TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS run (run_id TEXT PRIMARY KEY, report_id TEXT, pdf TEXT, model TEXT, prompt_version TEXT, phases TEXT,
  started_at TEXT, finished_at TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS run_record (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, report_id TEXT NOT NULL, phase TEXT NOT NULL,
  check_id TEXT NOT NULL, outcome TEXT NOT NULL, count INTEGER, strategy TEXT, detail TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS query_log (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, intent TEXT, results INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_report_company_year ON report(company_id, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_risk_category ON risk_category(category);
CREATE INDEX IF NOT EXISTS idx_risk_canonical ON risk_instance(canonical_risk_id);
CREATE INDEX IF NOT EXISTS idx_risk_register ON risk_instance(source_register);
CREATE VIRTUAL TABLE IF NOT EXISTS risk_fts USING fts5(id UNINDEXED, title, description);
-- L3: status per canonical risk and year. new = no instance the year before; removed = none this year;
-- elevated = prominence rose (ESRS register -> ERM main risks); continuing otherwise. Empty with one report.
CREATE VIEW IF NOT EXISTS risk_status AS
WITH years AS (
  SELECT cr.id AS canonical_risk_id, r.fiscal_year, MIN(ri.prominence) AS prominence
  FROM risk_instance ri JOIN report r ON r.id = ri.report_id JOIN canonical_risk cr ON cr.id = ri.canonical_risk_id
  GROUP BY cr.id, r.fiscal_year),
pairs AS (
  SELECT y.canonical_risk_id, y.fiscal_year, y.prominence, p.prominence AS prev_prominence
  FROM years y LEFT JOIN years p ON p.canonical_risk_id = y.canonical_risk_id AND p.fiscal_year = y.fiscal_year - 1)
SELECT canonical_risk_id, fiscal_year,
  CASE WHEN prev_prominence IS NULL THEN 'new'
       WHEN prominence < prev_prominence THEN 'elevated' ELSE 'continuing' END AS status
FROM pairs
WHERE EXISTS (SELECT 1 FROM report r2 JOIN canonical_risk cr2 ON cr2.company_id = r2.company_id
              WHERE cr2.id = pairs.canonical_risk_id AND r2.fiscal_year = pairs.fiscal_year - 1)
UNION ALL
SELECT y.canonical_risk_id, y.fiscal_year + 1, 'removed'
FROM years y
WHERE NOT EXISTS (SELECT 1 FROM years n WHERE n.canonical_risk_id = y.canonical_risk_id AND n.fiscal_year = y.fiscal_year + 1)
  AND y.fiscal_year + 1 <= (SELECT MAX(fiscal_year) FROM report);
"""


def connect(db_path: Path, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))


def review_frequency(page50_text: str) -> str | None:
    m = re.search(REVIEW_FREQUENCY_PATTERN, page50_text)
    return f"every {m.group(1)} months" if m else None


def load(extraction: RiskExtraction, record: RunRecord, db_path: Path, page50_text: str = "", run_meta: dict | None = None) -> str:
    conn = connect(db_path)
    try:
        init_schema(conn)
        with conn:  # one transaction per report (L1)
            rep = extraction.report
            comp = extraction.company
            conn.execute("INSERT OR REPLACE INTO company VALUES (?,?,?,?)", (comp.id, comp.name, comp.sector, comp.country))
            freq = rep.review_frequency or review_frequency(page50_text)
            conn.execute("INSERT OR REPLACE INTO report VALUES (?,?,?,?,?,?,?,?)",
                         (rep.id, comp.id, rep.fiscal_year, rep.file, json.dumps(rep.review_bodies or REVIEW_BODIES), freq, rep.page_offset, extraction.run.run_id))
            # replace this report's rows
            old = [r[0] for r in conn.execute("SELECT id FROM risk_instance WHERE report_id = ?", (rep.id,))]
            for oid in old:
                conn.execute("DELETE FROM risk_citation WHERE risk_instance_id = ?", (oid,))
                conn.execute("DELETE FROM risk_category WHERE risk_instance_id = ?", (oid,))
                conn.execute("DELETE FROM risk_fts WHERE id = ?", (oid,))
            conn.execute("DELETE FROM risk_instance WHERE report_id = ?", (rep.id,))
            for r in extraction.risks:
                conn.execute("INSERT OR IGNORE INTO canonical_risk VALUES (?,?,?)", (r.canonical_risk_id, comp.id, r.title))
                conn.execute("""INSERT INTO risk_instance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (r.id, rep.id, r.canonical_risk_id, r.title, r.description, r.category.value, r.source_register.value,
                              r.source_taxonomy, r.section, r.page, r.potential_impact, r.mitigation, r.prominence, r.verbatim_span,
                              r.confidence, int(r.poor_fit), json.dumps(r.quality_flags), r.review_state, r.model, r.prompt_version, r.run_id))
                for c in r.citations:
                    conn.execute("INSERT INTO risk_citation VALUES (?,?,?,?,?)", (r.id, c.source_register.value, c.section, c.page, c.span))
                conn.execute("INSERT INTO risk_category VALUES (?,?,1)", (r.id, r.category.value))
                for sc in r.secondary_categories:
                    if sc != r.category:
                        conn.execute("INSERT OR IGNORE INTO risk_category VALUES (?,?,0)", (r.id, sc.value))
                conn.execute("INSERT INTO risk_fts(id, title, description) VALUES (?,?,?)", (r.id, r.title, r.description))
        n = conn.execute("SELECT COUNT(*) FROM risk_instance WHERE report_id = ?", (rep.id,)).fetchone()[0]
        record.add("load", "rows_written", "ok" if n == len(extraction.risks) else "error", count=n, db=str(db_path))
        # L4: the three brief questions run
        results = {}
        for name, sql in named_queries().items():
            params = {"company": None, "year": None, "category": "cyber", "sector": None}
            results[name] = len(conn.execute(sql, params).fetchall())
        record.add("load", "brief_queries", "ok", count=len(results), **results)
        # L6: run and run record, written last so the load's own checks are included
        meta = run_meta or {}
        with conn:
            conn.execute("INSERT OR REPLACE INTO run VALUES (?,?,?,?,?,?,?,?,?)",
                         (record.run_id, rep.id, meta.get("pdf"), extraction.run.model, extraction.run.prompt_version,
                          json.dumps(meta.get("phases", [])), extraction.run.started_at.isoformat(), meta.get("finished_at"), record.status()))
            conn.execute("DELETE FROM run_record WHERE run_id = ?", (record.run_id,))
            for row in record.rows:
                conn.execute("INSERT INTO run_record(run_id, report_id, phase, check_id, outcome, count, strategy, detail, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                             (row.run_id, row.report_id, row.phase, row.check_id, row.outcome, row.count, row.strategy,
                              json.dumps(row.detail, default=str), row.created_at.isoformat()))
        return record.status("load")
    finally:
        conn.close()
