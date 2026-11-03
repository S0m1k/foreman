"""The review queue: what an estimator still has to look at before trusting a takeoff."""

from __future__ import annotations

import pytest
from dc_api.takeoff_review import (
    REVIEWED_KEY,
    SCALES_KEY,
    confirm_scale,
    is_scale_confirmed,
    review_items,
    set_reviewed,
)


def _run(run_id, system, length, section="600x350", width=600):
    return {"id": run_id, "system": system, "confidence": "high", "section": section,
            "width_mm": width, "insulated": False, "length_m": length,
            "p0": [0, 0], "p1": [1, 0]}


def _result(*sheets, spec=None, spec_fittings=None):
    return {"spec": spec or {}, "spec_fittings": spec_fittings or {},
            "documents": {"doc": {"filename": "ОВ.pdf", "sheets": list(sheets)}}}


def _plan(page, runs, scale=100, fittings=()):
    return {"page": page, "kind": "plan", "title": f"План {page}", "width": 100,
            "height": 100, "scale": scale, "runs": runs, "fittings": list(fittings)}


def _kinds(items):
    return [(i["kind"], i["page"]) for i in items]


def test_every_measured_plan_asks_for_its_scale_to_be_confirmed():
    result = _result(_plan(1, [_run(0, "П1", 5.0)]), _plan(2, [_run(0, "П1", 3.0)], scale=50))
    items = review_items(result, {})
    scale = [i for i in items if i["kind"] == "scale"]
    assert [(i["page"], i["scale"]) for i in scale] == [(1, 100), (2, 50)]
    assert all(not i["can_dismiss"] for i in scale), "a scale is confirmed, not waved through"


def test_a_confirmed_scale_leaves_the_queue():
    result = _result(_plan(1, [_run(0, "П1", 5.0)]))
    overrides = confirm_scale({}, "doc", 1, 100)
    assert is_scale_confirmed(overrides, "doc", _plan(1, [], scale=100))
    assert [i for i in review_items(result, overrides) if i["kind"] == "scale"] == []


def test_a_confirmation_at_another_scale_no_longer_holds():
    """Confirmed 1:100, then the sheet was re-measured at 1:200 - ask again."""
    overrides = confirm_scale({}, "doc", 1, 100)
    assert not is_scale_confirmed(overrides, "doc", _plan(1, [], scale=200))


def test_unassigned_length_is_queued_per_sheet_and_cannot_be_waved_through():
    result = _result(_plan(1, [_run(0, None, 4.0), _run(1, None, 1.5), _run(2, "П1", 9.0)]))
    item = next(i for i in review_items(result, {}) if i["kind"] == "unassigned")
    assert item["page"] == 1 and item["length_m"] == pytest.approx(5.5)
    assert item["count"] == 2
    assert not item["can_dismiss"]


def test_assigning_or_excluding_the_runs_clears_the_unassigned_item():
    result = _result(_plan(1, [_run(0, None, 4.0), _run(1, None, 1.5)]))
    overrides = {"doc:1": {"0": "П1", "1": "excluded"}}
    assert [i for i in review_items(result, overrides) if i["kind"] == "unassigned"] == []


def test_runs_whose_section_was_not_read_are_queued():
    result = _result(_plan(1, [_run(0, "П1", 2.0, section=None, width=1100),
                               _run(1, "П1", 1.0, section=None, width=None),
                               _run(2, "П1", 7.0)]))
    item = next(i for i in review_items(result, {}) if i["kind"] == "section")
    assert item["length_m"] == pytest.approx(3.0) and item["count"] == 2
    assert item["can_dismiss"]


def test_excluded_runs_are_not_queued_for_their_section():
    result = _result(_plan(1, [_run(0, "П1", 2.0, section=None)]))
    items = review_items(result, {"doc:1": {"0": "excluded"}})
    assert "section" not in {i["kind"] for i in items}


def test_a_plan_with_no_ducts_found_is_queued():
    result = _result(_plan(1, [], scale=None))
    items = review_items(result, {})
    assert _kinds(items) == [("no_runs", 1)], "no scale to confirm when nothing was measured"


def test_systems_over_the_specification_are_queued():
    result = _result(_plan(1, [_run(0, "П1", 20.0), _run(1, "В1", 10.0)]),
                     spec={"П1": {"length_m": 12.0, "sections": {}},
                           "В1": {"length_m": 10.1, "sections": {}}})
    over = [i for i in review_items(result, {}) if i["kind"] == "over_spec"]
    assert [(i["system"], i["page"]) for i in over] == [("П1", None)], "В1 is within 3%"
    assert over[0]["length_m"] == pytest.approx(8.0)


def test_fittings_beyond_or_missing_from_the_specification_are_queued():
    fittings = [{"id": i, "mark": m, "kind": "решётка", "x": 0, "y": 0}
                for i, m in enumerate(["АМР 400x200"] * 3 + ["АДР 200x200"] * 2 + ["АМР 100x100"])]
    result = _result(_plan(1, [_run(0, "П1", 1.0)], fittings=fittings),
                     spec_fittings={"АМР 400x200": 2, "АДР 200x200": 4, "АМР 100x100": 1})
    marks = {i["mark"]: i["count"] for i in review_items(result, {}) if i["kind"] == "fitting"}
    assert marks == {"АМР 400x200": 1}, "fewer than specified is the unmeasured rest"

    result["spec_fittings"].pop("АДР 200x200")
    marks = {i["mark"] for i in review_items(result, {}) if i["kind"] == "fitting"}
    assert marks == {"АМР 400x200", "АДР 200x200"}


def test_marking_an_item_reviewed_keeps_it_listed_but_done():
    result = _result(_plan(1, [_run(0, "П1", 2.0, section=None)]))
    key = next(i["key"] for i in review_items(result, {}) if i["kind"] == "section")
    overrides = set_reviewed({}, key, True)
    assert overrides[REVIEWED_KEY] == [key]
    item = next(i for i in review_items(result, overrides) if i["key"] == key)
    assert item["is_reviewed"]
    assert set_reviewed(overrides, key, False)[REVIEWED_KEY] == []


def test_decisions_do_not_touch_the_sheet_edits():
    overrides = {"doc:1": {"0": "П1"}}
    after = set_reviewed(confirm_scale(overrides, "doc", 1, 100), "section:doc:1", True)
    assert after["doc:1"] == {"0": "П1"}
    assert after[SCALES_KEY] == {"doc:1": 100}
    assert overrides == {"doc:1": {"0": "П1"}}, "the stored dict is not mutated"


def test_queue_order_is_sheet_by_sheet_then_project_wide():
    result = _result(_plan(2, [_run(0, None, 1.0)]), _plan(1, [_run(0, "П1", 30.0)]),
                     spec={"П1": {"length_m": 10.0, "sections": {}}})
    assert _kinds(review_items(result, {})) == [
        ("scale", 1), ("scale", 2), ("unassigned", 2), ("over_spec", None)]
