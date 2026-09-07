"""Several drawings + several specifications in one project, cross-matched."""

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from pdfgen import DrawingCallout, SpecRow, make_drawing_pdf, make_spec_pdf  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from dc_api.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    root = tmp_path_factory.mktemp("multidoc")
    drawing1, drawing2 = root / "sheet1.pdf", root / "sheet2.pdf"
    spec1, spec2 = root / "spec_ov.pdf", root / "spec_vk.pdf"

    # Sheet 1: AHU-01 (param mismatch vs spec 1) + F-03 (clean match, spec 1)
    make_drawing_pdf(
        drawing1,
        [DrawingCallout("AHU-01", ["15 000 м3/ч"]), DrawingCallout("F-03", ["2 шт."])],
    )
    # Sheet 2: R-01 (qty mismatch vs spec 2) + V-17 (missing everywhere)
    make_drawing_pdf(
        drawing2,
        [DrawingCallout("R-01", ["8 шт."]), DrawingCallout("V-17", ["500 м3/ч"])],
    )
    # Spec 1 (OV): AHU-01 + F-03; N-02 exists only here (missing on drawings)
    make_spec_pdf(
        spec1,
        [
            SpecRow("AHU-01", "Приточная установка", "1", characteristic="12 000 м3/ч"),
            SpecRow("F-03", "Фильтр", "2"),
            SpecRow("N-02", "Насос", "2"),
        ],
    )
    # Spec 2 (VK): R-01 only
    make_spec_pdf(spec2, [SpecRow("R-01", "Радиатор", "7")], title="СПЕЦИФИКАЦИЯ ВК-СП")
    return [drawing1, drawing2], [spec1, spec2]


@pytest.fixture(scope="module")
def analyzed(client, files):
    drawings, specs = files
    project_id = client.post("/api/projects", json={"name": "Multidoc"}).json()["id"]
    for path in drawings:
        with open(path, "rb") as fh:
            response = client.post(
                f"/api/projects/{project_id}/documents",
                params={"type": "DRAWING"},
                files={"file": (path.name, fh, "application/pdf")},
            )
        assert response.status_code == 201, response.text
    for path in specs:
        with open(path, "rb") as fh:
            response = client.post(
                f"/api/projects/{project_id}/documents",
                params={"type": "SPECIFICATION"},
                files={"file": (path.name, fh, "application/pdf")},
            )
        assert response.status_code == 201, response.text

    assert client.post(f"/api/projects/{project_id}/analyze").status_code == 202
    for _ in range(240):
        status = client.get(f"/api/projects/{project_id}/analysis").json()
        if status["status"] != "ANALYSIS_STARTED":
            break
        time.sleep(0.5)
    assert status["status"] == "ANALYSIS_COMPLETED", status
    return project_id


class TestMultiDoc:
    def test_all_four_documents_listed(self, client, analyzed):
        docs = client.get(f"/api/projects/{analyzed}/documents").json()
        assert len(docs) == 4
        assert {d["type"] for d in docs} == {"DRAWING", "SPECIFICATION"}

    def test_cross_document_matching(self, client, analyzed):
        findings = client.get(f"/api/projects/{analyzed}/findings").json()
        by_type = {}
        for finding in findings:
            by_type.setdefault(finding["type"], []).append(finding)

        # AHU-01: sheet1 vs spec1
        ahu = next(f for f in by_type["PARAMETER_MISMATCH"] if f["entity"] == "AHU-01")
        assert ahu["drawing_evidence"]["document_filename"] == "sheet1.pdf"
        assert ahu["specification_evidence"]["document_filename"] == "spec_ov.pdf"
        # R-01: sheet2 vs spec2 — different file pair, same analysis
        r01 = next(f for f in by_type["QUANTITY_MISMATCH"] if f["entity"] == "R-01")
        assert r01["drawing_evidence"]["document_filename"] == "sheet2.pdf"
        assert r01["specification_evidence"]["document_filename"] == "spec_vk.pdf"

    def test_presence_across_all_files(self, client, analyzed):
        findings = client.get(f"/api/projects/{analyzed}/findings").json()
        missing_spec = [f for f in findings if f["type"] == "MISSING_IN_SPECIFICATION"]
        assert {f["entity"] for f in missing_spec} == {"V-17"}
        missing_drawing = [f for f in findings if f["type"] == "MISSING_ON_DRAWING"]
        assert {f["entity"] for f in missing_drawing} == {"N-02"}

    def test_clean_match_across_files_is_silent(self, client, analyzed):
        findings = client.get(f"/api/projects/{analyzed}/findings").json()
        assert not any(f["entity"] == "F-03" for f in findings)

    def test_duplicate_upload_rejected(self, client, analyzed, files):
        drawings, _ = files
        with open(drawings[0], "rb") as fh:
            response = client.post(
                f"/api/projects/{analyzed}/documents",
                params={"type": "DRAWING"},
                files={"file": ("sheet1.pdf", fh, "application/pdf")},
            )
        assert response.status_code == 409

    def test_delete_document(self, client, files):
        drawings, specs = files
        project_id = client.post("/api/projects", json={"name": "Del test"}).json()["id"]
        with open(drawings[0], "rb") as fh:
            doc = client.post(
                f"/api/projects/{project_id}/documents",
                params={"type": "DRAWING"},
                files={"file": ("sheet1.pdf", fh, "application/pdf")},
            ).json()
        assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
        assert client.get(f"/api/projects/{project_id}/documents").json() == []
