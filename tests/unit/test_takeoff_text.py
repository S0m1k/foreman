"""Shifted Cyrillic in PDF text.

AutoCAD exports some fonts without a ToUnicode map, so a text layer that
reads "План системы отопления" on paper extracts as "ǚǶǫǸǼǳǼǽǰǷȆ..." - each
Cyrillic letter moved by a constant offset that differs per font (seen:
+0x245, +0x247, +0x1D6), with spaces turning into control or Latin-1
characters. On 4 of 18 corpus projects every title, callout and
specification line read this way, so no sheet was recognised at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dc_extraction.takeoff import classify_sheet, leaders  # noqa: E402
from dc_extraction.takeoff.text import page_words, repair_text  # noqa: E402
from helpers.pdfgen import FONT, DuctSegment, _font_file, draw_duct_plan  # noqa: E402


def shifted(text: str, offset: int, space: str = "\x01") -> str:
    """Encode Cyrillic letters the way a broken font extracts them."""
    return "".join(chr(ord(c) - offset) if "Ѐ" <= c <= "ӿ" else space if c == " " else c
                   for c in text)


@pytest.mark.parametrize("raw, expected", [
    # verbatim from corpus sheets, three different fonts
    ("ǚǶǫǸ\x01ǼǳǼǽǰǷȆ\x01ǹǽǹǺǶǰǸǳȊ", "План системы отопления"),
    ("ǘǴǩǶÚǸǮǹǫǷǬǷÚȆǻǩǯǩ", "План первого этажа"),
    ("ɇɚɢɦɟɧɨɜɚɧɢɟ", "Наименование"),
])
def test_shifted_cyrillic_is_restored(raw, expected):
    assert repair_text(raw) == expected


@pytest.mark.parametrize("text", [
    "План 1 этажа, Ø200, 400x200",
    "dy25 -3,600 20-2020",
    "Δp = 120 Па, λ = 0,04",  # genuine Greek next to genuine Cyrillic
])
def test_healthy_text_is_left_alone(text):
    assert repair_text(text) == text


def test_two_fonts_on_one_page_are_each_restored():
    text = shifted("Спецификация оборудования изделий и материалов", 0x245) + "\n" + \
        shifted("Наименование и техническая характеристика", 0x1D6)
    assert repair_text(text) == ("Спецификация оборудования изделий и материалов\n"
                                 "Наименование и техническая характеристика")


def _page(tmp_path, lines, segments=None, callouts=None):
    doc = pymupdf.open()
    page = doc.new_page(width=1200, height=850)
    page.insert_font(fontname=FONT, fontfile=_font_file())
    if segments:
        draw_duct_plan(page, segments, callouts)
    for i, line in enumerate(lines):
        page.insert_text((700, 760 + 16 * i), line, fontsize=10, fontname=FONT)
    path = tmp_path / "sheet.pdf"
    doc.save(path)
    return pymupdf.open(path)[0]


def test_sheet_with_a_shifted_title_block_is_recognised(tmp_path):
    page = _page(tmp_path, [shifted("План системы отопления на отм. -3,600", 0x245),
                            shifted("Строительство спортивного комплекса", 0x245)])
    sheet = classify_sheet(page)
    assert (sheet.kind, sheet.title) == ("plan", "План системы отопления на отм. -3,600")


def test_shifted_callouts_resolve_to_systems(tmp_path):
    """The title gives the page enough letters to pin the font's offset; a
    two-character callout like "П1" could not do that on its own."""
    red = (1.0, 0.0, 0.0)
    page = _page(
        tmp_path,
        [shifted("План первого этажа вентиляция", 0x245)],
        segments=[DuctSegment((0, 0), (10, 0), 600, red)],
        callouts=[((500.0, 300.0), [shifted("П1", 0x245), "600x350"], (5.0, 0.0))],
    )
    found = {(kind, text) for kind, text, _, _ in leaders(page)}
    assert ("system", "П1") in found
    assert ("size", "600x350") in found


def test_words_split_where_a_shifted_space_was(tmp_path):
    page = _page(tmp_path, [shifted("План системы отопления", 0x245)])
    texts = [w[4] for w in page_words(page)]
    assert texts == ["План", "системы", "отопления"]
