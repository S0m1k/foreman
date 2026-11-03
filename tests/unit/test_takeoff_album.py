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


# --- fittings: grilles and dampers counted off the plans ---------------------

from dc_extraction.takeoff import fittings as read_fittings  # noqa: E402
from helpers.pdfgen import SpecFitting  # noqa: E402

LABELS = [((300, 400), "АМР 400х200"), ((300, 430), "АМР 400x200"), ((300, 460), "АДР-К 650x300"),
          ((600, 400), "КЛАПЪ-(60)-НО-100x100"), ((600, 430), "АМР")]


@pytest.fixture
def album_with_fittings(tmp_path):
    path = tmp_path / "album.pdf"
    make_album_pdf(
        path,
        [DuctSegment((0, 0), (10, 0), 600, RED)],
        callouts=[((140, 600), ["П1", "600x350"], (3.0, 0.0))],
        spec=[SpecDuct("П1", "600x350", 12.5)],
        labels=LABELS,
        fittings=[SpecFitting("П1", "Решетка АМР 400х200", 5),
                  SpecFitting("П1", "Клапан КЛАПЪ-(60)-НО-100x100", 1)],
    )
    return pymupdf.open(path)


def test_grille_and_damper_marks_are_read_off_the_plan(album_with_fittings):
    marks = sorted(f.mark for f in read_fittings(album_with_fittings[0]))
    # Cyrillic and Latin "x" are one size; a label without a size is no fitting
    assert marks == ["АДР-К 650x300", "АМР 400x200", "АМР 400x200", "КЛАПЪ-(60)-НО-100x100"]
    kinds = {f.mark: f.kind for f in read_fittings(album_with_fittings[0])}
    assert kinds["КЛАПЪ-(60)-НО-100x100"] == "клапан"
    assert kinds["АМР 400x200"] == "решётка"


def test_album_counts_fittings_on_plans_only(album_with_fittings):
    result = run_album(album_with_fittings)
    plan, schematic, _ = result.sheets
    assert len(plan.fittings) == 4
    assert schematic.fittings == [], "schematics are not counted"
    payload = result.to_json()
    assert {"id", "mark", "kind", "x", "y"} <= set(payload["sheets"][0]["fittings"][0])
    # the specification's equipment, keyed the same way the plan's marks are
    assert payload["spec_fittings"] == {"АМР 400x200": 5, "КЛАПЪ-(60)-НО-100x100": 1}


def test_damper_mark_drops_the_actuator_suffix(tmp_path):
    """On the plan a damper is written with its actuator - КЛАПЪ-(60)-НО-100x100-BМ220
    - while the specification row names the damper alone; they must match."""
    path = tmp_path / "album.pdf"
    make_album_pdf(path, [DuctSegment((0, 0), (10, 0), 600, RED)],
                   labels=[((300, 400), "КЛАПЪ-(60)-НО-100x100-BМ220"),
                           ((300, 430), "КЛАПЪ-(60)-НЗ-750x400-ВМ220")])
    marks = sorted(f.mark for f in read_fittings(pymupdf.open(path)[0]))
    assert marks == ["КЛАПЪ-(60)-НЗ-750x400", "КЛАПЪ-(60)-НО-100x100"]


def test_specification_counts_the_k_series_grille(tmp_path):
    """"АДР-К 650х300" is one mark; the spec reader's pattern stopped at "АДР-"
    and dropped 36 such grilles on the benchmark album."""
    path = tmp_path / "album.pdf"
    make_album_pdf(path, [DuctSegment((0, 0), (10, 0), 600, RED)],
                   spec=[SpecDuct("П1", "600x350", 12.5)],
                   fittings=[SpecFitting("П1", "Вентиляционная решетка АДР-К 650х300", 14),
                             SpecFitting("П2", "Вентиляционная решетка АДР-К 650х300", 11)])
    assert run_album(pymupdf.open(path)).spec_fittings == {"АДР-К 650x300": 25}
