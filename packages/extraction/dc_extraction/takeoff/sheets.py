"""Tell plan sheets from the rest of an HVAC album by their title block.

Only plans are measured. System schematics are drawn in the same colours, so
the geometry alone would happily "measure" them (800-1100 m per schematic on
the benchmark album); the title is what separates them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import pymupdf

SheetKind = Literal["plan", "schematic", "specification", "other"]

TITLE_RE = re.compile(r"^\s*((План|Схема)\b.*?)\s*$", re.MULTILINE)
SPEC_TITLE_RE = re.compile(r"^\s*(Спецификаци[яи]\b.*?)\s*$", re.MULTILINE)
# Column header of the ГОСТ 21.110 specification form; continuation sheets
# carry nothing else that identifies them.
SPEC_FORM_HEADER = "Наименование и техническая характеристика"
# A sheet naming this many drawings is the album's sheet list, not a drawing.
SHEET_LIST_MIN_TITLES = 3


@dataclass(frozen=True)
class Sheet:
    kind: SheetKind
    title: str | None


def classify_sheet(page: pymupdf.Page) -> Sheet:
    # Fonts often extract word gaps as no-break spaces and hyphens as soft
    # hyphens; titles are matched and shown with the plain characters.
    text = re.sub(r"[ \t ]+", " ", page.get_text()).replace("­", "-")
    titles = list(dict.fromkeys(m.group(1) for m in TITLE_RE.finditer(text)))
    spec_titles = list(dict.fromkeys(m.group(1) for m in SPEC_TITLE_RE.finditer(text)))
    if len(titles) + len(spec_titles) >= SHEET_LIST_MIN_TITLES:
        return Sheet("other", None)
    if spec_titles or SPEC_FORM_HEADER in text:
        return Sheet("specification", spec_titles[0] if spec_titles else None)
    if not titles:
        return Sheet("other", None)
    title = titles[0]
    return Sheet("schematic" if title.startswith("Схема") else "plan", title)
