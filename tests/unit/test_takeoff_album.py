"""Whole-album takeoff: classify sheets, read the spec, measure the plans."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dc_extraction.takeoff import run_album  # noqa: E402
from helpers.pdfgen import DuctSegment, SpecDuct, make_album_pdf  # noqa: E402

RED = (1.0, 0.0, 0.0)  # supply (П) family
BLUE = (0.0, 0.0, 1.0)  # extract (В) family


@pytest.fixture
def album(tmp_path):
    path = tmp_path / "album.pdf"
    make_album_pdf(
        path,
        [DuctSegment((0, 0), (10, 0), 600, RED), DuctSegment((0, 6), (8, 6), 500, BLUE)],
        callouts=[((140, 600), ["П1", "600x350"], (3.0, 0.0))],
        spec=[SpecDuct("П1", "600x350", 12.5), SpecDuct("В1", "500x300", 9.0)],
    )
    return pymupdf.open(path)


def test_only_plan_sheets_are_measured(album):
    result = run_album(album)
    kinds = [(s.page, s.kind) for s in result.sheets]
    assert kinds == [(1, "plan"), (2, "schematic"), (3, "specification")]
    plan, schematic, _ = result.sheets
    assert sum(r.length_m for r in plan.runs) == pytest.approx(18.0, abs=1.0)
    assert schematic.runs == [], "the schematic draws the same ducts but is not a plan"


def test_runs_are_attributed_against_the_album_specification(album):
    result = run_album(album)
    assert set(result.spec) == {"П1", "В1"}
    systems = {r.system for r in result.sheets[0].runs}
    assert "П1" in systems, "the callout pins the red duct"
    assert "В1" in systems, "the blue duct fits В1 by section and budget"


def test_a_separate_specification_replaces_the_albums_own(album):
    from dc_extraction.takeoff import SpecSystem

    result = run_album(album, spec={"П1": SpecSystem("П1", 30.0, {"600x350": 30.0})})
    assert set(result.spec) == {"П1"}


def test_progress_reports_each_measured_plan(album):
    steps = []
    run_album(album, on_progress=lambda step, done, total: steps.append((step, done, total)))
    assert ("classify", 3, 3) in steps
    assert ("measure", 1, 1) in steps


def test_result_is_plain_json(album):
    payload = run_album(album).to_json()
    text = json.dumps(payload, ensure_ascii=False)
    plan = json.loads(text)["sheets"][0]
    assert plan["scale"] == 100
    assert {"id", "system", "section", "width_mm", "insulated", "length_m", "p0", "p1"} \
        <= set(plan["runs"][0])
    assert json.loads(text)["spec"]["П1"]["length_m"] == 12.5
