import json
import tempfile
from pathlib import Path

import pytest

from shared.config import DEFAULT_PDF, EVAL_DIR, RUNS_DIR
from pipeline.extract.locate import locate
from pipeline.extract.parse import parse
from shared.runrecord import RunRecord

# the recorded evidence run ships with the repo under eval/runs; a fresh local run under runs/ is the fallback
BASELINE = (EVAL_DIR / "runs" / "baseline") if (EVAL_DIR / "runs" / "baseline" / "final.json").exists() else RUNS_DIR / "baseline"


@pytest.fixture(scope="session")
def pdf_path():
    if not DEFAULT_PDF.exists():
        pytest.skip(f"source PDF not present at {DEFAULT_PDF}")
    return DEFAULT_PDF


@pytest.fixture(scope="session")
def record():
    return RunRecord("test", "vestas-2025", Path(tempfile.mkdtemp()))


@pytest.fixture(scope="session")
def located(pdf_path, record):
    return locate(pdf_path, record)


@pytest.fixture(scope="session")
def parsed(pdf_path, located):
    return parse(pdf_path, located)


@pytest.fixture(scope="session")
def baseline_run():
    """A recorded run: its llm/ records make the transform phase replayable without a model server."""
    if not (BASELINE / "final.json").exists():
        pytest.skip("no recorded baseline run under eval/runs or runs/; run `uv run python etl.py --run-id baseline` once with the model server up")
    return BASELINE


@pytest.fixture(scope="session")
def shifted_pdf_path(pdf_path, tmp_path_factory):
    """The report with one blank page inserted at the front: printed numbers no longer equal PDF indices."""
    import pymupdf

    src = pymupdf.open(str(pdf_path))
    dst = pymupdf.open()
    dst.new_page(width=src[0].rect.width, height=src[0].rect.height)
    dst.insert_pdf(src)
    out = tmp_path_factory.mktemp("shifted") / "shifted.pdf"
    dst.save(str(out))
    return out
