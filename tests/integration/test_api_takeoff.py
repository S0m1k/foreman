"""Duct takeoff over HTTP: upload album -> run -> sheets -> sheet -> edit -> export."""

import io
import sys
import time
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from pdfgen import DuctSegment, SpecDuct, SpecFitting, make_album_pdf  # noqa: E402

RED = (1.0, 0.0, 0.0)
BLUE = (0.0, 0.0, 1.0)


@pytest.fixture(scope="module")
def client():
    from dc_api.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def album_pdf(tmp_path_factory):
    path = tmp_path_factory.mktemp("takeoff") / "ОВ альбом.pdf"
    make_album_pdf(
        path,
        [DuctSegment((0, 0), (10, 0), 600, RED), DuctSegment((0, 6), (8, 6), 500, BLUE)],
        callouts=[((140, 600), ["П1", "600x350"], (3.0, 0.0))],
        spec=[SpecDuct("П1", "600x350", 12.5), SpecDuct("В1", "500x300", 9.0)],
        labels=[((300, 400), "АМР 400х200"), ((300, 430), "АМР 400x200"),
                ((300, 460), "АДР-К 650x300"), ((600, 400), "КЛАПЪ-(60)-НО-100x100")],
        fittings=[SpecFitting("П1", "Решетка АМР 400х200", 5),
                  SpecFitting("П1", "Клапан КЛАПЪ-(60)-НО-100x100", 1)],
    )
    return path


def _new_project(client, name="Takeoff"):
    return client.post("/api/projects", json={"name": name}).json()["id"]


