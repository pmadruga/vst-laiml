"""Response models for the API (DESIGN.md > 2. API). The consumer-facing shape of a record, declared once.

Built from the shared schema so the enum values and field names are the pipeline's; the API adds what the
join supplies (company, fiscal year, review facts) and the parsed intent on the question endpoint.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.schema import Category, QueryIntent, Register


class CitationOut(BaseModel):
    source_register: Register
    section: str
    page: int
    span: str


class CategoryOut(BaseModel):
    category: Category
    is_primary: bool

    @field_validator("is_primary", mode="before")
    @classmethod
    def _int_to_bool(cls, v):
        return bool(v)


class RiskOut(BaseModel):
    """One principal risk as served: the pipeline's record plus the report and company facts it joins to."""

    model_config = ConfigDict(extra="ignore")

    id: str
    report_id: str
    canonical_risk_id: str
    company_name: str
    sector: str | None = None
    fiscal_year: int
    title: str
    description: str
    category: Category
    categories: list[CategoryOut] = Field(default_factory=list, description="primary and secondary")
    source_register: Register
    source_taxonomy: str | None = None
    section: str
    page: int
    citations: list[CitationOut] = Field(min_length=1)
    potential_impact: str | None = None
    mitigation: str | None = None
    prominence: int
    verbatim_span: str
    confidence: float | None = None
    poor_fit: bool = False
    quality_flags: list[str] = Field(default_factory=list)
    review_state: Literal["auto_accepted", "pending_review", "verified", "corrected"]
    review_frequency: str | None = None
    review_bodies: list[str] = Field(default_factory=list)
    model: str | None = None
    prompt_version: str | None = None
    run_id: str | None = None

    @field_validator("poor_fit", mode="before")
    @classmethod
    def _poor_fit(cls, v):
        return bool(v)

    @field_validator("quality_flags", "review_bodies", mode="before")
    @classmethod
    def _json_list(cls, v):
        if isinstance(v, str):
            return json.loads(v) if v else []
        return v or []


class RiskListResponse(BaseModel):
    intent: QueryIntent
    count: int
    records: list[RiskOut]


class AskResponse(RiskListResponse):
    question: str
    call_id: str


class QuestionResponse(BaseModel):
    """A named brief question: rows are whatever queries.sql selects, so they stay a list of objects."""

    question: str
    count: int
    rows: list[dict]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    schema_version: str
    db: str


class CompanyOut(BaseModel):
    id: str
    name: str
    sector: str | None = None
    country: str | None = None


class RunOut(BaseModel):
    run_id: str
    report_id: str | None = None
    pdf: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    phases: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    status: str | None = None

    @field_validator("phases", mode="before")
    @classmethod
    def _json_list(cls, v):
        return json.loads(v) if isinstance(v, str) and v else (v or [])


class RunCheckOut(BaseModel):
    phase: str
    check_id: str
    outcome: Literal["ok", "warning", "error"]
    count: int | None = None
    strategy: str | None = None
    detail: dict = Field(default_factory=dict)
