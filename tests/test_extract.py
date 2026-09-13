"""E1-E8 against the real report (SPECS.md > EXTRACT)."""

import tempfile
from pathlib import Path

from shared.config import SectionSpec
from pipeline.extract.locate import locate, match_title, normalise
from pipeline.extract.validate import validate_extraction
from shared.runrecord import RunRecord
from shared.schema import TocEntry

ESRS_RISKS = {
    ("E1", "Carbon taxes and tariffs"), ("S1", "Cost implication of injuries in own workforce"),
    ("S2", "Cost implications of injuries to contractors and sub-contractors"), ("S2", "Fines related to forced or child labour"),
    ("G1", "Insufficient market conditions"), ("G1", "Cyber security risks"), ("G1", "Risk of corruption and bribery"),
}
OPPORTUNITIES = {"Low-emission materials (entity-specific)", "Growth rate of the wind industry (entity-specific)", "Recyclable blades"}


# --- E1-E3 ---------------------------------------------------------------------------------


def test_sections_resolve_through_toc_links(located):
    by = {s.section: s for s in located.sections}
    assert located.status == "ok"
    assert (by["risk_management"].first_page, by["risk_management"].last_page, by["risk_management"].pdf_index) == (50, 51, 49)
    assert (by["material_iros"].first_page, by["material_iros"].last_page, by["material_iros"].pdf_index) == (71, 74, 70)
    assert by["cyber_security"].pdf_index == 117
    assert all(s.source == "toc_link" and s.match_grade == "exact" for s in located.sections)


def test_qualifier_in_toc_title_is_dropped_by_normalisation(located):
    cyber = next(s for s in located.sections if s.section == "cyber_security")
    assert cyber.matched_title == "Cyber security (entity-specific)"
    assert normalise(cyber.matched_title) == "cyber security"


def test_match_grades():
    entries = [TocEntry(title="Risk management and internal control", printed_page=50),
               TocEntry(title="Material impacts, risks and opportunity", printed_page=71),
               TocEntry(title="Risk factors", printed_page=12)]
    e, grade, score = match_title(SectionSpec("rm", "Risk management", 50, 51, None, True, None), entries)
    assert grade == "variant" and e.printed_page == 50
    e, grade, score = match_title(SectionSpec("mi", "Material impacts, risks, and opportunities", 71, 74, None, True, None), entries)
    assert grade == "similarity" and score >= 0.85 and e.printed_page == 71
    e, grade, _ = match_title(SectionSpec("x", "Quarterly hedging review", 1, 1, None, False, None), entries)
    assert e is None and grade == "none"


def test_required_section_not_found_is_an_error_and_optional_a_warning(pdf_path):
    rec = RunRecord("t", "vestas-2025", Path(tempfile.mkdtemp()))
    specs = (SectionSpec("risk_management", "Enterprise risk review", 50, 51, None, True, None),
             SectionSpec("climate_change", "Weather outlook", 85, 92, None, False, None))
    res = locate(pdf_path, rec, specs)
    by = {s.section: s for s in res.sections}
    assert by["risk_management"].outcome == "error" and by["risk_management"].source == "config"
    assert by["climate_change"].outcome == "warning"
    assert res.status == "error"
    grades = [r for r in rec.rows if r.check_id == "section_match_grade"]
    assert {r.outcome for r in grades} == {"error", "warning"}


def test_shifted_pdf_still_resolves(shifted_pdf_path):
    rec = RunRecord("t", "vestas-2025", Path(tempfile.mkdtemp()))
    res = locate(shifted_pdf_path, rec)
    by = {s.section: s for s in res.sections}
    assert res.page_count == 196
    assert by["risk_management"].first_page == 50  # printed number, what a reader cites
    assert by["risk_management"].pdf_index == 50  # shifted by one
    assert res.status == "ok"


# --- E4-E7 ---------------------------------------------------------------------------------


def test_p51_three_columns_reconstructed(parsed):
    erm = [b for b in parsed.blocks if b.strategy == "main_risks_table"]
    assert [b.heading for b in erm] == ["Geopolitics and regulatory framework", "Project execution", "Cyber attacks"]
    by = {b.heading: b for b in erm}
    assert by["Cyber attacks"].fields["description"].startswith("Vestas’ digital and other critical assets are exposed to cyber attacks")
    assert "Project execution at Vestas involves" in by["Project execution"].fields["description"]
    assert "Project execution at Vestas" not in by["Cyber attacks"].text
    assert by["Geopolitics and regulatory framework"].fields["how_we_manage_it"].startswith("We manage geopolitical risks")
    assert set(by["Cyber attacks"].fields) == {"description", "potential_impact", "how_we_manage_it"}


def test_naive_text_order_scrambles_p51(pdf_path):
    import pymupdf
    text = pymupdf.open(str(pdf_path))[50].get_text("text")
    assert text.index("Cyber attacks") < text.index("Project execution at Vestas involves")


def test_esrs_rows_and_markers(parsed):
    fin = [b for b in parsed.blocks if b.strategy == "esrs_table" and b.marker in ("risk", "opportunity")]
    assert {(b.source_taxonomy, b.heading) for b in fin if b.marker == "risk"} == ESRS_RISKS
    assert {b.heading for b in fin if b.marker == "opportunity"} == OPPORTUNITIES
    assert all(b.marker_source == "icon+text" for b in fin), [(b.heading, b.marker_source, b.quality_flags) for b in fin]
    assert all(b.source_register == "esrs_financial_risk" for b in fin if b.marker == "risk")
    assert all(b.source_register is None for b in parsed.blocks if b.marker != "risk")


def test_esrs_row_metadata(parsed):
    carbon = next(b for b in parsed.blocks if b.heading == "Carbon taxes and tariffs")
    assert (carbon.page, carbon.pdf_index, carbon.source_taxonomy, carbon.value_chain) == (71, 70, "E1", "Own operations")
    assert carbon.sub_topic == "Climate change adaptation" and carbon.fields["materiality"] == "Financial materiality"
    cyber = next(b for b in parsed.blocks if b.heading == "Cyber security risks")
    assert (cyber.page, cyber.source_taxonomy, cyber.sub_topic) == (74, "G1", "Cyber security")


# --- E8 ------------------------------------------------------------------------------------


def test_extraction_validation_passes(pdf_path, located, parsed):
    rec = RunRecord("t", "vestas-2025", Path(tempfile.mkdtemp()))
    status = validate_extraction(pdf_path, located, parsed, rec)
    by = {r.check_id: r for r in rec.rows}
    assert status != "error"
    assert by["main_risks_shape"].outcome == "ok"
    assert by["marker_disagreement"].detail["risks"] == 7 and by["marker_disagreement"].detail["opportunities"] == 3
    assert by["text_not_on_page"].outcome == "ok"
    assert by["block_ids_and_ranges"].outcome == "ok"
