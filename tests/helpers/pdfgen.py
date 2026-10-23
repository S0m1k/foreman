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


# --------------------------------------------------------------------------- #
# Vector duct plan, for the takeoff pipeline.
#
# Drawn the way a real HVAC sheet is: each duct is a pair of parallel lines at
# the true scale, insulation is a cross-hatch in the same colour between two
# concentric outlines, and callouts are text stacks over a rule with a leader.
# --------------------------------------------------------------------------- #

import math  # noqa: E402

MM_PER_PT_AT_1_100 = 25.4 / 72 * 100


@dataclass
class DuctSegment:
    start: tuple[float, float]  # metres, in plan coordinates
    end: tuple[float, float]
    width_mm: float
    colour: tuple[float, float, float] = (0.0, 0.0, 1.0)
    insulated: bool = False
    insulation_mm: float = 20.0
    axis: bool = False          # dash-dot centre line, as drawn in round ducts
    hatch_jitter: float = 0.0   # vary stroke length, as a hatch does in an elbow


def _to_points(metres: float) -> float:
    return metres * 1000 / MM_PER_PT_AT_1_100


def _draw_band(page, origin, seg: DuctSegment, half_mm: float, width: float = 0.5) -> None:
    ox, oy = origin
    ax, ay = ox + _to_points(seg.start[0]), oy + _to_points(seg.start[1])
    bx, by = ox + _to_points(seg.end[0]), oy + _to_points(seg.end[1])
    length = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / length, (by - ay) / length
    nx, ny = -uy, ux
    half = half_mm / MM_PER_PT_AT_1_100
    for sign in (1, -1):
        page.draw_line((ax + nx * half * sign, ay + ny * half * sign),
                       (bx + nx * half * sign, by + ny * half * sign),
                       color=seg.colour, width=width)


Callout = tuple[tuple[float, float], list[str], tuple[float, float]]


def make_duct_plan_pdf(path: str | Path, segments: list[DuctSegment],
                       callouts: list[Callout] | None = None,
                       origin: tuple[float, float] = (60.0, 60.0)) -> None:
    """Draw ducts at 1:100 plus optional leader callouts.

    `callouts` entries are (text anchor in points, stacked lines, target point
    in metres) - the leader runs from the end of the rule to the target.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=1200, height=850)
    page.insert_font(fontname=FONT, fontfile=_font_file())
    draw_duct_plan(page, segments, callouts, origin)
    doc.save(str(path))
    doc.close()


def draw_duct_plan(page, segments: list[DuctSegment], callouts: list[Callout] | None = None,
                   origin: tuple[float, float] = (60.0, 60.0)) -> None:
    """Draw ducts and callouts onto an existing page (font already inserted)."""
    ox, oy = origin

    for seg in segments:
        _draw_band(page, origin, seg, seg.width_mm / 2)
        if seg.insulated:
            _draw_band(page, origin, seg, seg.width_mm / 2 + seg.insulation_mm, width=0.4)
            ax, ay = ox + _to_points(seg.start[0]), oy + _to_points(seg.start[1])
            bx, by = ox + _to_points(seg.end[0]), oy + _to_points(seg.end[1])
            length = math.hypot(bx - ax, by - ay)
            ux, uy = (bx - ax) / length, (by - ay) / length
            nx, ny = -uy, ux
            half = seg.width_mm / 2 / MM_PER_PT_AT_1_100
            pitch = 8.0
            steps = int((length - 2 * half) // pitch)
            for i in range(steps):
                t = half + i * pitch
                grow = 1.0 + seg.hatch_jitter * (i % 5) / 4.0
                for direction in (1, -1):
                    sx = ax + ux * t - nx * half
                    sy = ay + uy * t - ny * half
                    ex = ax + ux * (t + direction * 2 * half * grow) + nx * half * grow
                    ey = ay + uy * (t + direction * 2 * half * grow) + ny * half * grow
                    page.draw_line((sx, sy), (ex, ey), color=seg.colour, width=0.4)
        if seg.axis:
            ax, ay = ox + _to_points(seg.start[0]), oy + _to_points(seg.start[1])
            bx, by = ox + _to_points(seg.end[0]), oy + _to_points(seg.end[1])
            total = math.hypot(bx - ax, by - ay)
            ux, uy = (bx - ax) / total, (by - ay) / total
            t = 0.0
            while t < total:
                for run in (9.0, 2.0):          # long dash, then a dot
                    end = min(t + run, total)
                    page.draw_line((ax + ux * t, ay + uy * t), (ax + ux * end, ay + uy * end),
                                   color=seg.colour, width=0.4)
                    t = end + 3.0

    for anchor, lines, target in callouts or []:
        tx, ty = anchor
        for i, line in enumerate(lines):
            page.insert_text((tx, ty + 11 * i), line, fontsize=9, fontname=FONT)
        rule_y = ty + 11 * (len(lines) - 1) + 3
        rule_x1 = tx + 70
        page.draw_line((tx - 2, rule_y), (rule_x1, rule_y), color=(0, 0, 0), width=0.5)
        page.draw_line((rule_x1, rule_y),
                       (ox + _to_points(target[0]), oy + _to_points(target[1])),
                       color=(0, 0, 0), width=0.5)


# --------------------------------------------------------------------------- #
# A small HVAC album: plan, schematic, specification - the sheet kinds the
# takeoff has to tell apart.
# --------------------------------------------------------------------------- #

# Column positions of the A3 specification form that dc_extraction reads.
SPEC_X_SYSTEM, SPEC_X_NAME, SPEC_X_UNIT, SPEC_X_QTY = 40.0, 110.0, 900.0, 950.0


@dataclass
class SpecDuct:
    system: str
    section: str     # e.g. "600x350"
    length_m: float


def make_album_pdf(path: str | Path, segments: list[DuctSegment],
                   callouts: list[Callout] | None = None,
                   spec: list[SpecDuct] | None = None) -> None:
    """Page 1 plan, page 2 schematic of the same ducts, page 3 specification."""
    doc = pymupdf.open()
    for title in ("План 1 этажа", "Схема систем П1, В1"):
        page = doc.new_page(width=1200, height=850)
        page.insert_font(fontname=FONT, fontfile=_font_file())
        draw_duct_plan(page, segments, callouts)
        page.insert_text((900, 820), title, fontsize=11, fontname=FONT)

    page = doc.new_page(width=1191, height=842)
    page.insert_font(fontname=FONT, fontfile=_font_file())
    page.insert_text((300, 40), "Спецификация оборудования, изделий и материалов",
                     fontsize=12, fontname=FONT)
    page.insert_text((SPEC_X_NAME, 70), "Наименование и техническая характеристика",
                     fontsize=8, fontname=FONT)
    y = 100.0
    current = None
    for row in spec or []:
        if row.system != current:
            page.insert_text((SPEC_X_SYSTEM, y), row.system, fontsize=9, fontname=FONT)
            current = row.system
            y += 16
        page.insert_text((SPEC_X_NAME, y), f"Воздуховод из оцинкованной стали {row.section}",
                         fontsize=9, fontname=FONT)
        page.insert_text((SPEC_X_UNIT, y), "м", fontsize=9, fontname=FONT)
        page.insert_text((SPEC_X_QTY, y), f"{row.length_m:g}".replace(".", ","),
                         fontsize=9, fontname=FONT)
        y += 16
    doc.save(str(path))
    doc.close()
