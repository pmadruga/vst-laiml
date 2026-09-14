"""Serving API, A1-A5 (DESIGN.md > 2. API; SPECS.md > API).

Read-only over the SQLite file the load phase writes. Structured endpoints take filters; the
question endpoint parses a natural-language question into the same filters with one recorded
model call (same taxonomy and mapping rule as the pipeline), then runs our SQL. The model never
writes SQL. The parsed intent is returned with the results.

    uvicorn api.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Literal
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from shared.config import DB_PATH, LLM_MODEL, PROMPT_VERSION, RUNS_DIR
from shared.queries import named_queries
from shared.schema import SCHEMA_VERSION, Category, QueryIntent, Register
from shared.llm import LLMClient, ReplayMiss, load_prompt

from .models import (AskResponse, CompanyOut, HealthResponse, QuestionResponse, RiskListResponse, RiskOut, RunCheckOut, RunOut)

DB = Path(os.environ.get("DB_PATH", DB_PATH))
REPLAY_RUN = os.environ.get("API_REPLAY_RUN")  # serve intents from a recorded run: no model needed


# --- A1: open ------------------------------------------------------------------------------


def open_db() -> sqlite3.Connection:
    if not DB.exists():
        raise RuntimeError(f"database not found at {DB}; run the pipeline's load phase first")
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    version = row[0] if row else None
    if version != SCHEMA_VERSION:
        conn.close()
        raise RuntimeError(f"schema version mismatch: database {version!r}, service {SCHEMA_VERSION!r}")
    return conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_db().close()  # A1: refuses to start on a schema mismatch; endpoints open their own read-only connection
    app.state.queries = named_queries()
    app.state.llm = None
    yield


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


app = FastAPI(title="Structured Risk Intelligence API", version=SCHEMA_VERSION, lifespan=lifespan)


# --- A2 / A4: structured queries ----------------------------------------------------------


def row_to_record(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    d = dict(row)
    d["quality_flags"] = json.loads(d.get("quality_flags") or "[]")
    d["citations"] = [dict(c) for c in conn.execute(
        "SELECT source_register, section, page, span FROM risk_citation WHERE risk_instance_id = ?", (d["id"],))]
    d["categories"] = [dict(c) for c in conn.execute(
        "SELECT category, is_primary FROM risk_category WHERE risk_instance_id = ?", (d["id"],))]
    return d


def query_records(conn: sqlite3.Connection, intent: QueryIntent, limit: int = 100) -> list[dict]:
    sql = ["SELECT DISTINCT ri.*, c.name AS company_name, c.sector, r.fiscal_year, r.review_frequency, r.review_bodies",
           "FROM risk_instance ri JOIN report r ON r.id = ri.report_id JOIN company c ON c.id = r.company_id"]
    where, params = [], []
    if intent.categories:
        sql.append("JOIN risk_category rc ON rc.risk_instance_id = ri.id")
        where.append(f"rc.category IN ({','.join('?' * len(intent.categories))})")
        params += [c.value for c in intent.categories]
    if intent.companies:
        where.append("(" + " OR ".join("(c.id = ? OR lower(c.name) LIKE ?)" for _ in intent.companies) + ")")
        for name in intent.companies:
            params += [name.lower(), f"%{name.lower()}%"]
    if intent.source_register:
        where.append("ri.source_register = ?")
        params.append(intent.source_register.value)
    if intent.sector:
        where.append("lower(c.sector) LIKE ?")
        params.append(f"%{intent.sector.lower()}%")
    if intent.status == "removed":
        # a removed risk has no instance in the year it is removed: return its last instance, the year before
        sql.append("JOIN risk_status s ON s.canonical_risk_id = ri.canonical_risk_id AND s.fiscal_year = r.fiscal_year + 1")
    elif intent.status:
        sql.append("JOIN risk_status s ON s.canonical_risk_id = ri.canonical_risk_id AND s.fiscal_year = r.fiscal_year")
    if intent.status:
        where.append("s.status = ?")
        params.append(intent.status)
    if intent.years:  # the year asked about: for removed, the year the risk is gone
        year_col = "s.fiscal_year" if intent.status == "removed" else "r.fiscal_year"
        where.append(f"{year_col} IN ({','.join('?' * len(intent.years))})")
        params += intent.years
    if intent.free_text.strip():
        sql.append("JOIN risk_fts f ON f.id = ri.id")
        where.append("risk_fts MATCH ?")
        params.append(" OR ".join('"' + w.replace('"', '""') + '"' for w in intent.free_text.split()))
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY r.fiscal_year DESC, ri.prominence, ri.page, ri.id LIMIT ?")
    params.append(limit)
    rows = conn.execute("\n".join(sql), params).fetchall()
    return [row_to_record(conn, r) for r in rows]


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok", "schema_version": SCHEMA_VERSION, "db": str(DB)}


@app.get("/risks", response_model=RiskListResponse)
def risks(company: str | None = None, year: int | None = None, category: Category | None = None,
          register: Register | None = None, status: Literal["new", "continuing", "removed", "elevated"] | None = None,
          sector: str | None = None, q: str | None = Query(default=None, description="full-text search over title and description"),
          limit: int = Query(default=100, ge=1, le=1000)):
    intent = QueryIntent(categories=[category] if category else [], companies=[company] if company else [],
                         years=[year] if year else [], source_register=register, status=status, sector=sector, free_text=q or "")
    with conn() as c:
        records = query_records(c, intent, limit)
    return {"intent": intent.model_dump(mode="json"), "count": len(records), "records": records}


@app.get("/risks/{risk_id}", response_model=RiskOut)
def risk(risk_id: str):
    with conn() as c:
        row = c.execute("SELECT ri.*, c.name AS company_name, c.sector, r.fiscal_year, r.review_frequency, r.review_bodies "
                        "FROM risk_instance ri JOIN report r ON r.id = ri.report_id JOIN company c ON c.id = r.company_id WHERE ri.id = ?",
                        (risk_id,)).fetchone()
        if not row:
            raise HTTPException(404, "no such risk")
        return row_to_record(c, row)


@app.get("/questions/{name}", response_model=QuestionResponse)
def brief_question(name: str, company: str | None = None, year: int | None = None, category: str = "cyber", sector: str | None = None):
    """The three brief questions as named endpoints over queries.sql (A2)."""
    sql = app.state.queries.get(name)
    if not sql:
        raise HTTPException(404, f"unknown question; choose one of {sorted(app.state.queries)}")
    with conn() as c:
        rows = c.execute(sql, {"company": company, "year": year, "category": category, "sector": sector}).fetchall()
    return {"question": name, "count": len(rows), "rows": [dict(r) for r in rows]}


@app.get("/companies", response_model=list[CompanyOut])
def companies():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM company ORDER BY name")]


@app.get("/runs", response_model=list[RunOut])
def runs():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM run ORDER BY started_at DESC")]


@app.get("/runs/{run_id}/record", response_model=list[RunCheckOut])
def run_record(run_id: str):
    with conn() as c:
        rows = c.execute("SELECT phase, check_id, outcome, count, strategy, detail FROM run_record WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
    return [{**dict(r), "detail": json.loads(r["detail"] or "{}")} for r in rows]


# --- A3 / A5: question endpoint ------------------------------------------------------------


class Question(BaseModel):
    question: str
    limit: int = 100


def query_understanding_step(question: str) -> tuple[QueryIntent, str]:
    """A3: one structured-output model call turns the question into a QueryIntent, the same filters the structured endpoints take."""
    if app.state.llm is None:
        run_dir = RUNS_DIR / "api"
        run_dir.mkdir(parents=True, exist_ok=True)
        replay = None
        if REPLAY_RUN:  # a path, or a run id under runs/
            replay = Path(REPLAY_RUN) if (Path(REPLAY_RUN) / "llm").is_dir() else RUNS_DIR / REPLAY_RUN
        app.state.llm = LLMClient(run_dir, model=LLM_MODEL, prompt_version=PROMPT_VERSION, replay_dir=replay)
    system = load_prompt("intent", PROMPT_VERSION)
    key = "".join(ch for ch in question.lower() if ch.isalnum())[:40]
    return app.state.llm.complete(f"intent-{key}", system, f"Question: {question}", QueryIntent)


@app.post("/ask", response_model=AskResponse)
def ask(body: Question):
    try:
        intent, call_id = query_understanding_step(body.question)
    except ReplayMiss:
        raise HTTPException(503, "question parsing unavailable: no recorded answer for this question in replay mode")
    except Exception as e:  # provider down: structured endpoints keep working; detail goes to the log, not the client
        import logging
        logging.getLogger("api").warning("intent parsing failed: %s", e)
        raise HTTPException(503, "question parsing unavailable; the structured endpoints still work")
    with conn() as c:
        records = query_records(c, intent, min(max(body.limit, 1), 1000))
    return {"question": body.question, "intent": intent.model_dump(mode="json"), "call_id": call_id,
            "count": len(records), "records": records}
