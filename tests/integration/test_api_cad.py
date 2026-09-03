"""DXF drawing + PDF specification through the HTTP API, end to end."""

import sys
import time
from pathlib import Path

import ezdxf
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from pdfgen import SpecRow, make_spec_pdf  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from dc_api.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    root = tmp_path_factory.mktemp("cad_api")
    dxf = root / "plan.dxf"
    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    msp.add_text("AHU-01", dxfattribs={"height": 5}).set_placement((10, 100))
    msp.add_text("15 000 м3/ч", dxfattribs={"height": 3}).set_placement((10, 92))
    msp.add_text("V-17", dxfattribs={"height": 5}).set_placement((80, 100))
    msp.add_lwpolyline([(0, 0), (200, 0), (200, 120), (0, 120), (0, 0)])
    doc.saveas(str(dxf))

    spec = root / "spec.pdf"
    make_spec_pdf(
        spec,
        [SpecRow("AHU-01", "Приточная установка", "1", characteristic="12 000 м3/ч")],
    )
    return dxf, spec


@pytest.fixture(scope="module")
def analyzed(client, files):
    dxf, spec = files
    project = client.post("/api/projects", json={"name": "CAD check"}).json()
    project_id = project["id"]

    with open(dxf, "rb") as fh:
        response = client.post(
            f"/api/projects/{project_id}/documents",
            params={"type": "DRAWING"},
            files={"file": ("plan.dxf", fh, "application/octet-stream")},
        )
    assert response.status_code == 201, response.text
    with open(spec, "rb") as fh:
        response = client.post(
            f"/api/projects/{project_id}/documents",
            params={"type": "SPECIFICATION"},
            files={"file": ("spec.pdf", fh, "application/pdf")},
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


class TestCadFlow:
    def test_findings_from_dxf_drawing(self, client, analyzed):
        findings = client.get(f"/api/projects/{analyzed}/findings").json()
        by_type = {f["type"]: f for f in findings}
        assert "PARAMETER_MISMATCH" in by_type
        assert by_type["PARAMETER_MISMATCH"]["drawing_value"]["value"] == 15000
        assert "MISSING_IN_SPECIFICATION" in by_type
        assert by_type["MISSING_IN_SPECIFICATION"]["entity"] == "V-17"

    def test_evidence_crop_from_rendered_cad(self, client, analyzed):
        findings = client.get(f"/api/projects/{analyzed}/findings").json()
        mismatch = next(f for f in findings if f["type"] == "PARAMETER_MISMATCH")
        response = client.get(f"/api/findings/{mismatch['id']}/evidence/drawing.png")
        assert response.status_code == 200
        assert response.content.startswith(b"\x89PNG")

    def test_page_image_from_rendered_cad(self, client, analyzed):
        docs = client.get(f"/api/projects/{analyzed}/documents").json()
        drawing = next(d for d in docs if d["type"] == "DRAWING")
        assert drawing["filename"] == "plan.dxf"
        response = client.get(f"/api/documents/{drawing['id']}/pages/1.png")
        assert response.status_code == 200

    def test_unsupported_extension_rejected(self, client, analyzed):
        response = client.post(
            f"/api/projects/{analyzed}/documents",
            params={"type": "DRAWING"},
            files={"file": ("model.rvt", b"data", "application/octet-stream")},
        )
        assert response.status_code == 422
