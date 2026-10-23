"""Read the callouts on an HVAC plan and tie them to measured duct runs.

A callout is a stack of text lines over a horizontal rule, with a leader
polyline running from one end of that rule to the duct it describes:

    В4
    600x500
    ─────────╲
               ╲──▶ duct

A grille or damper is labelled the same size-shaped way as a duct - "АМР
400х200" reads, to a regex, exactly like a duct section. That size is real
(it is the grille's own face), just not the duct's: a grille's face commonly
matches the spigot it sits on, so a naive width-match sanity check does not
catch it either - on sheet 6, 57 of 151 grille sizes that reach a leader
target slip through undetected and would silently overwrite that duct's true
section. What actually distinguishes them is not the Cyrillic "х" some of
them happen to use (a few genuine duct sections are typed with it too, most
likely by inconsistent hand-entry) but where they sit: a grille's size is
written immediately after its own label (АМР/АДР/АДР-К/АРН/Рс) on the same
line, a duct's is not.
"""

from __future__ import annotations

import collections
import math
import re

import pymupdf

from .geometry import PT_TO_MM_AT_1_1, DuctRun

SIZE_RE = re.compile(r"^([⌀øØФф]\s?\d{2,4}|\d{2,4}\s?[xх×]\s?\d{2,4})$")
SYSTEM_RE = re.compile(r"^(В|П|ДВ|ПД|ДП)\d+(\.\d+)?[аб]?$")
# A grille/damper label a size is written right after, on the same line -
# "АМР 400х200" - naming the fitting's own face, not the duct it sits on.
GRILLE_LABEL_RE = re.compile(r"^(АМР|АДР(-К)?|АРН|Рс)$")
_GRILLE_LABEL_GAP = 25.0
EQUIPMENT_RE = re.compile(
    r"(КЛАПЪ-\(\d+\)-Н[ОЗ]\(?C?\)?-\d+x\d+|АДР[ -][\dхx]+|АРН[ -][\dхx]+|АМР[ -][\dхx]+)"
)
FAMILY_RE = re.compile(r"^(ДВ|ПД|ДП|В|П)")

COLOUR_FAMILY = {"red": "П", "blue": "В", "green": "ДВ", "orange": "ПД"}

_STACK_LIMIT = 40.0


def normalise_size(text: str) -> str:
    text = text.replace(" ", "").replace("х", "x").replace("×", "x")
    for char in "øØФф⌀":
        text = text.replace(char, "Ø")
    return text


def size_dimensions(text: str) -> tuple[int, int]:
    if text.startswith("Ø"):
        diameter = int(text[1:])
        return diameter, diameter
    a, b = text.split("x")
    return int(a), int(b)


def labelled_sizes(page: pymupdf.Page) -> frozenset[int]:
    """Every section dimension written on the sheet, in mm - a scale witness."""
    sizes: set[int] = set()
    for word in page.get_text("words"):
        text = word[4].replace(" ", "")
        if SIZE_RE.match(text):
            sizes.update(size_dimensions(normalise_size(text)))
    return frozenset(sizes)


def _black_segments(page: pymupdf.Page) -> list[tuple[float, float, float, float]]:
    out = []
    for path in page.get_drawings():
        if path.get("color") != (0.0, 0.0, 0.0):
            continue
        for item in path["items"]:
            if item[0] == "l":
                a, b = item[1], item[2]
                out.append((a.x, a.y, b.x, b.y))
    return out


