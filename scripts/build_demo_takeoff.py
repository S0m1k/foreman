"""Rebuild the /takeoff/demo data from a synthetic album (no customer data).

    .venv/Scripts/python scripts/build_demo_takeoff.py

Draws a one-plan album with its own specification sheet, runs the same album
takeoff the API runs, and writes the sheet in the API's response shape.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from dc_extraction.takeoff import run_album  # noqa: E402
from helpers.pdfgen import DuctSegment as S  # noqa: E402
from helpers.pdfgen import SpecDuct, make_album_pdf  # noqa: E402

WEB = ROOT / "apps" / "web"
RED, BLUE, GREEN = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.53, 0.0)

SEGMENTS = [
    S((0, 0), (12, 0), 600, RED, insulated=True),   # П1 main
    S((8, 0), (8, 5), 400, RED, insulated=True),    # П1 branch
    S((0, 9), (14, 9), 600, BLUE),                  # В1 main
    S((6, 9), (6, 14), 400, BLUE),                  # В1 branch
    S((16, 2), (16, 12), 800, GREEN),               # ДВ1
]
CALLOUTS = [
    ((140, 600), ["В1", "600x350"], (3.0, 9.0)),
    ((140, 640), ["В1", "400x200"], (6.0, 12.0)),
    ((140, 680), ["П1", "600x350"], (4.0, 0.0)),
    ((900, 600), ["ДВ1", "800x500"], (16.0, 7.0)),
]
SPEC = [
    SpecDuct("П1", "600x350", 12.0), SpecDuct("П1", "400x200", 4.0),
    SpecDuct("В1", "600x350", 14.0), SpecDuct("В1", "400x200", 5.5),
    SpecDuct("ДВ1", "800x500", 10.0),
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "demo_album_OV.pdf"
        make_album_pdf(path, SEGMENTS, CALLOUTS, SPEC)
        with pymupdf.open(path) as doc:
            album = run_album(doc).to_json()
            svg = doc[0].get_svg_image(text_as_path=False)

    plan = album["sheets"][0]
    sheet = {
        "takeoff_id": "demo",
        "document_id": "demo",
        "filename": "demo_album_OV.pdf",
        "page": plan["page"],
        "title": plan["title"],
        "scale": plan["scale"],
        "width": plan["width"],
        "height": plan["height"],
        "image_url": "/demo/sheet-1.svg",
        "runs": plan["runs"],
        "overrides": {},
        "spec_m": {name: entry["length_m"] for name, entry in album["spec"].items()},
        "other_sheets_m": {},
    }
    data = WEB / "src" / "data" / "demo-sheet.json"
    data.write_text(json.dumps(sheet, ensure_ascii=False, indent=1), encoding="utf-8")
    (WEB / "public" / "demo" / "sheet-1.svg").write_text(svg, encoding="utf-8")
    print(f"{data.relative_to(ROOT)}: {len(sheet['runs'])} runs, spec {sheet['spec_m']}")


if __name__ == "__main__":
    main()