def _upload(client, project_id, path, doc_type="DRAWING"):
    with open(path, "rb") as fh:
        response = client.post(
            f"/api/projects/{project_id}/documents",
            params={"type": doc_type},
            files={"file": (path.name, fh, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _wait(client, project_id):
    for _ in range(240):
        body = client.get(f"/api/projects/{project_id}/takeoff").json()
        if body["status"] in ("COMPLETED", "FAILED"):
            return body
        time.sleep(0.25)
    raise AssertionError("takeoff did not finish")


@pytest.fixture(scope="module")
def done(client, album_pdf):
    project_id = _new_project(client)
    document_id = _upload(client, project_id, album_pdf)
    response = client.post(f"/api/projects/{project_id}/takeoff")
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "RUNNING"
    body = _wait(client, project_id)
    assert body["status"] == "COMPLETED", body.get("error")
    return project_id, document_id, body


def test_summary_lists_every_sheet_with_its_kind(done):
    _, document_id, body = done
    sheets = [(s["document_id"], s["page"], s["kind"]) for s in body["sheets"]]
    assert sheets == [(document_id, 1, "plan"), (document_id, 2, "schematic"),
                      (document_id, 3, "specification")]
    plan = body["sheets"][0]
    assert plan["title"] == "План 1 этажа"
    assert plan["filename"] == "ОВ альбом.pdf"
    assert plan["run_count"] >= 2
    assert plan["length_m"] == pytest.approx(18.0, abs=1.0)
    assert body["sheets"][1]["run_count"] == 0


def test_summary_reconciles_systems_against_the_specification(done):
    _, _, body = done
    systems = {s["system"]: s for s in body["systems"]}
    assert systems["П1"]["spec_m"] == 12.5
    assert systems["П1"]["measured_m"] == pytest.approx(10.0, abs=0.6)
    assert systems["В1"]["spec_m"] == 9.0


def test_sheet_carries_runs_geometry_and_image(client, done):
    project_id, document_id, body = done
    response = client.get(f"/api/takeoffs/{body['id']}/sheets/{document_id}/1")
    assert response.status_code == 200, response.text
    sheet = response.json()
    assert sheet["scale"] == 100 and sheet["width"] == 1200
    assert sheet["image_url"] == f"/api/documents/{document_id}/pages/1.png?max_side=6000"
    assert sheet["overrides"] == {}
    run = sheet["runs"][0]
    assert {"id", "system", "section", "width_mm", "insulated", "length_m", "p0", "p1"} <= set(run)
    assert set(sheet["spec_m"]) == {"П1", "В1"}
    assert sheet["other_sheets_m"] == {}, "there is only one plan sheet"


def test_sheet_image_is_sized_for_a_browser(client, done):
    """A full-size plan at the default 200 dpi is ~14000x6600 px; browsers
    silently refuse to draw that inside an SVG <image>."""
    from PIL import Image

    _, document_id, _ = done
    response = client.get(f"/api/documents/{document_id}/pages/1.png", params={"max_side": 600})
    assert response.status_code == 200
    assert max(Image.open(io.BytesIO(response.content)).size) <= 600
    too_big = client.get(f"/api/documents/{document_id}/pages/1.png", params={"max_side": 99999})
    assert too_big.status_code == 422


def test_only_plan_sheets_have_a_takeoff(client, done):
    _, document_id, body = done
    response = client.get(f"/api/takeoffs/{body['id']}/sheets/{document_id}/2")
    assert response.status_code == 404


def test_edits_are_kept_and_move_the_totals(client, done):
    project_id, document_id, body = done
    url = f"/api/takeoffs/{body['id']}/sheets/{document_id}/1"
    runs = client.get(url).json()["runs"]
    red = next(r for r in runs if r["system"] == "П1")

    response = client.put(f"{url}/overrides", json={"overrides": {str(red["id"]): "В1"}})
    assert response.status_code == 200, response.text
    assert response.json()["overrides"] == {str(red["id"]): "В1"}

    summary = client.get(f"/api/projects/{project_id}/takeoff").json()
    systems = {s["system"]: s for s in summary["systems"]}
    assert systems["П1"]["measured_m"] == pytest.approx(0.0, abs=0.01)
    assert systems["В1"]["measured_m"] == pytest.approx(18.0, abs=1.0)

    # an empty map undoes every edit on the sheet
    client.put(f"{url}/overrides", json={"overrides": {}})
    assert client.get(url).json()["overrides"] == {}


def test_excluded_runs_leave_the_totals(client, done):
    project_id, document_id, body = done
    url = f"/api/takeoffs/{body['id']}/sheets/{document_id}/1"
    runs = client.get(url).json()["runs"]
    client.put(f"{url}/overrides",
               json={"overrides": {str(r["id"]): "excluded" for r in runs}})
    summary = client.get(f"/api/projects/{project_id}/takeoff").json()
    assert summary["sheets"][0]["length_m"] == 0
    client.put(f"{url}/overrides", json={"overrides": {}})


@pytest.mark.parametrize("overrides", [
    {"0": "НЕТ-ТАКОЙ"},          # not a system of this project
    {"999": "В1"},               # not a run of this sheet
    {"0": "x" * 100},
])
def test_bad_edits_are_rejected(client, done, overrides):
    _, document_id, body = done
    url = f"/api/takeoffs/{body['id']}/sheets/{document_id}/1/overrides"
    assert client.put(url, json={"overrides": overrides}).status_code == 422


def test_export_is_a_workbook_with_the_edited_figures(client, done):
    _, document_id, body = done
    url = f"/api/takeoffs/{body['id']}/sheets/{document_id}/1"
    runs = client.get(url).json()["runs"]
    blue = next(r for r in runs if r["system"] == "В1")
    client.put(f"{url}/overrides", json={"overrides": {str(blue["id"]): "excluded"}})

    response = client.get(f"/api/takeoffs/{body['id']}/export.xlsx")
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    sheet = openpyxl.load_workbook(io.BytesIO(response.content)).active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0][:4] == ("Система", "Сечение", "Изоляция", "Длина, м")
    assert {r[0] for r in rows[1:-1]} == {"П1"}, "the excluded В1 run is gone"
    assert rows[-1][0] == "Итого"
    client.put(f"{url}/overrides", json={"overrides": {}})


def test_takeoff_needs_a_drawing(client):
    project_id = _new_project(client, "Empty")
    response = client.post(f"/api/projects/{project_id}/takeoff")
    assert response.status_code == 422


def test_no_takeoff_yet_is_a_404(client):
    project_id = _new_project(client, "Fresh")
    assert client.get(f"/api/projects/{project_id}/takeoff").status_code == 404


def test_summary_counts_fittings_against_the_specification(done):
    _, _, body = done
    fittings = {f["mark"]: f for f in body["fittings"]}
    assert fittings["АМР 400x200"] == {
        "mark": "АМР 400x200", "kind": "решётка", "counted": 2, "spec": 5}
    assert fittings["КЛАПЪ-(60)-НО-100x100"]["counted"] == 1
    assert fittings["КЛАПЪ-(60)-НО-100x100"]["spec"] == 1
    # on a plan but not in the specification's equipment rows
    assert fittings["АДР-К 650x300"]["spec"] is None


def test_sheet_payload_carries_fitting_positions(client, done):
    _, document_id, body = done
    sheet = client.get(f"/api/takeoffs/{body['id']}/sheets/{document_id}/1").json()
    assert len(sheet["fittings"]) == 4
    assert {"id", "mark", "kind", "x", "y"} <= set(sheet["fittings"][0])


def test_export_has_an_elements_sheet(client, done):
    _, _, body = done
    response = client.get(f"/api/takeoffs/{body['id']}/export.xlsx")
    book = openpyxl.load_workbook(io.BytesIO(response.content))
    assert book.sheetnames == ["Воздуховоды", "Элементы"]
    rows = list(book["Элементы"].iter_rows(values_only=True))
    assert rows[0] == ("Элемент", "Тип", "На планах, шт.", "По спецификации, шт.")
    by_mark = {r[0]: r for r in rows[1:]}
    assert by_mark["АМР 400x200"][2:] == (2, 5)
    assert by_mark["АДР-К 650x300"][3] is None


def test_scale_starts_unconfirmed_and_is_in_the_review_queue(client, done):
    project_id, document_id, body = done
    summary = client.get(f"/api/projects/{project_id}/takeoff").json()
    assert summary["sheets"][0]["scale_confirmed"] is False
    scale_items = [i for i in summary["review"] if i["kind"] == "scale"]
    assert [(i["document_id"], i["page"], i["scale"]) for i in scale_items] == [
        (document_id, 1, 100)]


def test_confirming_the_detected_scale_keeps_the_figures(client, done):
    project_id, document_id, body = done
    url = f"/api/takeoffs/{body['id']}/sheets/{document_id}/1"
    before = client.get(url).json()
    response = client.put(f"{url}/scale", json={"scale": 100})
    assert response.status_code == 200, response.text
    sheet = response.json()
    assert sheet["scale"] == 100 and sheet["scale_confirmed"] is True
    assert sheet["detected_scale"] == 100
    assert [r["length_m"] for r in sheet["runs"]] == [r["length_m"] for r in before["runs"]]
    summary = client.get(f"/api/projects/{project_id}/takeoff").json()
    assert "scale" not in {i["kind"] for i in summary["review"]}


def test_correcting_the_scale_measures_the_sheet_again(client, done):
    project_id, document_id, body = done
    url = f"/api/takeoffs/{body['id']}/sheets/{document_id}/1"
    runs = client.get(url).json()["runs"]
    client.put(f"{url}/overrides", json={"overrides": {str(runs[0]["id"]): "excluded"}})

    response = client.put(f"{url}/scale", json={"scale": 200})
    assert response.status_code == 200, response.text
    sheet = response.json()
    assert sheet["scale"] == 200 and sheet["scale_confirmed"] is True
    assert sheet["detected_scale"] == 100, "what the measurer read is kept for reference"
    assert sum(r["length_m"] for r in sheet["runs"]) == pytest.approx(36.0, abs=2.0)
    assert sheet["overrides"] == {}, "edits named runs of the old measurement"
    summary = client.get(f"/api/projects/{project_id}/takeoff").json()
    assert summary["sheets"][0]["length_m"] == pytest.approx(36.0, abs=2.0)

    back = client.put(f"{url}/scale", json={"scale": 100}).json()
    assert sum(r["length_m"] for r in back["runs"]) == pytest.approx(18.0, abs=1.0)
    assert back["detected_scale"] == 100


@pytest.mark.parametrize("scale", [0, 5, 5000])
def test_implausible_scales_are_rejected(client, done, scale):
    _, document_id, body = done
    url = f"/api/takeoffs/{body['id']}/sheets/{document_id}/1/scale"
    assert client.put(url, json={"scale": scale}).status_code == 422


def test_only_plan_sheets_take_a_scale(client, done):
    _, document_id, body = done
    url = f"/api/takeoffs/{body['id']}/sheets/{document_id}/2/scale"
    assert client.put(url, json={"scale": 100}).status_code == 404


def test_review_items_can_be_marked_reviewed(client, done):
    project_id, _, body = done
    summary = client.get(f"/api/projects/{project_id}/takeoff").json()
    item = next(i for i in summary["review"] if i["can_dismiss"])
    url = f"/api/takeoffs/{body['id']}/review"

    response = client.put(url, json={"key": item["key"], "reviewed": True})
    assert response.status_code == 200, response.text
    marked = next(i for i in response.json()["review"] if i["key"] == item["key"])
    assert marked["is_reviewed"] is True

    client.put(url, json={"key": item["key"], "reviewed": False})
    summary = client.get(f"/api/projects/{project_id}/takeoff").json()
    assert next(i for i in summary["review"] if i["key"] == item["key"])["is_reviewed"] is False


def test_only_dismissable_items_can_be_marked_reviewed(client, done):
    project_id, document_id, body = done
    url = f"/api/takeoffs/{body['id']}/review"
    assert client.put(url, json={"key": "no-such-item", "reviewed": True}).status_code == 422
    # a scale is settled by confirming it, not by waving it through
    client.put(f"/api/takeoffs/{body['id']}/sheets/{document_id}/1/scale", json={"scale": 200})
    client.put(f"/api/takeoffs/{body['id']}/sheets/{document_id}/1/scale", json={"scale": 100})
    summary = client.get(f"/api/projects/{project_id}/takeoff").json()
    assert "scale" not in {i["kind"] for i in summary["review"]}
