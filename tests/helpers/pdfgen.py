"""Synthetic construction PDFs for tests and the benchmark harness.

Generates a "drawing" page (tags + characteristics scattered as callouts) and
a "specification" page (a ruled table PyMuPDF can detect), so the whole
pipeline can be exercised end-to-end without proprietary project files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

FONT = "F0"  # embedded TTF with Cyrillic coverage (see _FONT_CANDIDATES)

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def _font_file() -> str:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("no TTF with Cyrillic coverage found for test PDF generation")


@dataclass
class SpecRow:
    tag: str
    name: str
    quantity: str  # as written, e.g. "8"
    unit: str = "шт."
    characteristic: str = ""  # e.g. "12 000 м3/ч"


@dataclass
class DrawingCallout:
    tag: str
    lines: list[str] = field(default_factory=list)  # e.g. ["15 000 м3/ч", "5,5 кВт"]


def make_drawing_pdf(path: str | Path, callouts: list[DrawingCallout]) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)  # A4 landscape
    page.insert_font(fontname=FONT, fontfile=_font_file())
    page.insert_text((40, 40), "PLAN OV-05 / HVAC LAYOUT", fontsize=14, fontname=FONT)
    x, y = 80, 120
    for callout in callouts:
        page.draw_rect(pymupdf.Rect(x - 8, y - 16, x + 160, y + 14 + 14 * len(callout.lines)))
        page.insert_text((x, y), callout.tag, fontsize=12, fontname=FONT)
        for i, line in enumerate(callout.lines):
            page.insert_text((x, y + 16 + 14 * i), line, fontsize=9, fontname=FONT)
        x += 200
        if x > 650:
            x = 80
            y += 120
    doc.save(str(path))
    doc.close()


def make_spec_pdf(path: str | Path, rows: list[SpecRow], title: str = "СПЕЦИФИКАЦИЯ ОВ-СП") -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4 portrait
    page.insert_font(fontname=FONT, fontfile=_font_file())
    page.insert_text((40, 50), title, fontsize=13, fontname=FONT)

    headers = ["Поз.", "Наименование", "Характеристика", "Ед.", "Кол-во"]
    col_x = [40, 110, 320, 470, 510, 560]
    top = 90
    row_height = 26
    bottom = top + row_height * (len(rows) + 1)

    for x in col_x:
        page.draw_line((x, top), (x, bottom))
    for i in range(len(rows) + 2):
        y = top + row_height * i
        page.draw_line((col_x[0], y), (col_x[-1], y))

    def put(col: int, row: int, text: str, size: float = 9) -> None:
        page.insert_text((col_x[col] + 4, top + row_height * row + 17), text,
                         fontsize=size, fontname=FONT)

    for c, header in enumerate(headers):
        put(c, 0, header, size=9)
    for r, row in enumerate(rows, start=1):
        put(0, r, row.tag)
        put(1, r, row.name)
        put(2, r, row.characteristic)
        put(3, r, row.unit)
        put(4, r, row.quantity)
    doc.save(str(path))
    doc.close()