def leaders(page: pymupdf.Page) -> list[tuple[str, str, float, float]]:
    """Resolve every callout to the point its leader touches.

    Returns (kind, text, x, y) with kind in {"size", "system"}.
    """
    black = _black_segments(page)
    ends: dict[tuple[int, int], list[tuple[int, int]]] = collections.defaultdict(list)

    def key(x: float, y: float) -> tuple[int, int]:
        return (round(x / 1.2), round(y / 1.2))

    for i, (x0, y0, x1, y1) in enumerate(black):
        ends[key(x0, y0)].append((i, 0))
        ends[key(x1, y1)].append((i, 1))

    def follow(sx: float, sy: float, max_steps: int = 12):
        current = (sx, sy)
        seen: set[int] = set()
        steps = 0
        for _ in range(max_steps):
            nxt = None
            for i, end in ends.get(key(*current), []):
                if i in seen:
                    continue
                x0, y0, x1, y1 = black[i]
                if math.hypot(x1 - x0, y1 - y0) < 0.5:
                    continue
                seen.add(i)
                nxt = (x1, y1) if end == 0 else (x0, y0)
                break
            if nxt is None:
                break
            current = nxt
            steps += 1
        return current, steps

    words = page.get_text("words")

    def stacked_above(word):
        """Lines standing over `word` share its underline and its leader."""
        result = []
        for other in words:
            if other is word:
                continue
            if other[3] > word[1] + 0.5 or other[3] < word[1] - _STACK_LIMIT:
                continue
            overlap = min(other[2], word[2]) - max(other[0], word[0])
            if overlap < 0.3 * min(other[2] - other[0], word[2] - word[0]):
                continue
            result.append(other)
        return result

    def classify(text: str) -> str | None:
        if SIZE_RE.match(text):
            return "size"
        if SYSTEM_RE.match(text):
            return "system"
        return None

    def names_a_grille(word) -> bool:
        """Is `word` a size sitting right after a grille/damper label?"""
        for other in words:
            if other is word or abs(other[1] - word[1]) > 1.0:
                continue
            gap = word[0] - other[2]
            if 0 <= gap < _GRILLE_LABEL_GAP and GRILLE_LABEL_RE.match(other[4]):
                return True
        return False

    out: list[tuple[str, str, float, float]] = []
    for word in words:
        kind = classify(word[4])
        if kind is None:
            continue
        if kind == "size" and names_a_grille(word):
            continue  # this size is the grille's own face, not the duct's
        x0, y0, x1, y1 = word[0], word[1], word[2], word[3]
        rule = None
        for ax, ay, bx, by in black:
            if abs(ay - by) > 0.4 or not (y1 - 1.0 <= ay <= y1 + 4.0):
                continue
            lo, hi = sorted((ax, bx))
            if lo <= x0 + 1 and hi >= x1 - 1 and (rule is None or hi - lo < rule[0]):
                rule = (hi - lo, lo, hi, ay)
        if rule is None:
            continue
        _, lo, hi, ay = rule
        reaches = []
        for px, py in ((lo, ay), (hi, ay)):
            far, steps = follow(px, py)
            if steps > 1:
                reaches.append((math.hypot(far[0] - px, far[1] - py), far))
        if not reaches:
            continue
        _, far = max(reaches)
        payload = normalise_size(word[4]) if kind == "size" else word[4]
        out.append((kind, payload, far[0], far[1]))
        for other in stacked_above(word):
            other_kind = classify(other[4])
            if other_kind is None:
                continue
            if other_kind == "size" and names_a_grille(other):
                continue
            text = normalise_size(other[4]) if other_kind == "size" else other[4]
            out.append((other_kind, text, far[0], far[1]))
    return sorted(set(out))


def equipment_marks(page: pymupdf.Page) -> list[tuple[str, tuple]]:
    """Equipment marks with their word box, for use as attribution anchors."""
    out = []
    for word in page.get_text("words"):
        match = EQUIPMENT_RE.match(word[4])
        if match:
            out.append((match.group(1), word))
    return out


def nearest_run(runs: list[DuctRun], px: float, py: float, scale: int = 100,
                slack: float = 8.0, colours: set[str] | None = None
               ) -> tuple[int | None, float]:
    """A leader points at the duct *wall*, so score distance to the band.

    Once the leader's endpoint lands inside a band, distance-to-wall clamps
    to zero, and a wide duct's band reaches much further out than a narrow
    one's - so a callout meant for a slim orange damper can tie at zero
    against a fat blue duct routed past it and lose to whichever happens to
    come first in `runs`. Pass `colours` (the callout's system family, from
    :data:`COLOUR_FAMILY`) to restrict the search up front and rule that out;
    within the tie, prefer the smaller raw distance rather than list order.
    """
    mm_per_pt = PT_TO_MM_AT_1_1 * scale
    best, best_raw, best_index = slack, None, None
    for i, run in enumerate(runs):
        if colours is not None and run.colour not in colours:
            continue
        a, b = run.p0, run.p1
        vx, vy = b[0] - a[0], b[1] - a[1]
        squared = vx * vx + vy * vy
        if squared == 0:
            continue
        t = max(0.0, min(1.0, ((px - a[0]) * vx + (py - a[1]) * vy) / squared))
        distance = math.hypot(a[0] + vx * t - px, a[1] + vy * t - py)
        score = max(0.0, distance - run.width_mm / mm_per_pt / 2 - 1.0)
        if score < best or (score == best and (best_raw is None or distance < best_raw)):
            best, best_raw, best_index = score, distance, i
    return best_index, best
