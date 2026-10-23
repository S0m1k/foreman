"""Which sheets of an HVAC album to measure.

Running the duct measurement over every page is wrong, not just slow: on the
benchmark album the system schematics (sheets 12-19) are drawn in the same
colours as the plans and "measure" 800-1100 m each. The title block says what
a sheet is, so that is what decides.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dc_extraction.takeoff import classify_sheet  # noqa: E402
from helpers.pdfgen import FONT, _font_file  # noqa: E402


def sheet(tmp_path: Path, lines: list[str]) -> pymupdf.Page:
    doc = pymupdf.open()
    page = doc.new_page(width=1190, height=842)
    page.insert_font(fontname=FONT, fontfile=_font_file())
    for i, line in enumerate(lines):
        page.insert_text((40, 60 + 18 * i), line, fontsize=10, fontname=FONT)
    path = tmp_path / "sheet.pdf"
    doc.save(path)
    return pymupdf.open(path)[0]


@pytest.mark.parametrize("lines, kind, title", [
    (["Изм. Кол.уч. Лист", "План паркинга в осях 3/1-21/1 и Вс8-Кс6"],
     "plan", "План паркинга в осях 3/1-21/1 и Вс8-Кс6"),
    (["План 1 этажа"], "plan", "План 1 этажа"),
    (["Схема систем В1,В2,В4,В5"], "schematic", "Схема систем В1,В2,В4,В5"),
    (["Спецификация оборудования, изделий и материалов"],
     "specification", "Спецификация оборудования, изделий и материалов"),
    (["П1", "VKC-VP-S-10", "АИР 100 S4"], "other", None),
])
def test_title_block_decides_the_kind(tmp_path, lines, kind, title):
    result = classify_sheet(sheet(tmp_path, lines))
    assert (result.kind, result.title) == (kind, title)


def test_specification_continuation_without_a_title_is_still_a_specification(tmp_path):
    """Continuation sheets carry only the form's column header, no title."""
    page = sheet(tmp_path, ["Поз.", "Наименование и техническая характеристика",
                            "Воздуховод из оцинкованной стали 400x200", "м", "12,5"])
    assert classify_sheet(page).kind == "specification"


def test_schematic_mentioning_ducts_in_its_notes_is_not_a_specification(tmp_path):
    page = sheet(tmp_path, ["Схема систем ДВ1а-ДВ3а", "Воздуховоды выполнить из стали"])
    assert classify_sheet(page).kind == "schematic"


def test_sheet_list_naming_many_plans_is_not_a_plan(tmp_path):
    """The general-data sheet lists every drawing in the album."""
    page = sheet(tmp_path, ["Общие данные", "Ведомость рабочих чертежей",
                            "План паркинга", "План 1 этажа", "План 2 этажа",
                            "Схема систем В1"])
    assert classify_sheet(page).kind == "other"
