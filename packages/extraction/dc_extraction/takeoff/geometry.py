"""Measure duct centrelines off a vector HVAC plan.

The drawing carries everything we need, encoded geometrically:

* a duct is a pair of parallel polylines of the same colour, drawn to scale;
* insulation is a cross-hatch in that same colour filling the band;
* an insulated duct is drawn with two concentric outlines (the wall and the
  outer face of the insulation), which must be collapsed to one run.

So the length of a duct is the length of the *centreline* of that pair, never
the summed length of the coloured strokes: on a real sheet the strokes run to
roughly nine times the duct length once hatching and outlines are counted.
"""

from __future__ import annotations

import collections
import contextlib
import math
from dataclasses import dataclass

import pymupdf

# Points are 1/72", so at 1:N one point on paper is 25.4/72*N mm on site.
PT_TO_MM_AT_1_1 = 25.4 / 72

# Duct sizes are standardised, which is what makes automatic scale detection
# possible: only the right scale maps measured band widths onto this ladder.
STANDARD_WIDTHS_MM = (
    100, 125, 150, 160, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650,
    700, 750, 800, 850, 900, 950, 1000, 1100, 1200, 1250, 1400, 1600,
)

# AutoCAD index colours as they land in the PDF, mapped to system families.
DEFAULT_PALETTE = {
    (1.0, 0.0, 0.0): "red",
    (0.0, 0.0, 1.0): "blue",
    (0.0, 0.53, 0.0): "green",
    (0.87, 0.44, 0.0): "orange",
}

ANGLE_TOL = math.radians(0.7)


@dataclass(frozen=True, slots=True)
class DuctRun:
    """One measured stretch of duct centreline."""

    colour: str
    width_mm: float
    insulated: bool
    p0: tuple[float, float]
    p1: tuple[float, float]
    length_m: float


def page_segments(page: pymupdf.Page) -> list[tuple[float, float, float, float, tuple]]:
    """Flatten the page's vector content into straight segments with colour."""
    out: list[tuple[float, float, float, float, tuple]] = []
    for path in page.get_drawings():
        colour = path.get("color")
        if colour is None:
            continue
        key = tuple(round(c, 2) for c in colour)
        for item in path["items"]:
            if item[0] == "l":
                a, b = item[1], item[2]
                out.append((a.x, a.y, b.x, b.y, key))
            elif item[0] == "re":
                r = item[1]
                corners = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
                for i in range(4):
                    q = corners[(i + 1) % 4]
                    out.append((corners[i][0], corners[i][1], q[0], q[1], key))
    return out


def of_colour(segments, colour, min_length: float = 1.5):
    res = []
    for x0, y0, x1, y1, key in segments:
        if key != colour:
            continue
        length = math.hypot(x1 - x0, y1 - y0)
        if length >= min_length:
            res.append((x0, y0, x1, y1, length))
    return res


def merge_collinear(segments, tol: float = 0.35, min_length: float = 2.0):
    """A single duct wall arrives as hundreds of tiny collinear pieces."""
    used = [False] * len(segments)
    ends: dict[tuple[int, int], list[tuple[int, int]]] = collections.defaultdict(list)

    def key(x: float, y: float) -> tuple[int, int]:
        return (round(x / tol), round(y / tol))

    for i, (x0, y0, x1, y1, _) in enumerate(segments):
        ends[key(x0, y0)].append((i, 0))
        ends[key(x1, y1)].append((i, 1))

    out = []
    for i, (x0, y0, x1, y1, _) in enumerate(segments):
        if used[i]:
            continue
        used[i] = True
        pts = [(x0, y0), (x1, y1)]
        for side in (0, 1):
            while True:
                px, py = pts[0] if side == 0 else pts[-1]
                if side == 0:
                    ux, uy = pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]
                else:
                    ux, uy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
                norm = math.hypot(ux, uy)
                if norm == 0:
                    break
                ux, uy = ux / norm, uy / norm
                nxt = None
                for j, end in ends.get(key(px, py), []):
                    if used[j]:
                        continue
                    ax, ay, bx, by, _ = segments[j]
                    qx, qy = (bx, by) if end == 0 else (ax, ay)
                    vx, vy = qx - px, qy - py
                    vnorm = math.hypot(vx, vy)
                    if vnorm == 0:
                        continue
                    if (ux * vx + uy * vy) / vnorm > math.cos(ANGLE_TOL):
                        nxt = (j, qx, qy)
                        break
                if nxt is None:
                    break
                j, qx, qy = nxt
                used[j] = True
                if side == 0:
                    pts.insert(0, (qx, qy))
                else:
                    pts.append((qx, qy))
        out.append((pts[0][0], pts[0][1], pts[-1][0], pts[-1][1],
                    math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])))
    return [s for s in out if s[4] >= min_length]


