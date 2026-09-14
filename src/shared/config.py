"""Static configuration: sections, company metadata, taxonomy rule, model settings, thresholds."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .schema import Register

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PDF = Path(os.environ.get("PDF_PATH", REPO_ROOT / "documentation" / "baseline" / "VestasAnnualReport2025.pdf"))  # in Docker: /reports/...
RUNS_DIR = Path(os.environ.get("RUNS_DIR", REPO_ROOT / "runs"))
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO_ROOT / "data"))
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "risk.db"))
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"  # versioned prompt texts ship with the shared package
EVAL_DIR = REPO_ROOT / "eval"

# --- model (T1 llm strategy, T2, A3) --------------------------------------------------------
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:9292/v1")  # llama-swap, OpenAI-compatible
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-oss")
LLM_WEAK_MODEL = os.environ.get("LLM_WEAK_MODEL", "ministral-3:14b")  # the "weaker model" regression in the eval
LLM_API_KEY = os.environ.get("LLM_API_KEY", "none")
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "600"))
LLM_REASONING_EFFORT = os.environ.get("LLM_REASONING_EFFORT", "low")  # gpt-oss chat-template kwarg
PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "v1")

# --- thresholds (SPECS.md > Validation points) -------------------------------------------
PAGE_COVERAGE_MIN = 0.95
IDENTIFY_AGREEMENT_MIN = 0.7
GROUNDING_PASS_MIN = 0.8
LOW_CONFIDENCE = 0.6  # below this, T2 draws extra samples and takes the majority category
SELF_CONSISTENCY_SAMPLES = 3

PHASES: dict[str, tuple[str, ...]] = {
    "extract": ("E1 toc links", "E2 match titles", "E3 validate sections", "E4-E7 read and persist", "E8 validate extraction"),
    "transform": ("T1 identify", "T2 describe", "T3 merge", "T4 validate and repair", "T6 validate transform"),
    "load": ("L1-L6 sqlite"),
}


@dataclass(frozen=True)
class SectionSpec:
    name: str
    toc_title: str
    first_page: int  # configured fallback (printed)
    last_page: int
    register: Register | None
    required: bool
    layout: str | None  # "main_risks_table" for p.51, "esrs_table" for pp.71-74, None = plain text
    layout_pages: tuple[int, ...] = ()


SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec("risk_management", "Risk management", 50, 51, Register.ERM_MAIN_RISK, True, "main_risks_table", (51,)),
    SectionSpec("material_iros", "Material impacts, risks, and opportunities", 71, 74, Register.ESRS_FINANCIAL_RISK, True, "esrs_table", (71, 72, 73, 74)),
    SectionSpec("climate_change", "Climate change", 85, 92, None, False, None),
    SectionSpec("cyber_security", "Cyber security", 118, 118, None, False, None),
)

# Section-title vocabulary (E2): configured title -> accepted synonyms. Grows as reports are processed.
TITLE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "Risk management": ("Risk management", "Enterprise risk management", "Risks"),
    "Material impacts, risks, and opportunities": ("Material impacts, risks, and opportunities", "Impacts, risks and opportunities"),
    "Climate change": ("Climate change",),
    "Cyber security": ("Cyber security", "Cybersecurity"),
}

COMPANY = {"id": "vestas", "name": "Vestas Wind Systems A/S", "sector": "renewable energy", "country": "DK"}
REPORT = {"id": "vestas-2025", "fiscal_year": 2025}

# Review frequency is a report-level fact from p.50 (PLAN.md > Assumptions)
REVIEW_BODIES = ["Executive Management Team", "Board of Directors", "Audit Committee"]
REVIEW_FREQUENCY_PATTERN = r"reviewed every (\w+) months"

# ESRS topic code -> categories the code makes likely (T2 prior). The model still decides within the seven.
ESRS_CATEGORY_PRIOR: dict[str, tuple[str, ...]] = {
    "E1": ("climate", "regulatory", "market"),
    "E4": ("climate", "regulatory"),
    "E5": ("operational", "supply_chain", "regulatory"),
    "S1": ("operational",),
    "S2": ("operational", "supply_chain", "regulatory"),
    "S3": ("regulatory", "operational"),
    "G1": ("regulatory", "market", "cyber"),
}
