"""Give every duct component a system number, without CAD layers.

Signals, strongest first:

1. colour -> system family. Checked against every resolved system callout on
   sheets 6-7 of the reference project: 66 of 67 agree (red П, blue В, green
   ДВ, orange ПД), so the family is settled for the whole sheet for free.
2. system callouts, read through their leader line.
3. equipment callouts whose mark belongs to exactly one system in the spec.
4. section fingerprint - inside one family the systems' section sets barely
   overlap, so a component's measured widths usually name the system.
5. a length budget from the spec, which no system may exceed.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass, field

from .callouts import COLOUR_FAMILY, FAMILY_RE
from .geometry import DuctRun
from .network import Trunk
from .spec import SpecSystem

SEED_SYSTEM_WEIGHT = 5
SEED_EQUIPMENT_WEIGHT = 2
MIN_WIDTH_FIT = 0.7
PROXIMITY_SCALE_PT = 300.0


@dataclass
class Component:
    key: tuple
    colour: str
    family: str | None
    length_m: float = 0.0
    insulated_m: float = 0.0
    widths: collections.Counter = field(default_factory=collections.Counter)
    centre: tuple[float, float] = (0.0, 0.0)
    trunks: list[int] = field(default_factory=list)
    system: str | None = None
    confidence: str = "none"  # "callout" | "fingerprint" | "none"


def build_components(page_number: int, trunks: list[Trunk], component_of: list[int]
                     ) -> dict[tuple, Component]:
    comps: dict[tuple, Component] = {}
    points: dict[tuple, list[tuple[float, float]]] = collections.defaultdict(list)
    for index, trunk in enumerate(trunks):
        key = (page_number, component_of[index])
        comp = comps.get(key)
        if comp is None:
            comp = comps[key] = Component(key=key, colour=trunk.colour,
                                          family=COLOUR_FAMILY.get(trunk.colour))
        comp.length_m += trunk.length_m
        comp.insulated_m += trunk.insulated_m
        comp.widths[round(trunk.width_mm / 25) * 25] += trunk.length_m
        comp.trunks.append(index)
        points[key].extend((trunk.p0, trunk.p1))
    for key, comp in comps.items():
        pts = points[key]
        comp.centre = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return comps


def seed_votes(runs: list[DuctRun], run_to_trunk: list[int | None], component_of: list[int],
               page_number: int, leader_hits, equipment_hits) -> dict[tuple, collections.Counter]:
    """leader_hits / equipment_hits: iterables of (run_index, system name)."""
    votes: dict[tuple, collections.Counter] = collections.defaultdict(collections.Counter)
    for run_index, name in leader_hits:
        trunk = run_to_trunk[run_index]
        if trunk is not None:
            votes[(page_number, component_of[trunk])][name] += SEED_SYSTEM_WEIGHT
    for run_index, name in equipment_hits:
        trunk = run_to_trunk[run_index]
        if trunk is not None:
            votes[(page_number, component_of[trunk])][name] += SEED_EQUIPMENT_WEIGHT
    return votes


def width_fit(widths: collections.Counter, system_widths: set[int], tol: float = 30.0) -> float:
    if not system_widths:
        return 0.0
    hit = sum(length for width, length in widths.items()
              if any(abs(width - known) <= tol for known in system_widths))
    return hit / max(sum(widths.values()), 1e-9)


def assign_systems(components: dict[tuple, Component],
                   votes: dict[tuple, collections.Counter],
                   spec: dict[str, SpecSystem],
                   scope: list[str]) -> dict[tuple, Component]:
    """Fill in `system` and `confidence` on every component, in place."""
    for key, counter in votes.items():
        comp = components.get(key)
        if comp is not None and counter:
            comp.system = counter.most_common(1)[0][0]
            comp.confidence = "callout"

    budget = {name: spec[name].length_m if name in spec else 0.0 for name in scope}
    placed: dict[str, list[tuple[float, float]]] = collections.defaultdict(list)
    for comp in components.values():
        if comp.system:
            budget[comp.system] = budget.get(comp.system, 0.0) - comp.length_m
            placed[comp.system].append(comp.centre)

    remaining = sorted((c for c in components.values() if not c.system),
                       key=lambda c: -c.length_m)
    for comp in remaining:
        if not comp.family:
            continue
        best, best_score = None, 0.0
        for name in scope:
            match = FAMILY_RE.match(name)
            if not match or match.group(1) != comp.family:
                continue
            entry = spec.get(name)
            if entry is None:
                continue
            fit = width_fit(comp.widths, entry.widths_mm)
            if fit < MIN_WIDTH_FIT:
                continue
            if budget.get(name, 0.0) < comp.length_m:
                continue
            near = placed.get(name)
            if near:
                distance = min(math.hypot(comp.centre[0] - x, comp.centre[1] - y)
                               for x, y in near)
                proximity = 1.0 / (1.0 + distance / PROXIMITY_SCALE_PT)
            else:
                proximity = 0.25
            score = 0.6 * fit + 0.4 * proximity
            if score > best_score:
                best, best_score = name, score
        if best:
            comp.system = best
            comp.confidence = "fingerprint"
            budget[best] -= comp.length_m
            placed[best].append(comp.centre)
    return components


def exceeds_specification(totals: dict[str, float], spec: dict[str, SpecSystem],
                          tolerance: float = 1.02) -> list[str]:
    """Systems measured longer than the specification allows - always an error."""
    flagged = []
    for name, measured in totals.items():
        entry = spec.get(name)
        if entry and entry.length_m and measured > entry.length_m * tolerance:
            flagged.append(name)
    return sorted(flagged)
