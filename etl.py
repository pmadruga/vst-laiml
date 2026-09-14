#!/usr/bin/env python
"""Control file for the ETL pipeline (DESIGN.md > 1. Pipeline).

    python etl.py --extract                       # E1-E8   -> runs/<run_id>/{locate,parse}.json
    python etl.py --transform --run-id R          # T1-T6   -> runs/R/{identify,describe,final}.json  (model calls recorded)
    python etl.py --transform --run-id R2 --replay R   # same, served from R's recorded calls: no model
    python etl.py --load --run-id R               # L1-L6   -> data/risk.db
    python etl.py                                  # all three phases, new run id
    python etl.py --list

Options: --pdf, --model, --prompt-version, --no-llm-identify (skip the second identify strategy),
--break-parser (regression: naive text order on p.51), --grounding (T4 checks: regex or spacy), --db.
run.json keeps every invocation of a run id, so a run's provenance survives later phases and re-scoring.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from shared.config import (COMPANY, DB_PATH, DEFAULT_PDF, EVAL_DIR, GROUNDING_NLP, LLM_MODEL, PHASES, PROMPT_VERSION, REPORT, REVIEW_BODIES, RUNS_DIR)
from pipeline.extract.locate import locate
from pipeline.extract.parse import parse
from pipeline.extract.validate import validate_extraction
from pipeline.load.sqlite import load, review_frequency
from shared.runrecord import RunRecord
from shared.schema import (Company, IdentifyResult, LocateResult, ParseResult, Report, RiskExtraction, RiskRecord, RunInfo, DescribedRisk)
from pipeline.transform.describe import describe
from pipeline.transform.enrich import enrich_mitigations
from pipeline.transform.identify import identify
from shared.llm import LLMClient
from pipeline.transform.merge import merge
from pipeline.transform.validate import validate_and_repair, validate_transform


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="etl.py", description="Annual report PDF -> structured principal-risk records -> SQLite.")
    p.add_argument("--extract", action="store_true"); p.add_argument("--transform", action="store_true"); p.add_argument("--load", action="store_true")
    p.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    p.add_argument("--run-id", default=None, help="run directory under runs/ (default: UTC timestamp)")
    p.add_argument("--replay", default=None, metavar="RUN_ID", help="serve model calls from that run's llm/ records")
    p.add_argument("--model", default=LLM_MODEL); p.add_argument("--prompt-version", default=PROMPT_VERSION)
    p.add_argument("--no-llm-identify", action="store_true", help="skip the model-proposed identify strategy (T1)")
    p.add_argument("--break-parser", action="store_true", help="regression: replace the p.51 table parser with naive text order")
    p.add_argument("--grounding", choices=("regex", "spacy"), default=GROUNDING_NLP, help="T4 grounding checks: hand-rolled regex or spaCy")
    p.add_argument("--db", type=Path, default=DB_PATH)
    p.add_argument("--list", action="store_true")
    return p


def resolve_run(ref: str) -> Path:
    """A run to replay from: a path, a run id under runs/, or a run id under eval/runs/."""
    for cand in (Path(ref), RUNS_DIR / ref, EVAL_DIR / "runs" / ref):
        if (cand / "llm").is_dir():
            return cand
    raise SystemExit(f"no recorded run at {ref!r} (looked in ./, runs/, eval/runs/)")


def write(d: Path, name: str, model) -> None:
    (d / name).write_text(model.model_dump_json(indent=2) + "\n")


def phase_extract(args, d: Path, rec: RunRecord) -> int:
    located = locate(args.pdf, rec)
    write(d, "locate.json", located)
    print(f"[extract] locate: {located.status}; toc pages {located.toc_pages}; offset {located.page_offset:+d}")
    for s in located.sections:
        flag = f"  ! {'; '.join(s.quality_flags)}" if s.quality_flags else ""
        print(f"  {s.section:<18} pp.{s.first_page}-{s.last_page} (idx {s.pdf_index}) via {s.source:<10} {s.match_grade:<10} {s.outcome}{flag}")
    if located.status == "error":
        print("[extract] a required section failed: report deferred (E3)")
        return 3
    if args.break_parser:
        from pipeline.extract import parse as parse_mod
        parse_mod.LAYOUT_PARSERS["main_risks_table"] = _naive_main_risks  # the "breaking the parser" regression
        rec.add("extract", "parser_override", "warning", strategy="naive_text_order", note="--break-parser")
    parsed = parse(args.pdf, located)
    write(d, "parse.json", parsed)
    status = validate_extraction(args.pdf, located, parsed, rec)
    risks = [b for b in parsed.blocks if b.marker == "risk"]
    print(f"[extract] parse: {len(parsed.blocks)} blocks; {len(risks)} risk blocks (ERM {sum(b.source_register == 'erm_main_risk' for b in risks)}, ESRS {sum(b.source_register == 'esrs_financial_risk' for b in risks)}); E8 {status}")
    print(rec.summary("extract"))
    return 0 if status != "error" else 3


def _naive_main_risks(page, page_no, pdf_index, section):
    """Regression stand-in for E5: the page's body text in reading order, cut into three equal columns and each
    column into three equal fields. Well-shaped, so E8 passes, but text lands under the wrong risk and field."""
    from pipeline.extract.pdf import plain_text
    from shared.schema import Register, SectionBlock
    heads = ["Geopolitics and regulatory framework", "Project execution", "Cyber attacks"]
    text = " ".join(plain_text(page).split())
    body = text.split("Cyber attacks", 1)[1] if "Cyber attacks" in text else text
    ws = body.split()
    n = max(1, len(ws) // 3)
    chunks = [" ".join(ws[i * n:(i + 1) * n]) for i in range(3)]

    def thirds(chunk: str) -> dict[str, str]:
        cw = chunk.split(); m = max(1, len(cw) // 3)
        return {"description": " ".join(cw[:m]), "potential_impact": " ".join(cw[m:2 * m]), "how_we_manage_it": " ".join(cw[2 * m:])}
    return [SectionBlock(block_id=f"p{page_no}-erm-{i + 1}", section=section, page=page_no, pdf_index=pdf_index,
                         source_register=Register.ERM_MAIN_RISK, heading=heads[i], fields=thirds(chunk), text=chunk,
                         marker="risk", marker_source="n/a", strategy="main_risks_table", quality_flags=["naive_text_order"])
            for i, chunk in enumerate(chunks)]


def phase_transform(args, d: Path, rec: RunRecord) -> int:
    located = LocateResult.model_validate_json((d / "locate.json").read_text())
    parsed = ParseResult.model_validate_json((d / "parse.json").read_text())
    replay = resolve_run(args.replay) if args.replay else None
    client = LLMClient(d, model=args.model, prompt_version=args.prompt_version, replay_dir=replay)
    mode = f"replay of {args.replay}" if replay else f"live {args.model}"
    print(f"[transform] model calls: {mode}; prompt {args.prompt_version}")

    identified = identify(parsed, rec, None if args.no_llm_identify else client)
    write(d, "identify.json", identified)
    print(f"[transform] T1 identify: {len(identified.candidates)} register candidates; llm proposed {len(identified.llm_candidates)}; agreement {identified.agreement}")

    described = describe(identified, rec, client)
    (d / "describe.json").write_text(json.dumps([x.model_dump(mode="json") for x in described], indent=2) + "\n")
    print(f"[transform] T2 describe: {len(described)} records; poor fit {sum(x.output.poor_fit for x in described)}; voted {sum(len(x.call_ids) > 1 for x in described)}")

    records, merges = merge(identified.candidates, described, rec, rec.run_id, args.model, args.prompt_version)
    print(f"[transform] T3 merge: {len(records)} records ({len(merges)} merged)")
    records = enrich_mitigations(records, parsed, rec)
    print(f"[transform] T5 enrich: {sum(any(f.startswith('mitigation_from_topical') for f in r.quality_flags) for r in records)} mitigations from the topical sections")

    records = validate_and_repair(records, parsed, rec, client, args.grounding)
    flagged = [r.id for r in records if r.quality_flags]
    print(f"[transform] T4 validate and repair: {len(flagged)} flagged {flagged}")

    page50 = parsed.page_text.get(50, "")
    extraction = RiskExtraction(
        company=Company(**COMPANY),
        report=Report(id=REPORT["id"], company_id=COMPANY["id"], fiscal_year=REPORT["fiscal_year"], file=str(args.pdf.name),
                      review_bodies=REVIEW_BODIES, review_frequency=review_frequency(page50), page_offset=located.page_offset),
        run=RunInfo(run_id=rec.run_id, model=args.model, prompt_version=args.prompt_version), risks=records)
    write(d, "final.json", extraction)

    replay_records = None
    if replay is None:
        # T6 determinism: replay our own recorded calls and compare
        rd = Path(tempfile.mkdtemp(prefix="replay-check-"))  # scratch: nothing from the check is kept
        rc = LLMClient(rd, model=args.model, prompt_version=args.prompt_version, replay_dir=d)
        rrec = RunRecord(rec.run_id + "-replay", rec.report_id, rd)
        try:
            ident2 = identify(parsed, rrec, None if args.no_llm_identify else rc)
            desc2 = describe(ident2, rrec, rc)
            rec2, _ = merge(ident2.candidates, desc2, rrec, rec.run_id, args.model, args.prompt_version)
            rec2 = enrich_mitigations(rec2, parsed, rrec)
            replay_records = validate_and_repair(rec2, parsed, rrec, rc, args.grounding)
        except Exception as e:  # a replay miss is itself the finding
            rec.add("transform", "pipeline_reproducibility", "error", count=1, error=str(e)[:200])
    status = validate_transform(records, len(identified.candidates), merges, parsed, rec, replay_records)
    print(f"[transform] T6: {status}")
    print(rec.summary("transform"))
    for r in records:
        print(f"  {r.id} p.{r.page:<3} {r.category:<12} {r.title:<45} conf {r.confidence:.2f} cites {len(r.citations)} mit {'yes' if r.mitigation else 'no '} {r.quality_flags}")
    return 0 if status != "error" else 3


def phase_load(args, d: Path, rec: RunRecord) -> int:
    extraction = RiskExtraction.model_validate_json((d / "final.json").read_text())
    parsed = ParseResult.model_validate_json((d / "parse.json").read_text())
    if rec.rows and any(r.check_id == "eval_scores" and r.outcome == "error" for r in rec.rows):
        print("[load] refused: a golden-set evaluator failed (T6). See runs/<id>/eval/report.json")
        return 3
    phases = json.loads((d / "run.json").read_text()).get("phases", ["load"]) if (d / "run.json").exists() else ["load"]
    meta = {"pdf": str(args.pdf), "phases": phases, "finished_at": datetime.now(timezone.utc).isoformat()}
    status = load(extraction, rec, args.db, parsed.page_text.get(50, ""), meta)
    print(f"[load] {status}; database {args.db}")
    print(rec.summary("load"))
    return 0 if status != "error" else 3


def write_run_json(d: Path, run_id: str, invocation: dict) -> dict:
    """Append this invocation to run.json. Top-level model, prompt and replay come from the latest invocation that ran the
    transform (the one whose calls are recorded); phases is every phase any invocation ran."""
    path = d / "run.json"
    meta = json.loads(path.read_text()) if path.exists() else {}
    invocations = meta.get("invocations") or ([{k: meta[k] for k in ("phases", "pdf", "model", "prompt_version", "replay", "started_at") if k in meta}] if meta else [])
    invocations.append(invocation)
    source = next((i for i in reversed(invocations) if "transform" in i.get("phases", [])), invocation)
    meta = {"run_id": run_id, "pdf": source.get("pdf"), "model": source.get("model"), "prompt_version": source.get("prompt_version"),
            "replay": source.get("replay"), "grounding": source.get("grounding"),
            "phases": [ph for ph in ("extract", "transform", "load") if any(ph in i.get("phases", []) for i in invocations)],
            "invocations": invocations}
    path.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        for ph, steps in PHASES.items():
            print(f"--{ph:<10} {' -> '.join(steps) if isinstance(steps, tuple) else steps}")
        return 0
    wanted = [ph for ph in ("extract", "transform", "load") if getattr(args, ph)] or ["extract", "transform", "load"]
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = RUNS_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    rec = RunRecord(run_id, REPORT["id"], d)
    write_run_json(d, run_id, {"phases": wanted, "pdf": str(args.pdf), "model": args.model, "prompt_version": args.prompt_version,
                               "replay": args.replay, "grounding": args.grounding, "started_at": datetime.now(timezone.utc).isoformat()})
    print(f"run {run_id} -> {d}")
    for ph in wanted:
        rc = {"extract": phase_extract, "transform": phase_transform, "load": phase_load}[ph](args, d, rec)
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
