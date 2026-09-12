"""End-to-end duct takeoff: plan sheets in, takeoff rows out."""

from __future__ import annotations

import collections
from dataclasses import dataclass, field

import pymupdf

from .assign import Component, assign_systems, build_components, seed_votes
from .callouts import (
    COLOUR_FAMILY,
    FAMILY_RE,
    equipment_marks,
    leaders,
    nearest_run,
    size_dimensions,
)
from .geometry import DuctRun, centrelines, detect_scale, snap_width
from .network import connect, merge_trunks
from .spec import SpecSystem, parse_specification, unique_equipment

# family letter -> the duct colours drawn for it (COLOUR_FAMILY inverted)
_FAMILY_COLOURS: dict[str, set[str]] = collections.defaultdict(set)
for _colour, _family in COLOUR_FAMILY.items():
    _FAMILY_COLOURS[_family].add(_colour)


def _colours_for(system_name: str) -> set[str] | None:
    """The duct colours a system's own family is drawn in, if known."""
    match = FAMILY_RE.match(system_name)
    return _FAMILY_COLOURS.get(match.group(1)) if match else None


@dataclass
class TakeoffRow:
    system: str | None
    confidence: str
    section: str | None
    width_mm: int | None
    insulated: bool
    length_m: float
    page: int


@dataclass
class SheetTakeoff:
    page: int
    scale: int
    runs: list[DuctRun]
    components: dict[tuple, Component]
    run_to_component: list[tuple | None]
    sections: dict[int, str]
    votes: dict[tuple, collections.Counter] = field(default_factory=dict)


def measure_sheet(doc: pymupdf.Document, page_number: int, scale: int | None = None,
                  equipment_owner: dict[str, str] | None = None,
                  palette: dict[tuple, str] | None = None) -> SheetTakeoff:
    """Measure one plan sheet and collect its attribution seeds.

    `palette` overrides the default four AutoCAD colours - different sheets in
    the same document can draw the same system family in a different exact
    RGB (e.g. a pastel blue for apartment risers once the plain blue is taken
    by water pipes on that sheet).
    """
    page = doc[page_number - 1]
    if scale is None:
        scale = detect_scale(page)
    runs = centrelines(page, scale=scale, palette=palette)
    trunks, run_to_trunk = merge_trunks(runs)
    component_of = connect(trunks, scale=scale)
    components = build_components(page_number, trunks, component_of)

    leader_hits: list[tuple[int, str]] = []
    sections: dict[int, str] = {}
    for kind, text, px, py in leaders(page):
        if kind == "system":
            # Restrict to the system's own family colour(s) first: once a
            # leader's endpoint lands inside *any* band the distance score
            # clamps to zero, and a wide duct passing nearby can then out-tie
            # the slim one the callout actually names.
            index, _ = nearest_run(runs, px, py, scale=scale, colours=_colours_for(text))
            if index is not None:
                leader_hits.append((index, text))
        else:
            index, _ = nearest_run(runs, px, py, scale=scale)
            if index is not None:
                sections[index] = text

    equipment_hits: list[tuple[int, str]] = []
    for mark, word in equipment_marks(page):
        owner = (equipment_owner or {}).get(mark)
        if not owner:
            continue
        index, _ = nearest_run(runs, (word[0] + word[2]) / 2, word[3] + 2, scale=scale,
                               colours=_colours_for(owner))
        if index is not None:
            equipment_hits.append((index, owner))

    votes = seed_votes(runs, run_to_trunk, component_of, page_number,
                       leader_hits, equipment_hits)
    run_to_component: list[tuple | None] = [
        (page_number, component_of[t]) if t is not None else None for t in run_to_trunk
    ]
    return SheetTakeoff(page=page_number, scale=scale, runs=runs, components=components,
                        run_to_component=run_to_component, sections=sections, votes=votes)


def takeoff(doc: pymupdf.Document, pages: list[int], scope: list[str],
            scale: int | None = None,
            palette: dict[tuple, str] | None = None) -> tuple[list[TakeoffRow],
                                                               dict[str, SpecSystem],
                                                               list[SheetTakeoff]]:
    """Measure `pages`, attribute to the systems in `scope`, return takeoff rows."""
    spec = parse_specification(doc)
    owner = unique_equipment(spec, set(scope))

    sheets = [measure_sheet(doc, page, scale=scale, equipment_owner=owner, palette=palette)
              for page in pages]
    components: dict[tuple, Component] = {}
    votes: dict[tuple, collections.Counter] = collections.defaultdict(collections.Counter)
    for sheet in sheets:
        components.update(sheet.components)
        for key, counter in sheet.votes.items():
            votes[key].update(counter)
    assign_systems(components, votes, spec, scope)

    rows: list[TakeoffRow] = []
    for sheet in sheets:
        for index, run in enumerate(sheet.runs):
            key = sheet.run_to_component[index]
            comp = components.get(key) if key else None
            section = sheet.sections.get(index)
            width = snap_width(run.width_mm)
            if section:
                dims = size_dimensions(section)
                if width is not None and min(abs(width - d) for d in dims) > 30:
                    section = None  # the callout does not match what is drawn
            rows.append(TakeoffRow(
                system=comp.system if comp else None,
                confidence=comp.confidence if comp else "none",
                section=section,
                width_mm=width,
                insulated=run.insulated,
                length_m=run.length_m,
                page=sheet.page,
            ))
    return rows, spec, sheets


def summarise(rows: list[TakeoffRow]) -> dict[tuple, float]:
    """Group into the shape an estimator works with: system, section, insulation."""
    out: collections.Counter = collections.Counter()
    for row in rows:
        section = row.section or (f"{row.width_mm}x?" if row.width_mm else "?")
        out[(row.system or "не определено", section, row.insulated)] += row.length_m
    return dict(out)


def totals_by_system(rows: list[TakeoffRow]) -> dict[str, float]:
    out: collections.Counter = collections.Counter()
    for row in rows:
        out[row.system or "не определено"] += row.length_m
    return dict(out)
