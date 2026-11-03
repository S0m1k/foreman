"""The review queue: what an estimator has to look at before trusting a takeoff.

The queue is derived, never stored: each item is a condition read off the
measured album and the estimator's edits, and it leaves the queue when the
condition is gone (the scale confirmed, the runs assigned). Items the measurer
cannot settle on its own - a section it could not read, a system over the
specification - can also be marked reviewed; those stay listed, as done.

The estimator's decisions live beside the per-sheet run edits in the same
overrides JSON, under keys no "document_id:page" can take:

    overrides = {"document_id:page": {run id: system},
                 "_scales": {"document_id:page": confirmed scale},
                 "_reviewed": [item key, ...]}
"""

from __future__ import annotations

import collections

from . import takeoff_view as view

SCALES_KEY = "_scales"
REVIEWED_KEY = "_reviewed"
# the web's reconciliation verdict calls a system within 3% of its specification a match
SPEC_TOLERANCE = 0.03
DISMISSABLE = frozenset({"section", "no_runs", "over_spec", "fitting"})


def is_scale_confirmed(overrides: dict, document_id: str, sheet: dict) -> bool:
    confirmed = overrides.get(SCALES_KEY, {}).get(view.sheet_key(document_id, sheet["page"]))
    return confirmed is not None and confirmed == sheet["scale"]


def confirm_scale(overrides: dict, document_id: str, page: int, scale: int) -> dict:
    scales = {**overrides.get(SCALES_KEY, {}), view.sheet_key(document_id, page): scale}
    return {**overrides, SCALES_KEY: scales}


def set_reviewed(overrides: dict, key: str, reviewed: bool) -> dict:
    keys = [k for k in overrides.get(REVIEWED_KEY, []) if k != key]
    return {**overrides, REVIEWED_KEY: keys + [key] if reviewed else keys}


def _item(kind: str, key: str, **fields) -> dict:
    base = {"key": key, "kind": kind, "document_id": None, "page": None, "sheet_title": None,
            "system": None, "mark": None, "scale": None, "length_m": None, "count": None,
            "can_dismiss": kind in DISMISSABLE}
    return {**base, **fields}


def _sheet_items(document_id: str, sheet: dict, overrides: dict) -> list[dict]:
    page = sheet["page"]
    where = {"document_id": document_id, "page": page, "sheet_title": sheet["title"]}
    tail = f"{document_id}:{page}"
    if not sheet["runs"]:
        return [_item("no_runs", f"no_runs:{tail}", **where)]

    items = []
    if not is_scale_confirmed(overrides, document_id, sheet):
        items.append(_item("scale", f"scale:{tail}", scale=sheet["scale"], **where))
    own = overrides.get(view.sheet_key(document_id, page), {})
    counted = [r for r in sheet["runs"] if view.effective_system(r, own) != view.EXCLUDED]
    unassigned = [r for r in counted if view.effective_system(r, own) == view.UNKNOWN]
    if unassigned:
        items.append(_item("unassigned", f"unassigned:{tail}", count=len(unassigned),
                           length_m=round(sum(r["length_m"] for r in unassigned), 2), **where))
    unread = [r for r in counted if not r["section"]]
    if unread:
        items.append(_item("section", f"section:{tail}", count=len(unread),
                           length_m=round(sum(r["length_m"] for r in unread), 2), **where))
    return items


def _over_spec_items(result: dict, overrides: dict) -> list[dict]:
    measured = view.measured_by_system(result, overrides)
    items = []
    for system, spec_m in sorted(view.spec_lengths(result).items()):
        excess = measured.get(system, 0.0) - spec_m
        if spec_m > 0 and excess > spec_m * SPEC_TOLERANCE:
            items.append(_item("over_spec", f"over_spec:{system}", system=system,
                               length_m=round(excess, 2)))
    return items


def _fitting_items(result: dict) -> list[dict]:
    """Marks counted beyond the specification, or absent from it.

    Fewer than specified is not queued: the specification covers the whole
    building, the rest sits on sheets not measured.
    """
    items = []
    for fitting in view.fittings_summary(result):
        spec, counted = fitting["spec"], fitting["counted"]
        if counted and (spec is None or counted > spec):
            items.append(_item("fitting", f"fitting:{fitting['mark']}", mark=fitting["mark"],
                               count=counted - (spec or 0)))
    return items


def review_items(result: dict, overrides: dict) -> list[dict]:
    """Sheet by sheet in album order, then the project-wide reconciliation."""
    by_document: dict[str, list[dict]] = collections.defaultdict(list)
    for document_id, sheet in view.plan_sheets(result):
        by_document[document_id].append(sheet)
    items = [item
             for document_id, sheets in by_document.items()
             for sheet in sorted(sheets, key=lambda s: s["page"])
             for item in _sheet_items(document_id, sheet, overrides)]
    items += _over_spec_items(result, overrides) + _fitting_items(result)
    reviewed = set(overrides.get(REVIEWED_KEY, []))
    return [{**i, "is_reviewed": i["can_dismiss"] and i["key"] in reviewed} for i in items]
