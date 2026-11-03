"""Count grilles and fire dampers off a plan sheet.

A grille is written as its label followed by its face size on the same line -
"АМР 400х200", "АДР-К 650x300" - and a damper as one word,
"КЛАПЪ-(60)-НО-100x100". Each occurrence on a plan is one fitting; the
specification states how many the whole building has, so the counts reconcile
the same way the duct lengths do.

Cyrillic "х" and Latin "x" are one size, so marks are normalised to "x".
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

import pymupdf

from .callouts import GRILLE_LABEL_RE, SIZE_RE, normalise_size
from .spec import SpecSystem
from .text import page_words

FittingKind = Literal["решётка", "клапан"]

DAMPER_RE = re.compile(r"^КЛАПЪ-\(\d+\)-Н[ОЗ]\(?C?\)?-\d+[xх]\d+")
# Same bound the callout reader uses for "a size right after its label".
LABEL_GAP = 25.0
LINE_TOLERANCE = 1.0


@dataclass(frozen=True)
class Fitting:
    mark: str
    kind: FittingKind
    x: float
    y: float


def normalise_mark(mark: str) -> str:
    return mark.replace("х", "x").replace("×", "x")


def fittings(page: pymupdf.Page) -> list[Fitting]:
    """Every grille and damper mark on `page`, at the centre of its size word."""
    words = page_words(page)
    found: list[Fitting] = []
    for word in words:
        text = word[4].replace(" ", "")
        centre = ((word[0] + word[2]) / 2, (word[1] + word[3]) / 2)
        damper = DAMPER_RE.match(text)
        if damper:
            # the plan adds the actuator ("-BМ220"); the specification row does not
            found.append(Fitting(normalise_mark(damper.group(0)), "клапан", *centre))
            continue
        if not SIZE_RE.match(text):
            continue
        for other in words:
            gap = word[0] - other[2]
            if (other is not word and abs(other[1] - word[1]) <= LINE_TOLERANCE
                    and 0 <= gap < LABEL_GAP and GRILLE_LABEL_RE.match(other[4])):
                size = normalise_size(text)
                found.append(Fitting(f"{other[4]} {size}", "решётка", *centre))
                break
    return found


def spec_fitting_counts(spec: dict[str, SpecSystem]) -> dict[str, int]:
    """Equipment rows of the specification, summed over systems, marks normalised."""
    total: Counter = Counter()
    for entry in spec.values():
        for mark, count in entry.equipment.items():
            total[normalise_mark(mark)] += count
    return dict(total)
