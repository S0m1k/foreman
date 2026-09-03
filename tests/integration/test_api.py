"""Definition-of-Done over HTTP: create -> upload -> analyze -> findings -> review."""

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
def pdfs(tmp_path_factory):
    root = tmp_path_factory.mktemp("api_pdfs")
    drawing, spec = root / "drawing.pdf", root / "spec.pdf"
    make_drawing_pdf(
        drawing,
        [
            DrawingCallout("AHU-01", ["15 000 м3/ч"]),
            DrawingCallout("R-01", ["8 шт."]),
            DrawingCallout("V-17", ["500 м3/ч"]),
        ],
    )
    make_spec_pdf(
        spec,
        [
            SpecRow("AHU-01", "Приточная установка", "1", characteristic="12 000 м3/ч"),
            SpecRow("R-01", "Радиатор", "7"),
        ],
    )
    return drawing, spec


@pytest.fixture(scope="module")
def analyzed_project(client, pdfs):
    drawing, spec = pdfs
    project = client.post("/api/projects", json={"name": "Test HVAC"}).json()
    project_id = project["id"]

    for path, doc_type in ((drawing, "DRAWING"), (spec, "SPECIFICATION")):
        with open(path, "rb") as fh:
            response = client.post(
                f"/api/projects/{project_id}/documents",
                params={"type": doc_type},
                files={"file": (path.name, fh, "application/pdf")},
            )
        assert response.status_code == 201, response.text

    response = client.post(f"/api/projects/{project_id}/analyze")
    assert response.status_code == 202, response.text

    for _ in range(120):
        status = client.get(f"/api/projects/{project_id}/analysis").json()
        if status["status"] in ("ANALYSIS_COMPLETED", "ANALYSIS_FAILED"):
            break
        time.sleep(0.5)
    assert status["status"] == "ANALYSIS_COMPLETED", status
    return project_id, status


class TestApiFlow:
    def test_project_listing(self, client, analyzed_project):
        project_id, _ = analyzed_project
        listed = client.get("/api/projects").json()
        assert any(p["id"] == project_id for p in listed)

    def test_stages_are_reported(self, analyzed_project):
        _, status = analyzed_project
        stages = {s["stage"]: s["status"] for s in status["stages"]}
        assert stages["compare"] == "DONE"
        assert stages["verify_findings"] == "DONE"
        assert "PENDING" not in stages.values()

    def test_findings_present_with_evidence(self, client, analyzed_project):
        project_id, _ = analyzed_project
        findings = client.get(f"/api/projects/{project_id}/findings").json()
        types = {f["type"] for f in findings}
        assert "PARAMETER_MISMATCH" in types
        assert "QUANTITY_MISMATCH" in types
        assert "MISSING_IN_SPECIFICATION" in types
        for finding in findings:
            assert finding["drawing_evidence"] or finding["specification_evidence"]

    def test_finding_detail_and_values(self, client, analyzed_project):
        project_id, _ = analyzed_project
        findings = client.get(f"/api/projects/{project_id}/findings").json()
        ahu = next(f for f in findings if f["type"] == "PARAMETER_MISMATCH")
        detail = client.get(f"/api/findings/{ahu['id']}").json()
        assert detail["drawing_value"]["value"] == 15000
        assert detail["specification_value"]["value"] == 12000

    def test_evidence_crop_served(self, client, analyzed_project):
        project_id, _ = analyzed_project
        findings = client.get(f"/api/projects/{project_id}/findings").json()
        ahu = next(f for f in findings if f["type"] == "PARAMETER_MISMATCH")
        response = client.get(f"/api/findings/{ahu['id']}/evidence/drawing.png")
        assert response.status_code == 200
        assert response.content.startswith(b"\x89PNG")

    def test_page_image_served(self, client, analyzed_project):
        project_id, _ = analyzed_project
        docs = client.get(f"/api/projects/{project_id}/documents").json()
        drawing = next(d for d in docs if d["type"] == "DRAWING")
        response = client.get(f"/api/documents/{drawing['id']}/pages/1.png")
        assert response.status_code == 200
        assert response.content.startswith(b"\x89PNG")

    def test_confirm_and_false_positive(self, client, analyzed_project):
        project_id, _ = analyzed_project
        findings = client.get(f"/api/projects/{project_id}/findings").json()
        first, second = findings[0], findings[1]
        assert client.post(f"/api/findings/{first['id']}/confirm").json()["status"] == "CONFIRMED"
        assert (
            client.post(f"/api/findings/{second['id']}/false-positive").json()["status"]
            == "FALSE_POSITIVE"
        )
        filtered = client.get(
            f"/api/projects/{project_id}/findings", params={"status": "CONFIRMED"}
        ).json()
        assert [f["id"] for f in filtered] == [first["id"]]

    def test_filter_by_severity(self, client, analyzed_project):
        project_id, _ = analyzed_project
        high = client.get(
            f"/api/projects/{project_id}/findings", params={"severity": "HIGH"}
        ).json()
        assert all(f["severity"] == "HIGH" for f in high)

    def test_analyze_requires_both_documents(self, client):
        project = client.post("/api/projects", json={"name": "Empty"}).json()
        response = client.post(f"/api/projects/{project['id']}/analyze")
        assert response.status_code == 422

    def test_non_pdf_rejected(self, client, analyzed_project):
        project_id, _ = analyzed_project
        response = client.post(
            f"/api/projects/{project_id}/documents",
            params={"type": "DRAWING"},
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 422
