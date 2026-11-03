"""Take off a whole HVAC album: classify sheets, read the spec, measure plans.

This is the unit the product works in - an estimator uploads the project's
OV album, not a page number - and the shape the web screens render.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pymupdf

from .fittings import Fitting, fittings, spec_fitting_counts
from .pipeline import TakeoffRow, takeoff
from .sheets import SheetKind, classify_sheet
from .spec import SpecSystem, parse_specification

# on_progress(step, done, total) with step in "classify" | "spec" | "measure"
Progress = Callable[[str, int, int], None]


@dataclass(frozen=True)
class AlbumRun:
    id: int
    system: str | None
    confidence: str
    section: str | None
    width_mm: int | None
    insulated: bool
    length_m: float
    p0: tuple[float, float]
    p1: tuple[float, float]


@dataclass(frozen=True)
class AlbumFitting:
    id: int
    mark: str
    kind: str
    x: float
    y: float


@dataclass
class AlbumSheet:
    page: int
    kind: SheetKind
    title: str | None
    width: float
    height: float
    scale: int | None = None
    runs: list[AlbumRun] = field(default_factory=list)
    fittings: list[AlbumFitting] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "page": self.page,
            "kind": self.kind,
            "title": self.title,
            "width": round(self.width, 2),
            "height": round(self.height, 2),
            "scale": self.scale,
            "runs": [_run_json(r) for r in self.runs],
            "fittings": [_fitting_json(f) for f in self.fittings],
        }


@dataclass
class AlbumTakeoff:
    sheets: list[AlbumSheet]
    spec: dict[str, SpecSystem]
    spec_fittings: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "sheets": [s.to_json() for s in self.sheets],
            "spec_fittings": self.spec_fittings,
            "spec": {
                name: {"length_m": round(entry.length_m, 2),
                       "sections": {k: round(v, 2) for k, v in entry.sections.items()}}
                for name, entry in self.spec.items()
            },
        }


def _fitting_json(item: AlbumFitting) -> dict:
    return {"id": item.id, "mark": item.mark, "kind": item.kind,
            "x": round(item.x, 1), "y": round(item.y, 1)}


def _run_json(run: AlbumRun) -> dict:
    return {
        "id": run.id,
        "system": run.system,
        "confidence": run.confidence,
        "section": run.section,
        "width_mm": run.width_mm,
        "insulated": run.insulated,
        "length_m": round(run.length_m, 2),
        "p0": [round(v, 1) for v in run.p0],
        "p1": [round(v, 1) for v in run.p1],
    }


def run_album(doc: pymupdf.Document, spec: dict[str, SpecSystem] | None = None,
              on_progress: Progress | None = None) -> AlbumTakeoff:
    """Measure every plan sheet of `doc` against `spec` (default: the album's own)."""
    report = on_progress or (lambda step, done, total: None)

    sheets: list[AlbumSheet] = []
    for index, page in enumerate(doc, start=1):
        kind = classify_sheet(page)
        sheets.append(AlbumSheet(page=index, kind=kind.kind, title=kind.title,
                                 width=page.rect.width, height=page.rect.height))
        report("classify", index, len(doc))

    if spec is None:
        report("spec", 0, 1)
        spec = parse_specification(doc)
        report("spec", 1, 1)

    plans = [s for s in sheets if s.kind == "plan"]
    measured = 0

    def on_sheet(_page: int) -> None:
        nonlocal measured
        measured += 1
        report("measure", measured, len(plans))

    _measure_plans(doc, plans, spec, on_sheet=on_sheet)
    return AlbumTakeoff(sheets=sheets, spec=spec, spec_fittings=spec_fitting_counts(spec))


def remeasure_plan(doc: pymupdf.Document, page: int, spec: dict[str, SpecSystem],
                   scale: int) -> AlbumSheet:
    """Measure one plan sheet again at the scale the estimator gave.

    Systems are attributed from this sheet's own evidence: the album run also
    pools votes across sheets, so a run's system can differ from the first
    measurement where only another sheet named it.
    """
    pdf_page = doc[page - 1]
    kind = classify_sheet(pdf_page)
    sheet = AlbumSheet(page=page, kind="plan", title=kind.title,
                       width=pdf_page.rect.width, height=pdf_page.rect.height)
    _measure_plans(doc, [sheet], spec, scale=scale)
    return sheet


def _measure_plans(doc: pymupdf.Document, plans: list[AlbumSheet], spec: dict[str, SpecSystem],
                   scale: int | None = None,
                   on_sheet: Callable[[int], None] | None = None) -> None:
    """Fill each plan's scale, runs and fittings; `scale=None` reads it off each sheet."""
    if not plans:
        return
    rows, _, results = takeoff(doc, [s.page for s in plans], scope=sorted(spec), spec=spec,
                               scale=scale, on_sheet=on_sheet)
    by_page = {s.page: s for s in plans}
    for result in results:
        by_page[result.page].scale = result.scale
    _attach_runs(rows, results, by_page)
    for sheet in plans:
        found: list[Fitting] = fittings(doc[sheet.page - 1])
        sheet.fittings.extend(
            AlbumFitting(i, f.mark, f.kind, f.x, f.y) for i, f in enumerate(found))


def _attach_runs(rows: list[TakeoffRow], results, by_page: dict[int, AlbumSheet]) -> None:
    """takeoff() emits rows sheet by sheet, run by run - pair them back up."""
    position = 0
    for result in results:
        sheet = by_page[result.page]
        for index, run in enumerate(result.runs):
            row = rows[position]
            position += 1
            sheet.runs.append(AlbumRun(
                id=index, system=row.system, confidence=row.confidence, section=row.section,
                width_mm=row.width_mm, insulated=row.insulated, length_m=row.length_m,
                p0=run.p0, p1=run.p1,
            ))