def detect_hatch(segments) -> set[int]:
    """Insulation hatch seeds: >=4 parallel strokes of identical length."""
    families: dict[tuple[float, float], list[int]] = collections.defaultdict(list)
    for i, (x0, y0, x1, y1, length) in enumerate(segments):
        angle = math.atan2(y1 - y0, x1 - x0) % math.pi
        families[(round(angle, 2), round(length, 1))].append(i)
    hatch: set[int] = set()
    for (_, length), members in families.items():
        if len(members) >= 4 and length < 60:
            hatch.update(members)
    return hatch


def hatch_lattices(hatch) -> list[tuple[float, float]]:
    """Per hatch direction, the spacing between neighbouring strokes."""
    buckets: dict[int, list[tuple[float, float, float, float]]] = collections.defaultdict(list)
    for x0, y0, x1, y1, _ in hatch:
        angle = math.atan2(y1 - y0, x1 - x0) % math.pi
        buckets[int(round(math.degrees(angle)))].append((x0, y0, x1, y1))
    out = []
    for bucket, items in buckets.items():
        if len(items) < 6:
            continue
        angle = math.radians(bucket)
        nx, ny = -math.sin(angle), math.cos(angle)
        offsets = sorted((x0 + x1) / 2 * nx + (y0 + y1) / 2 * ny for x0, y0, x1, y1 in items)
        deltas = [round(offsets[i + 1] - offsets[i], 2) for i in range(len(offsets) - 1)]
        deltas = [d for d in deltas if 0.3 < d < 15]
        if deltas:
            out.append((angle, collections.Counter(deltas).most_common(1)[0][0]))
    return out


