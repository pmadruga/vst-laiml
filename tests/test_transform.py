"""T1-T6 in replay mode over the recorded baseline run: deterministic, no model server (SPECS.md > TRANSFORM)."""

import json
import tempfile
from pathlib import Path

import pytest

from shared.runrecord import RunRecord
from shared.schema import ParseResult, RiskExtraction
from pipeline.transform.describe import describe
from pipeline.transform.enrich import enrich_mitigations
from pipeline.transform.identify import identify, register_candidates
from shared.llm import LLMClient, ReplayMiss
from pipeline.transform.merge import canonical_id, merge
from pipeline.transform.validate import get_nlp, grounding_problems, validate_and_repair, validate_transform


def test_register_candidates_are_the_ten_register_rows(parsed):
    cands = register_candidates(parsed)
    assert len(cands) == 10
    assert sum(c.prominence == 1 for c in cands) == 3 and sum(c.prominence == 2 for c in cands) == 7
    assert all(c.verbatim_span for c in cands)
    cyber = next(c for c in cands if c.verbatim_title == "Cyber attacks")
    assert cyber.stated_mitigation and cyber.potential_impact


def test_replay_reproduces_the_baseline_records(baseline_run):
    parsed = ParseResult.model_validate_json((baseline_run / "parse.json").read_text())
    final = RiskExtraction.model_validate_json((baseline_run / "final.json").read_text())
    run_json = json.loads((baseline_run / "run.json").read_text())
    d = Path(tempfile.mkdtemp())
    rec = RunRecord("replay-test", "vestas-2025", d)
    client = LLMClient(d, model=run_json["model"], prompt_version=run_json["prompt_version"], replay_dir=baseline_run)
    ident = identify(parsed, rec, client)
    desc = describe(ident, rec, client)
    recs, merges = merge(ident.candidates, desc, rec, final.run.run_id, run_json["model"], run_json["prompt_version"])
    recs = enrich_mitigations(recs, parsed, rec)
    recs = validate_and_repair(recs, parsed, rec, client)
    assert [r.title for r in recs] == [r.title for r in final.risks]
    assert [r.category for r in recs] == [r.category for r in final.risks]
    assert [len(r.citations) for r in recs] == [len(r.citations) for r in final.risks]
    assert len(merges) == 1 and validate_transform(recs, len(ident.candidates), merges, parsed, rec) != "error"


def test_replay_miss_is_loud(baseline_run):
    from shared.schema import DescribeOutput
    d = Path(tempfile.mkdtemp())
    client = LLMClient(d, replay_dir=baseline_run)
    with pytest.raises(ReplayMiss):
        client.complete("never-recorded", "system", "a prompt that was never sent", DescribeOutput)


@pytest.mark.parametrize("backend", ["regex", "spacy"])
def test_grounding_catches_invented_facts(baseline_run, backend):
    if backend == "spacy":
        pytest.importorskip("spacy")
    nlp = get_nlp(backend)
    final = RiskExtraction.model_validate_json((baseline_run / "final.json").read_text())
    parsed = ParseResult.model_validate_json((baseline_run / "parse.json").read_text())
    rec = next(r for r in final.risks if r.category == "cyber")
    page = parsed.page_text[rec.page]
    assert all(not p.startswith("span") for p in grounding_problems(rec, page, nlp=nlp))
    bad = rec.model_copy(update={"description": "A SCADA breach in 2019 cost EUR 40m. Attackers from Ruritania targeted turbines."})
    problems = grounding_problems(bad, page, nlp=nlp)
    assert any(p.startswith("number_not_in_text") for p in problems)
    assert any(p.startswith("name_not_in_text") for p in problems)


def test_final_object_shape(baseline_run):
    final = RiskExtraction.model_validate_json((baseline_run / "final.json").read_text())
    assert final.report.id == "vestas-2025" and final.company.id == "vestas"
    assert len(final.risks) == 9
    cyber = next(r for r in final.risks if r.category == "cyber")
    assert {c.page for c in cyber.citations} == {51, 74}
    for r in final.risks:
        assert r.title and r.description and r.section and r.page and r.citations
        assert r.model and r.prompt_version and r.run_id


def test_canonical_id_comes_from_the_register_not_the_model(parsed):
    cands = {c.verbatim_title: c for c in register_candidates(parsed)}
    assert canonical_id(cands["Cyber attacks"]) == "vestas-erm-cyber-attacks"
    assert canonical_id(cands["Cyber security risks"]) == "vestas-g1-cyber-security-risks"


def test_final_object_has_register_fields_and_enriched_mitigation(baseline_run):
    final = RiskExtraction.model_validate_json((baseline_run / "final.json").read_text())
    by = {r.verbatim_title: r for r in final.risks}
    assert by["Cyber attacks"].stated_mitigation and by["Cyber attacks"].canonical_risk_id == "vestas-g1-cyber-security-risks"  # merged: ESRS id kept
    carbon = by["Carbon taxes and tariffs"]
    assert carbon.mitigation and any(f.startswith("mitigation_from_topical_section") for f in carbon.quality_flags)
    assert carbon.mitigation.startswith("Our transition plan")  # the MDR-A actions paragraph, not the quoted cross-reference
    assert any(c.page in (85, 86, 87) for c in carbon.citations)
