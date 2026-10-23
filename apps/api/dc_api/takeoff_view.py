"""Read a stored takeoff through the estimator's edits.

Pure functions over the JSON a takeoff run stores, so the routes stay thin and
every figure the screens and the export show is computed one way:

    result    = {"spec": {system: {"length_m", "sections"}},
                 "documents": {document_id: {"filename", "sheets": [album sheet]}}}
    overrides = {"document_id:page": {"run id": system | "excluded"}}
"""

from __future__ import annotations

import collections
from collections.abc import Iterator

EXCLUDED = "excluded"
UNKNOWN = "не определено"
MAX_SYSTEM_LENGTH = 32


def sheet_key(document_id: str, page: int) -> str:
    return f"{document_id}:{page}"


def plan_sheets(result: dict) -> Iterator[tuple[str, dict]]:
    for document_id, document in result.get("documents", {}).items():
        for sheet in document["sheets"]:
            if sheet["kind"] == "plan":
                yield document_id, sheet


def find_plan_sheet(result: dict, document_id: str, page: int) -> dict | None:
    return next((s for d, s in plan_sheets(result) if d == document_id and s["page"] == page),
                None)


def effective_system(run: dict, sheet_overrides: dict[str, str]) -> str:
    return sheet_overrides.get(str(run["id"]), run["system"]) or UNKNOWN


def section_label(run: dict) -> str:
    if run["section"]:
        return run["section"]
    return f"{run['width_mm']}x?" if run["width_mm"] else "?"


def _counted_runs(result: dict, overrides: dict, skip: str | None = None
                  ) -> Iterator[tuple[str, dict, dict]]:
    """(system, run, sheet) for every run that counts towards the totals."""
    for document_id, sheet in plan_sheets(result):
        key = sheet_key(document_id, sheet["page"])
        if key == skip:
            continue
        own = overrides.get(key, {})
        for run in sheet["runs"]:
            system = effective_system(run, own)
            if system != EXCLUDED:
                yield system, run, sheet


def measured_by_system(result: dict, overrides: dict, skip: str | None = None
                       ) -> dict[str, float]:
    totals: collections.Counter = collections.Counter()
    for system, run, _ in _counted_runs(result, overrides, skip):
        totals[system] += run["length_m"]
    return {name: round(length, 2) for name, length in totals.items()}


def sheet_length(document_id: str, sheet: dict, overrides: dict) -> float:
    own = overrides.get(sheet_key(document_id, sheet["page"]), {})
    return round(sum(r["length_m"] for r in sheet["runs"]
                     if effective_system(r, own) != EXCLUDED), 2)


def spec_lengths(result: dict) -> dict[str, float]:
    return {name: entry["length_m"] for name, entry in result.get("spec", {}).items()}


def known_systems(result: dict) -> set[str]:
    """Systems a run may be assigned to: the specification's and the measured ones."""
    auto = {r["system"] for _, s in plan_sheets(result) for r in s["runs"] if r["system"]}
    return set(result.get("spec", {})) | auto


def systems_summary(result: dict, overrides: dict) -> list[dict]:
    """Measured vs specified length for every system the plans touch."""
    measured = measured_by_system(result, overrides)
    spec = spec_lengths(result)
    auto = {r["system"] or UNKNOWN for _, s in plan_sheets(result) for r in s["runs"]}
    names = (set(measured) | auto) - {EXCLUDED}
    return [
        {"system": name, "measured_m": measured.get(name, 0.0), "spec_m": spec.get(name)}
        for name in sorted(names, key=lambda n: (n == UNKNOWN, n))
    ]


def validate_overrides(sheet: dict, overrides: dict[str, str], allowed: set[str]
                       ) -> dict[str, str]:
    """Return the edits as stored, or raise ValueError naming the bad one."""
    run_ids = {str(r["id"]) for r in sheet["runs"]}
    clean: dict[str, str] = {}
    for run_id, system in overrides.items():
        if run_id not in run_ids:
            raise ValueError(f"no run {run_id!r} on this sheet")
        if len(system) > MAX_SYSTEM_LENGTH:
            raise ValueError("system name is too long")
        if system != EXCLUDED and system not in allowed:
            raise ValueError(f"unknown system {system!r}")
        clean[run_id] = system
    return clean


def export_rows(result: dict, overrides: dict) -> list[list]:
    """System, section, insulation, length - the estimator's table, edits applied."""
    grouped: collections.Counter = collections.Counter()
    for system, run, _ in _counted_runs(result, overrides):
        grouped[(system, section_label(run), run["insulated"])] += run["length_m"]
    ordered = sorted(grouped.items(), key=lambda kv: (kv[0][0] == UNKNOWN, kv[0]))
    return [[system, section, insulated, round(length, 2)]
            for (system, section, insulated), length in ordered]
