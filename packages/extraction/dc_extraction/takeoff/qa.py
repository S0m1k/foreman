"""Visual QA: draw what was measured back onto the sheet.

Every metre in the takeoff belongs to a centreline that can be looked at, which
is the whole point of measuring instead of estimating. A reviewer opens the
overlay, sees a magenta line down the middle of each duct, and spots anything
the pipeline invented or missed.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from .geometry import DuctRun

# Chosen to stay readable over the drawing's own red/blue/green/orange ducts.
CONFIDENCE_COLOUR = {
    "callout": (0, 160, 60),       # pinned by a callout or a system-unique damper
    "fingerprint": (255, 0, 255),  # placed by section fingerprint under budget
    "none": (0, 0, 0),             # measured but not attributed to a system
}


def overlay(page: pymupdf.Page, runs: list[DuctRun], out_path: str | Path,
            clip: tuple[float, float, float, float] | None = None, dpi: int = 200,
            confidence: list[str] | None = None, width_mm: float | None = None) -> Path:
    """Render `page` (optionally cropped) with measured centrelines on top."""
    from PIL import Image, ImageDraw

    rect = pymupdf.Rect(*clip) if clip else page.rect
    pix = page.get_pixmap(clip=rect, dpi=int(dpi))
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    draw = ImageDraw.Draw(image)
    k = dpi / 72.0
    for index, run in enumerate(runs):
        if width_mm is not None and abs(run.width_mm - width_mm) > 30:
            continue
        colour = CONFIDENCE_COLOUR["none"]
        if confidence is not None and index < len(confidence):
            colour = CONFIDENCE_COLOUR.get(confidence[index], colour)
        draw.line(
            [((run.p0[0] - rect.x0) * k, (run.p0[1] - rect.y0) * k),
             ((run.p1[0] - rect.x0) * k, (run.p1[1] - rect.y0) * k)],
            fill=colour, width=max(1, int(k * 1.3)),
        )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    return out_path
