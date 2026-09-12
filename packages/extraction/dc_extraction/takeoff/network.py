"""Turn measured duct runs into a connected network.

Two things make this harder than it looks on a plan view:

* the measuring pass cuts a run wherever another band overlaps it, so raw runs
  carry false endpoints exactly at plan crossings - they must be re-merged into
  maximal trunks before any endpoint means anything;
* elbows are drawn as arcs, which reach the page as sub-2pt chords and are
  filtered out upstream, so two trunks turning into each other stop short of
  the corner by up to a duct width.

And two things that look like connections but are not: ducts of different
systems crossing at different levels, and parallel risers bundled along a wall.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass, field

from .geometry import PT_TO_MM_AT_1_1, DuctRun

END_TOL = 5.0
TEE_TOL = 4.0
COLLINEAR_GAP = 8.0
PARALLEL_TOL = math.radians(10)


@dataclass
class Trunk:
    colour: str
    angle: float
    offset: float
    t0: float
    t1: float
    p0: tuple[float, float]
    p1: tuple[float, float]
    length_m: float
    width_mm: float
    insulated_m: float
    members: list[int] = field(default_factory=list)


def _axis(run: DuctRun):
    a, b = run.p0, run.p1
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length == 0:
        return None
    angle = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
    ux, uy = math.cos(angle), math.sin(angle)
    nx, ny = -uy, ux
    t0, t1 = sorted((a[0] * ux + a[1] * uy, b[0] * ux + b[1] * uy))
    return angle, a[0] * nx + a[1] * ny, t0, t1


def merge_trunks(runs: list[DuctRun], gap: float = 2.5) -> tuple[list[Trunk], list[int | None]]:
    """Merge collinear, contiguous runs of one colour into maximal trunks."""
    meta = [_axis(r) for r in runs]
    parent = list(range(len(runs)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    buckets: dict[tuple, list[int]] = collections.defaultdict(list)
    for i, m in enumerate(meta):
        if m is None:
            continue
        angle, offset, _, _ = m
        bucket = int(round(math.degrees(angle)))
        for db in (-1, 0, 1):
            for do in (-1, 0, 1):
                buckets[(runs[i].colour, bucket + db, int(offset // 2) + do)].append(i)

    checked: set[tuple[int, int]] = set()
    for members in buckets.values():
        members = sorted(set(members))
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                i, j = members[a], members[b]
                if (i, j) in checked:
                    continue
                checked.add((i, j))
                ai, oi, t0i, t1i = meta[i]
                aj, oj, t0j, t1j = meta[j]
                delta = abs(ai - aj)
                delta = min(delta, math.pi - delta)
                if delta > math.radians(0.7) or abs(oi - oj) > 1.5:
                    continue
                if max(t0j - t1i, t0i - t1j) <= gap:
                    union(i, j)

    groups: dict[int, list[int]] = collections.defaultdict(list)
    for i, m in enumerate(meta):
        if m is not None:
            groups[find(i)].append(i)

    trunks: list[Trunk] = []
    index: list[int | None] = [None] * len(runs)
    for members in groups.values():
        angle = meta[members[0]][0]
        ux, uy = math.cos(angle), math.sin(angle)
        nx, ny = -uy, ux
        offset = sum(meta[i][1] for i in members) / len(members)
        t0 = min(meta[i][2] for i in members)
        t1 = max(meta[i][3] for i in members)
        k = len(trunks)
        trunks.append(Trunk(
            colour=runs[members[0]].colour,
            angle=angle, offset=offset, t0=t0, t1=t1,
            p0=(ux * t0 + nx * offset, uy * t0 + ny * offset),
            p1=(ux * t1 + nx * offset, uy * t1 + ny * offset),
            length_m=sum(runs[i].length_m for i in members),
            width_mm=max(runs[i].width_mm for i in members),
            insulated_m=sum(runs[i].length_m for i in members if runs[i].insulated),
            members=members,
        ))
        for i in members:
            index[i] = k
    return trunks, index


def connect(trunks: list[Trunk], scale: int = 100, end_tol: float = END_TOL,
            tee_tol: float = TEE_TOL, collinear_gap: float = COLLINEAR_GAP) -> list[int]:
    """Union trunks that genuinely meet; return a component id per trunk."""
    mm_per_pt = PT_TO_MM_AT_1_1 * scale
    parent = list(range(len(trunks)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    def angle_between(a: Trunk, b: Trunk) -> float:
        delta = abs(a.angle - b.angle)
        return min(delta, math.pi - delta)

    cell = 20.0
    ends: dict[tuple[int, int], list[tuple[float, float, int]]] = collections.defaultdict(list)
    for k, trunk in enumerate(trunks):
        for p in (trunk.p0, trunk.p1):
            ends[(int(p[0] // cell), int(p[1] // cell))].append((p[0], p[1], k))

    # 1. end to end: a corner, or a straight run interrupted by a fitting.
    for k, trunk in enumerate(trunks):
        for p in (trunk.p0, trunk.p1):
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cellkey = (int(p[0] // cell) + dx, int(p[1] // cell) + dy)
                    for x, y, j in ends.get(cellkey, ()):
                        if j == k or trunks[j].colour != trunk.colour:
                            continue
                        if math.hypot(x - p[0], y - p[1]) > end_tol:
                            continue
                        # parallel neighbours in a riser bundle touch without
                        # being connected
                        if (angle_between(trunk, trunks[j]) > PARALLEL_TOL
                                or abs(trunk.offset - trunks[j].offset) < 2.5):
                            union(k, j)

    # 2. elbow: rebuild the corner the dropped arc used to occupy.
    for k, trunk in enumerate(trunks):
        radius_k = trunk.width_mm / mm_per_pt
        for p in (trunk.p0, trunk.p1):
            reach = max(6.0, 1.2 * radius_k)
            span = int(reach // cell) + 1
            for dx in range(-span, span + 1):
                for dy in range(-span, span + 1):
                    cellkey = (int(p[0] // cell) + dx, int(p[1] // cell) + dy)
                    for x, y, j in ends.get(cellkey, ()):
                        other = trunks[j]
                        if j == k or other.colour != trunk.colour:
                            continue
                        if angle_between(trunk, other) < PARALLEL_TOL:
                            continue
                        limit = max(6.0, 1.2 * max(radius_k, other.width_mm / mm_per_pt))
                        if math.hypot(x - p[0], y - p[1]) > limit:
                            continue
                        n1 = (-math.sin(trunk.angle), math.cos(trunk.angle))
                        n2 = (-math.sin(other.angle), math.cos(other.angle))
                        det = n1[0] * n2[1] - n1[1] * n2[0]
                        if abs(det) < 1e-9:
                            continue
                        cx = (trunk.offset * n2[1] - other.offset * n1[1]) / det
                        cy = (other.offset * n1[0] - trunk.offset * n2[0]) / det
                        if (math.hypot(cx - p[0], cy - p[1]) <= limit
                                and math.hypot(cx - x, cy - y) <= limit):
                            union(k, j)

    # 3. a branch: one trunk ends on another trunk's body.
    body: dict[tuple[int, int], list[tuple[float, float, int]]] = collections.defaultdict(list)
    for k, trunk in enumerate(trunks):
        a, b = trunk.p0, trunk.p1
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(length / 3))
        for t in range(steps + 1):
            px = a[0] + (b[0] - a[0]) * t / steps
            py = a[1] + (b[1] - a[1]) * t / steps
            body[(int(px // 6), int(py // 6))].append((px, py, k))
    for k, trunk in enumerate(trunks):
        for p in (trunk.p0, trunk.p1):
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cellkey = (int(p[0] // 6) + dx, int(p[1] // 6) + dy)
                    for px, py, j in body.get(cellkey, ()):
                        if j == k or trunks[j].colour != trunk.colour:
                            continue
                        if math.hypot(px - p[0], py - p[1]) > tee_tol:
                            continue
                        if angle_between(trunk, trunks[j]) > PARALLEL_TOL:
                            union(k, j)

    # 4. collinear continuation across a damper, silencer or short break.
    lines: dict[tuple, list[int]] = collections.defaultdict(list)
    for k, trunk in enumerate(trunks):
        lines[(trunk.colour, round(math.degrees(trunk.angle) / 2),
               int(trunk.offset // 3))].append(k)
    for members in lines.values():
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                i, j = members[a], members[b]
                first, second = trunks[i], trunks[j]
                if abs(first.offset - second.offset) > 2.5:
                    continue
                ratio = first.width_mm / max(second.width_mm, 1e-9)
                if not 0.85 <= ratio <= 1.18:
                    continue
                if max(second.t0 - first.t1, first.t0 - second.t1) <= collinear_gap:
                    union(i, j)

    return [find(i) for i in range(len(trunks))]
