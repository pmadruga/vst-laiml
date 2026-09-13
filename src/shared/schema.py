"""Pydantic models for every step output, the final structured object, the run record and the API intent.

DESIGN.md > 1. Pipeline; SPECS.md > Run record. Step numbers in docstrings refer to SPECS.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "0.1"


class Category(StrEnum):
    """Closed taxonomy from the brief (PLAN.md > Assumptions)."""

    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    REGULATORY = "regulatory"
    MARKET = "market"
    CLIMATE = "climate"
    CYBER = "cyber"
    SUPPLY_CHAIN = "supply_chain"


class Register(StrEnum):
    ERM_MAIN_RISK = "erm_main_risk"  # p.51 "Main risks" table
    ESRS_FINANCIAL_RISK = "esrs_financial_risk"  # pp.71-74 rows marked as financial risks


Marker = Literal["risk", "opportunity", "impact", "immaterial", "none"]
Outcome = Literal["ok", "warning", "error"]


def now() -> datetime:
    return datetime.now(timezone.utc)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- run record (L6) ---------------------------------------------------------------------


class RunCheck(Strict):
    """One row of `run_record`: one validation outcome for one check of one run."""

    run_id: str
    report_id: str
    phase: Literal["extract", "transform", "load", "api"]
    check_id: str
    outcome: Outcome
    count: int = 0
    strategy: str | None = None
    detail: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)


# --- extract (E1-E8) ---------------------------------------------------------------------


class TocEntry(Strict):
    title: str
    printed_page: int
    pdf_index: int | None = Field(default=None, description="from the link annotation; None when the TOC has no links")


class SectionRange(Strict):
    section: str
    required: bool
    toc_title: str
    matched_title: str | None = None
    match_grade: Literal["exact", "variant", "similarity", "none"]
    match_score: float
    first_page: int = Field(ge=1, description="printed page number")
    last_page: int = Field(ge=1)
    pdf_index: int = Field(ge=0, description="0-based index of first_page in the PDF")
    source: Literal["toc_link", "toc_footer", "config"]
    outcome: Outcome
    quality_flags: list[str] = Field(default_factory=list)


class LocateResult(Strict):
    pdf: str
    page_count: int
    toc_pages: list[int] = Field(description="0-based indices of the pages read as table of contents")
    page_offset: int = Field(description="pdf_index - (printed_page - 1), as measured; informational when links resolve")
    sections: list[SectionRange]
    status: Literal["ok", "warnings", "error"]


class SectionBlock(Strict):
    """E7: one reconstructed block of text with exact provenance."""

    block_id: str
    section: str
    page: int = Field(ge=1, description="printed page number, what a reader cites")
    pdf_index: int = Field(ge=0)
    source_register: Register | None = None
    source_taxonomy: str | None = Field(default=None, description="ESRS topic code such as E1, G1")
    sub_topic: str | None = None
    heading: str
    fields: dict[str, str] = Field(default_factory=dict)
    text: str
    marker: Marker = "none"
    marker_source: Literal["icon+text", "icon", "text", "n/a"] = "n/a"
    value_chain: str | None = None
    actual_or_potential: Literal["actual", "potential"] | None = None
    strategy: Literal["main_risks_table", "esrs_table", "plain_text"]
    quality_flags: list[str] = Field(default_factory=list)


class ParseResult(Strict):
    pdf: str
    blocks: list[SectionBlock]
    page_text: dict[int, str] = Field(default_factory=dict, description="printed page -> plain text, for grounding checks")


# --- transform (T1-T6) -------------------------------------------------------------------


class CandidateRisk(Strict):
    candidate_id: str
    strategy: Literal["register", "llm"]
    source_register: Register | None
    section: str
    page: int = Field(ge=1)
    pdf_index: int = Field(ge=0)
    source_taxonomy: str | None = None
    sub_topic: str | None = None
    verbatim_title: str
    verbatim_span: str = Field(description="the description text as printed; must exist on the page")
    potential_impact: str | None = None
    stated_mitigation: str | None = None
    value_chain: str | None = None
    prominence: int = Field(ge=1, description="1 = ERM main risk, 2 = ESRS financial risk")


class LLMCandidate(Strict):
    """What the identify prompt returns per proposed risk (T1, second strategy)."""

    title: str
    span: str = Field(description="a verbatim sentence from the text that names the risk")


class LLMCandidateList(Strict):
    candidates: list[LLMCandidate]


class IdentifyResult(Strict):
    candidates: list[CandidateRisk]
    llm_candidates: list[CandidateRisk] = Field(default_factory=list)
    agreement: float | None = Field(default=None, description="register candidates matched by an LLM candidate / register count")
    matched: list[tuple[str, str]] = Field(default_factory=list, description="(register candidate_id, llm candidate_id)")


class DescribeOutput(Strict):
    """What the describe prompt returns (T2). This is the JSON schema sent to the model."""

    title: str = Field(max_length=80)
    description: str
    category: Category
    secondary_categories: list[Category] = Field(default_factory=list)
    mitigation: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    poor_fit: bool = False
    poor_fit_reason: str | None = None


class DescribedRisk(Strict):
    candidate_id: str
    output: DescribeOutput
    call_ids: list[str] = Field(default_factory=list)
    votes: dict[str, int] = Field(default_factory=dict, description="category -> votes when self-consistency ran")


class Citation(Strict):
    section: str
    page: int = Field(ge=1)
    source_register: Register
    span: str


class RiskRecord(Strict):
    """One principal risk of one company-year, with provenance. The brief's structured object, per risk."""

    id: str
    report_id: str
    canonical_risk_id: str
    title: str
    description: str
    category: Category
    secondary_categories: list[Category] = Field(default_factory=list)
    source_register: Register
    source_taxonomy: str | None = None
    section: str
    page: int = Field(ge=1)
    citations: list[Citation] = Field(min_length=1)
    potential_impact: str | None = None
    mitigation: str | None = None
    prominence: int = Field(ge=1)
    verbatim_span: str
    confidence: float = Field(ge=0.0, le=1.0)
    poor_fit: bool = False
    quality_flags: list[str] = Field(default_factory=list)
    review_state: Literal["auto_accepted", "pending_review", "verified", "corrected"] = "auto_accepted"
    model: str
    prompt_version: str
    run_id: str


class Company(Strict):
    id: str
    name: str
    sector: str | None = None
    country: str | None = None


class Report(Strict):
    id: str
    company_id: str
    fiscal_year: int
    file: str
    review_bodies: list[str] = Field(default_factory=list)
    review_frequency: str | None = None
    page_offset: int = 0


class RunInfo(Strict):
    run_id: str
    model: str | None = None
    prompt_version: str | None = None
    started_at: datetime = Field(default_factory=now)


class RiskExtraction(Strict):
    """The structured object the brief asks for (task step 3): one report's principal risks."""

    company: Company
    report: Report
    run: RunInfo
    risks: list[RiskRecord]


# --- api (A3) ----------------------------------------------------------------------------


class QueryIntent(Strict):
    """What the question endpoint parses a natural-language question into. Sent to the model as a JSON schema."""

    categories: list[Category] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    source_register: Register | None = None
    status: Literal["new", "continuing", "removed", "elevated"] | None = None
    sector: str | None = None
    free_text: str = ""
