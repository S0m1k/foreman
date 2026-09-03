"""The vertical slice, without HTTP: two PDFs in, verified findings out.

Ground truth built into the synthetic project:
* AHU-01 — airflow 15000 on the drawing vs 12000 in the spec  -> PARAMETER_MISMATCH
* R-01   — 8 pcs on the drawing vs 7 in the spec              -> QUANTITY_MISMATCH
* V-17   — on the drawing only                                -> MISSING_IN_SPECIFICATION
* N-02   — in the spec only                                   -> MISSING_ON_DRAWING
* F-03   — identical on both sides                            -> no finding
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from pdfgen import DrawingCallout, SpecRow, make_drawing_pdf, make_spec_pdf  # noqa: E402

from dc_comparison import compare, verify_findings
from dc_extraction import extract_page_entities
from dc_matching import match_entities
from dc_pdf import parse_pdf
from dc_schemas import DocumentType, FindingType


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("project")
    drawing_pdf = root / "drawing.pdf"
    spec_pdf = root / "specification.pdf"

    make_drawing_pdf(
        drawing_pdf,
        [
            DrawingCallout("AHU-01", ["15 000 м3/ч", "5,5 кВт"]),
            DrawingCallout("R-01", ["8 шт."]),
            DrawingCallout("V-17", ["500 м3/ч"]),
            DrawingCallout("F-03", ["2 шт."]),
        ],
    )
    make_spec_pdf(
        spec_pdf,
        [
            SpecRow("AHU-01", "Приточная установка", "1", characteristic="12 000 м3/ч"),
            SpecRow("R-01", "Радиатор", "7"),
            SpecRow("N-02", "Насос", "2", characteristic="3 кВт"),
            SpecRow("F-03", "Фильтр", "2"),
        ],
    )
    return drawing_pdf, spec_pdf


@pytest.fixture(scope="module")
def findings(project):
    drawing_pdf, spec_pdf = project

    drawing_entities = []
    for page in parse_pdf(drawing_pdf):
        drawing_entities += extract_page_entities(
            str(drawing_pdf), page, "doc_drawing", DocumentType.DRAWING
        )
    spec_entities = []
    for page in parse_pdf(spec_pdf):
        spec_entities += extract_page_entities(
            str(spec_pdf), page, "doc_spec", DocumentType.SPECIFICATION
        )

    assert {e.tag for e in drawing_entities} >= {"AHU-01", "R-01", "V-17", "F-03"}
    assert {e.tag for e in spec_entities} >= {"AHU-01", "R-01", "N-02", "F-03"}

    matches = match_entities(drawing_entities, spec_entities)
    return verify_findings(compare(matches))


def by_type(findings, finding_type):
    return [f for f in findings if f.type == finding_type]


class TestVerticalSlice:
    def test_parameter_mismatch_found(self, findings):
        hits = by_type(findings, FindingType.PARAMETER_MISMATCH)
        assert any(f.entity_key == "AHU-01" and f.parameter == "airflow" for f in hits)
        ahu = next(f for f in hits if f.entity_key == "AHU-01")
        assert ahu.drawing_value.value == 15000
        assert ahu.spec_value.value == 12000

    def test_quantity_mismatch_found(self, findings):
        hits = by_type(findings, FindingType.QUANTITY_MISMATCH)
        assert any(f.entity_key == "R-01" for f in hits)
        r01 = next(f for f in hits if f.entity_key == "R-01")
        assert (r01.drawing_value.value, r01.spec_value.value) == (8, 7)

    def test_missing_in_specification(self, findings):
        hits = by_type(findings, FindingType.MISSING_IN_SPECIFICATION)
        assert any(f.entity_key == "V-17" for f in hits)

    def test_missing_on_drawing(self, findings):
        hits = by_type(findings, FindingType.MISSING_ON_DRAWING)
        assert any(f.entity_key == "N-02" for f in hits)

    def test_matching_object_stays_silent(self, findings):
        assert not any(f.entity_key == "F-03" for f in findings)

    def test_every_finding_has_evidence(self, findings):
        for finding in findings:
            assert finding.drawing_evidence or finding.spec_evidence
            for evidence in (finding.drawing_evidence, finding.spec_evidence):
                if evidence is not None:
                    assert evidence.page >= 1
                    assert evidence.document_id