def drop_axis_lines(segments, d_max: float = 25.0, overlap_frac: float = 0.5):
    """Remove the dash-dot centre line drawn inside round ducts.

    Pairing takes the nearest parallel partner on each side, so a Ø200 with an
    axis line down the middle is read as two phantom 100 mm ducts and the real
    200 mm pair never forms. An axis line is recognisable: it has parallel
    company at the *same* distance on both sides.
    """
    cell = 60.0
    grid: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for i, (x0, y0, x1, y1, _) in enumerate(segments):
        lo_x, hi_x = sorted((x0, x1))
        lo_y, hi_y = sorted((y0, y1))
        for gx in range(int((lo_x - d_max) // cell), int((hi_x + d_max) // cell) + 1):
            for gy in range(int((lo_y - d_max) // cell), int((hi_y + d_max) // cell) + 1):
                grid[(gx, gy)].append(i)

    axes: set[int] = set()
    for i, (x0, y0, x1, y1, length) in enumerate(segments):
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = -uy, ux
        lo_x, hi_x = sorted((x0, x1))
        lo_y, hi_y = sorted((y0, y1))
        near: set[int] = set()
        for gx in range(int((lo_x - d_max) // cell), int((hi_x + d_max) // cell) + 1):
            for gy in range(int((lo_y - d_max) // cell), int((hi_y + d_max) // cell) + 1):
                near.update(grid.get((gx, gy), ()))
        best = {1: None, -1: None}
        for j in near:
            if j == i:
                continue
            ax, ay, bx, by, other = segments[j]
            vx, vy = (bx - ax) / other, (by - ay) / other
            if abs(ux * vx + uy * vy) < math.cos(ANGLE_TOL):
                continue
            mx, my = (ax + bx) / 2, (ay + by) / 2
            signed = (mx - x0) * nx + (my - y0) * ny
            distance = abs(signed)
            if distance < 0.8 or distance > d_max:
                continue
            span = sorted([(ax - x0) * ux + (ay - y0) * uy, (bx - x0) * ux + (by - y0) * uy])
            overlap = min(length, span[1]) - max(0.0, span[0])
            if overlap < overlap_frac * min(length, other):
                continue
            side = 1 if signed > 0 else -1
            if best[side] is None or distance < best[side]:
                best[side] = distance
        left, right = best[1], best[-1]
        if left is not None and right is not None and abs(left - right) <= 0.2 * max(left, right):
            axes.add(i)
    return [s for i, s in enumerate(segments) if i not in axes]


def grow_hatch(segments, hatch: set[int], rounds: int = 4) -> set[int]:
    """Extend a hatch family along its own lattice.

    The equal-length seed only catches strokes that repeat exactly, so where a
    band widens or tapers - and along its ragged ends - long strokes of varying
    length are left behind and go on to pair with each other into ducts that do
    not exist. A stroke parallel to a known one, a single spacing away and
    overlapping it, belongs to the same family.
    """
    lattices = hatch_lattices([segments[i] for i in hatch])
    if not lattices:
        return hatch
    spacing = collections.Counter(round(s, 2) for _, s in lattices).most_common(1)[0][0]
    cell = 30.0
    grid: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for i, (x0, y0, x1, y1, _) in enumerate(segments):
        grid[(int((x0 + x1) / 2 // cell), int((y0 + y1) / 2 // cell))].append(i)

    current = set(hatch)
    for _ in range(rounds):
        added: set[int] = set()
        for i in current:
            x0, y0, x1, y1, length = segments[i]
            angle = math.atan2(y1 - y0, x1 - x0) % math.pi
            ux, uy = math.cos(angle), math.sin(angle)
            nx, ny = -uy, ux
            offset = x0 * nx + y0 * ny
            t0, t1 = sorted((x0 * ux + y0 * uy, x1 * ux + y1 * uy))
            cx, cy = int((x0 + x1) / 2 // cell), int((y0 + y1) / 2 // cell)
            for dx in (-2, -1, 0, 1, 2):
                for dy in (-2, -1, 0, 1, 2):
                    for j in grid.get((cx + dx, cy + dy), ()):
                        if j in current or j in added:
                            continue
                        ax, ay, bx, by, other = segments[j]
                        if other > 1.6 * length:
                            continue
                        vx, vy = (bx - ax) / other, (by - ay) / other
                        if abs(ux * vx + uy * vy) < math.cos(math.radians(1.0)):
                            continue
                        gap = abs((ax * nx + ay * ny) - offset)
                        if not 0.6 * spacing <= gap <= 1.5 * spacing:
                            continue
                        u0, u1 = sorted((ax * ux + ay * uy, bx * ux + by * uy))
                        if min(t1, u1) - max(t0, u0) < 0.3 * min(length, other):
                            continue
                        added.add(j)
        if not added:
            break
        current |= added
    return current


def wall_pairs(segments, d_min: float = 2.3, d_max: float = 40.0,
               overlap_frac: float = 0.8, overlap_min: float = 4.0, cell: float = 60.0):
    """Pair each wall with its nearest parallel partner on either side."""
    tol = math.cos(ANGLE_TOL)
    grid: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for i, (x0, y0, x1, y1, _) in enumerate(segments):
        lo_x, hi_x = sorted((x0, x1))
        lo_y, hi_y = sorted((y0, y1))
        for gx in range(int((lo_x - d_max) // cell), int((hi_x + d_max) // cell) + 1):
            for gy in range(int((lo_y - d_max) // cell), int((hi_y + d_max) // cell) + 1):
                grid[(gx, gy)].append(i)

    candidates: dict[int, list[tuple]] = collections.defaultdict(list)
    for i, (x0, y0, x1, y1, length) in enumerate(segments):
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = -uy, ux
        lo_x, hi_x = sorted((x0, x1))
        lo_y, hi_y = sorted((y0, y1))
        near: set[int] = set()
        for gx in range(int((lo_x - d_max) // cell), int((hi_x + d_max) // cell) + 1):
            for gy in range(int((lo_y - d_max) // cell), int((hi_y + d_max) // cell) + 1):
                near.update(grid.get((gx, gy), ()))
        for j in near:
            if j == i:
                continue
            ax, ay, bx, by, other = segments[j]
            vx, vy = (bx - ax) / other, (by - ay) / other
            if abs(ux * vx + uy * vy) < tol:
                continue
            mx, my = (ax + bx) / 2, (ay + by) / 2
            signed = (mx - x0) * nx + (my - y0) * ny
            distance = abs(signed)
            if distance < d_min or distance > d_max:
                continue
            span = sorted([(ax - x0) * ux + (ay - y0) * uy, (bx - x0) * ux + (by - y0) * uy])
            lo = max(0.0, span[0])
            hi = min(length, span[1])
            if hi - lo < overlap_min or hi - lo < overlap_frac * min(length, other):
                continue
            candidates[i].append((distance, j, lo, hi, 1 if signed > 0 else -1))

    pairs: dict[tuple[int, int], tuple] = {}
    for i, options in candidates.items():
        for side in (1, -1):
            same_side = [c for c in options if c[4] == side]
            if not same_side:
                continue
            distance, j, lo, hi, _ = min(same_side)
            key = (min(i, j), max(i, j))
            if key in pairs and pairs[key][0] <= distance:
                continue
            x0, y0, x1, y1, length = segments[i]
            ux, uy = (x1 - x0) / length, (y1 - y0) / length
            nx, ny = -uy, ux
            off = side * distance / 2
            pairs[key] = (distance,
                          (x0 + ux * lo + nx * off, y0 + uy * lo + ny * off,
                           x0 + ux * hi + nx * off, y0 + uy * hi + ny * off),
                          hi - lo)
    return pairs


def drop_nested(pairs):
    """Drop a band that lies wholly inside a wider band of the same colour.

    That is what hatch strokes look like once they pair up with each other, and
    also what equipment outlines inside a plant room look like. A duct crossing
    over a bigger duct loses only the metre or so that is genuinely hidden.
    """
    items = sorted(((k, v) for k, v in pairs.items() if v[2] > 0), key=lambda kv: -kv[1][0])
    bands = []
    angles = []
    for _, value in items:
        a, b, c, e = value[1]
        length = math.hypot(c - a, e - b)
        bands.append((a, b, (c - a) / length, (e - b) / length, length, value[0]))
        angles.append(math.atan2(e - b, c - a) % math.pi)

    grid: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for idx, (a, b, ux, uy, length, _) in enumerate(bands):
        for t in range(0, int(length) + 10, 10):
            grid[(int((a + ux * t) // 40), int((b + uy * t) // 40))].append(idx)

    def inside(point, band, pad: float = 1.0) -> bool:
        x, y = point
        a, b, ux, uy, length, width = band
        t = (x - a) * ux + (y - b) * uy
        if t < -pad or t > length + pad:
            return False
        return abs((x - a) * (-uy) + (y - b) * ux) <= width / 2 + pad

    keep = {}
    for i, (key, value) in enumerate(items):
        a, b, ux, uy, length, width = bands[i]
        mid = (a + ux * length / 2, b + uy * length / 2)
        near: set[int] = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                near.update(grid.get((int(mid[0] // 40) + dx, int(mid[1] // 40) + dy), ()))
        nested = False
        for j in near:
            if j >= i or bands[j][5] < width + 2:
                continue
            # Concentric bands - the duct wall inside the outer face of its
            # insulation - share a centreline. Those are the same duct, and the
            # collinear sweep further down keeps the narrower one; dropping the
            # inner band here would measure insulated ducts one size too big.
            delta = abs(angles[i] - angles[j])
            delta = min(delta, math.pi - delta)
            if delta < math.radians(3):
                oa, ob, oux, ouy, _, _ = bands[j]
                if abs((mid[0] - oa) * (-ouy) + (mid[1] - ob) * oux) < 1.5:
                    continue
            if (inside(mid, bands[j]) and inside((a, b), bands[j])
                    and inside((a + ux * length, b + uy * length), bands[j])):
                nested = True
                break
        if not nested:
            keep[key] = value
    return keep


def drop_hatch_pairs(pairs, lattices, colour_segments):
    """Reject pairs that are two neighbouring strokes of an insulation hatch.

    A cross-hatch is two families of strokes crossing each other, so anything
    lying inside one is crossed by the other family at the lattice spacing -
    roughly one crossing every 5.67 pt at 1:100. A real duct centreline is
    crossed far more rarely, and only where another duct passes over it.

    This is what catches the strokes inside elbows, where the hatch fans out and
    every stroke has a different length, so the equal-length seed and its
    lattice growth both miss them.
    """
    if not lattices:
        return pairs

    cell = 40.0
    grid: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for index, (x0, y0, x1, y1, length) in enumerate(colour_segments):
        steps = max(1, int(length / cell))
        for t in range(steps + 1):
            px = x0 + (x1 - x0) * t / steps
            py = y0 + (y1 - y0) * t / steps
            grid[(int(px // cell), int(py // cell))].append(index)

    def crossings(line) -> int:
        ax, ay, bx, by = line
        length = math.hypot(bx - ax, by - ay)
        if length <= 0:
            return 0
        angle = math.atan2(by - ay, bx - ax) % math.pi
        near: set[int] = set()
        steps = max(1, int(length / cell))
        for t in range(steps + 1):
            px = ax + (bx - ax) * t / steps
            py = ay + (by - ay) * t / steps
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    near.update(grid.get((int(px // cell) + dx, int(py // cell) + dy), ()))
        by_direction: collections.Counter[int] = collections.Counter()
        for index in near:
            cx0, cy0, cx1, cy1, _ = colour_segments[index]
            other = math.atan2(cy1 - cy0, cx1 - cx0) % math.pi
            delta = abs(angle - other)
            delta = min(delta, math.pi - delta)
            if delta < math.radians(30):
                continue
            d1x, d1y = bx - ax, by - ay
            d2x, d2y = cx1 - cx0, cy1 - cy0
            det = d1x * d2y - d1y * d2x
            if abs(det) < 1e-9:
                continue
            t1 = ((cx0 - ax) * d2y - (cy0 - ay) * d2x) / det
            t2 = ((cx0 - ax) * d1y - (cy0 - ay) * d1x) / det
            if 0.0 <= t1 <= 1.0 and 0.0 <= t2 <= 1.0:
                by_direction[int(round(math.degrees(other) / 2))] += 1
        # Only one *family* counts: an insulation hatch crosses at a single
        # angle all the way along, while grille symbols and flexible connectors
        # throw strokes at every angle.
        return max(by_direction.values(), default=0)

    keep = {}
    for key, (width, line, length) in pairs.items():
        angle = math.atan2(line[3] - line[1], line[2] - line[0]) % math.pi
        is_hatch = False
        for hatch_angle, spacing in lattices:
            delta = abs(angle - hatch_angle)
            delta = min(delta, math.pi - delta)
            if delta >= math.radians(4) or abs(width - spacing) >= 0.35:
                continue
            span = math.hypot(line[2] - line[0], line[3] - line[1])
            expected = span / max(spacing, 1e-9)
            found = crossings(line)
            if expected >= 3 and found >= 0.5 * expected:
                is_hatch = True
                break
        if not is_hatch:
            keep[key] = (width, line, length)
    return keep


def detect_scale(page: pymupdf.Page, palette=None, candidates=(100, 50, 200)) -> int:
    """Pick the drawing scale whose band widths land on standard duct sizes.

    Widths alone cannot always separate scales that differ by a factor of two -
    600 mm at 1:100 reads as 300 mm at 1:50, and both are standard sizes - so
    ties go to the first candidate. Pass `scale` explicitly when the sheet says
    what it is.
    """
    palette = palette or DEFAULT_PALETTE
    segments = page_segments(page)
    widths: collections.Counter[float] = collections.Counter()
    for colour in palette:
        merged = merge_collinear(of_colour(segments, colour))
        if not merged:
            continue
        hatch_idx = grow_hatch(merged, detect_hatch(merged))
        walls = drop_axis_lines([s for i, s in enumerate(merged) if i not in hatch_idx])
        for width, _, length in wall_pairs(walls).values():
            widths[round(width, 2)] += length
    if not widths:
        return candidates[0]
    best, best_score = candidates[0], -1.0
    for scale in candidates:
        mm_per_pt = PT_TO_MM_AT_1_1 * scale
        score = 0.0
        for width, weight in widths.items():
            mm = width * mm_per_pt
            nearest = min(STANDARD_WIDTHS_MM, key=lambda s: abs(s - mm))
            if abs(nearest - mm) <= max(8.0, 0.03 * nearest):
                score += weight
        if score > best_score:
            best, best_score = scale, score
    return best


STRETCH_SPAN = 2.0  # pt of centreline offset one collinear stretch may cover


def _stretches(groups):
    """Split each same-angle group into collinear stretches of bounded spread.

    A wall paired with the outer face of the insulation on the opposite side
    gives a band whose centreline sits a fraction of a point off the duct's.
    Bucketing offsets by rounding put that band in the neighbouring bucket
    whenever the duct's centreline fell near a bucket edge, so the same duct
    was counted twice depending only on where it sat on the sheet. Anchoring
    each stretch on its first offset keeps the old bucket width without the
    edges; chaining neighbour to neighbour instead would let a run of close
    offsets glue genuinely different ducts together.
    """
    for members in groups:
        ordered = sorted(members, key=lambda m: m[5])
        stretch = [ordered[0]]
        for member in ordered[1:]:
            if member[5] - stretch[0][5] > STRETCH_SPAN:
                yield stretch
                stretch = []
            stretch.append(member)
        yield stretch


def centrelines(page: pymupdf.Page, scale: int = 100, palette=None) -> list[DuctRun]:
    """Measure every duct run on the page."""
    palette = palette or DEFAULT_PALETTE
    mm_per_pt = PT_TO_MM_AT_1_1 * scale
    segments = page_segments(page)
    runs: list[DuctRun] = []

    for colour, name in palette.items():
        merged = merge_collinear(of_colour(segments, colour))
        if not merged:
            continue
        hatch_idx = grow_hatch(merged, detect_hatch(merged))
        hatch = [merged[i] for i in hatch_idx]
        walls = drop_axis_lines([s for i, s in enumerate(merged) if i not in hatch_idx])
        pairs = wall_pairs(walls)
        pairs = drop_nested(pairs)
        pairs = drop_hatch_pairs(pairs, hatch_lattices(hatch), merged)

        hatch_grid: dict[tuple[int, int], list[tuple[float, float]]] = collections.defaultdict(list)
        for x0, y0, x1, y1, _ in hatch:
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            hatch_grid[(int(mx // 10), int(my // 10))].append((mx, my))

        def is_insulated(line, width, grid=hatch_grid) -> bool:
            a, b, c, e = line
            length = math.hypot(c - a, e - b)
            if length <= 0:
                return False
            samples = max(2, int(length / 4))
            hits = 0
            for t in range(samples + 1):
                px = a + (c - a) * t / samples
                py = b + (e - b) * t / samples
                found = False
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for mx, my in grid.get((int(px // 10) + dx, int(py // 10) + dy), ()):
                            if (mx - px) ** 2 + (my - py) ** 2 < (width * 0.6) ** 2:
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break
                hits += found
            return hits > 0.5 * (samples + 1)

        # An insulated duct carries two concentric outlines; sweep each
        # collinear stretch and keep only the narrower (the duct itself).
        by_angle: dict[int, list[tuple]] = collections.defaultdict(list)
        for width, line, _ in pairs.values():
            x0, y0, x1, y1 = line
            angle = math.atan2(y1 - y0, x1 - x0) % math.pi
            ux, uy = math.cos(angle), math.sin(angle)
            nx, ny = -uy, ux
            t0, t1 = sorted((x0 * ux + y0 * uy, x1 * ux + y1 * uy))
            off = x0 * nx + y0 * ny
            by_angle[round(angle / 0.02)].append(
                (t0, t1, width, is_insulated(line, width), angle, off))

        for members in _stretches(by_angle.values()):
            events = []
            for t0, t1, width, insulated, angle, off in members:
                events.append((t0, 1, width, insulated, angle, off))
                events.append((t1, -1, width, insulated, angle, off))
            events.sort(key=lambda e: (e[0], -e[1]))
            active: list[tuple] = []
            previous = None
            for t, kind, width, insulated, angle, off in events:
                if previous is not None and active and t > previous:
                    width2, insulated2, angle2, off2 = min(active)
                    ux, uy = math.cos(angle2), math.sin(angle2)
                    nx, ny = -uy, ux
                    runs.append(DuctRun(
                        colour=name,
                        width_mm=width2 * mm_per_pt,
                        insulated=insulated2,
                        p0=(ux * previous + nx * off2, uy * previous + ny * off2),
                        p1=(ux * t + nx * off2, uy * t + ny * off2),
                        length_m=(t - previous) * mm_per_pt / 1000,
                    ))
                if kind == 1:
                    active.append((width, insulated, angle, off))
                else:
                    with contextlib.suppress(ValueError):
                        active.remove((width, insulated, angle, off))
                previous = t
    return runs


def snap_width(width_mm: float, tolerance: float = 30.0) -> int | None:
    nearest = min(STANDARD_WIDTHS_MM, key=lambda s: abs(s - width_mm))
    return nearest if abs(nearest - width_mm) <= tolerance else None
