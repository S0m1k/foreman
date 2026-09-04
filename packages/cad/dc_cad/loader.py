"""DXF loading: render to PDF + extract text with PDF-space coordinates.

The rendered PDF carries no text layer (ezdxf draws glyphs as outlines), so
text is taken straight from the CAD entities — TEXT, MTEXT and block-attribute
values — and its coordinates are mapped into the produced PDF's point space.
That keeps every downstream step (extraction, evidence bboxes, crops)
identical to the plain-PDF path, with *exact* text instead of OCR.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import ezdxf
import matplotlib

matplotlib.use("Agg")

from dc_pdf import clean_text  # noqa: E402
from dc_schemas import ExtractionSource, PageContent, TextBlock  # noqa: E402
from ezdxf import bbox as ezdxf_bbox  # noqa: E402
from ezdxf.addons.drawing import Frontend, RenderContext  # noqa: E402
from ezdxf.addons.drawing.config import (  # noqa: E402
    BackgroundPolicy,
    ColorPolicy,
    Configuration,
)
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend  # noqa: E402
from matplotlib import pyplot as plt  # noqa: E402

logger = logging.getLogger(__name__)

CAD_EXTENSIONS = {".dwg", ".dxf"}

# Rendered sheet size: fit the drawing into ~A3 landscape at 72 pt/inch.
MAX_PAGE_PT = 1190.0
MIN_PAGE_PT = 300.0
PAGE_MARGIN_FRACTION = 0.02

# Rough glyph aspect used to estimate text widths (CAD text is monospacedish).
# Slightly generous: an over-wide evidence bbox is harmless, a clipped tag is not.
GLYPH_WIDTH_FACTOR = 0.8


def is_cad_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in CAD_EXTENSIONS


@dataclass(frozen=True)
class _Transform:
    """Drawing units -> PDF points (PyMuPDF convention: origin top-left, y down)."""

    min_x: float
    min_y: float
    scale: float
    page_height: float

    def point(self, x: float, y: float) -> tuple[float, float]:
        return (
            (x - self.min_x) * self.scale,
            self.page_height - (y - self.min_y) * self.scale,
        )

    def rect(self, x0: float, y0: float, x1: float, y1: float):
        ax, ay = self.point(x0, y0)
        bx, by = self.point(x1, y1)
        return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))


MAX_BLOCK_DEPTH = 4  # nested INSERTs deeper than this are decoration, not data


def _text_entities(msp) -> list[tuple[str, float, float, float]]:
    """Yield (text, x, y, height) for every textual entity in model space.

    Block references are exploded recursively (``virtual_entities``) because
    real drawings keep most of their labels *inside* blocks — equipment
    callouts, system tags, leader notes — not as top-level TEXT.
    """
    found: list[tuple[str, float, float, float]] = []

    def add(text: str, insert, height: float) -> None:
        text = clean_text(str(text)).strip()
        if not text or insert is None:
            return
        found.append((text, float(insert[0]), float(insert[1]), float(height or 2.5)))

    def walk(entities, depth: int) -> None:
        for entity in entities:
            kind = entity.dxftype()
            try:
                if kind == "TEXT" or kind == "ATTRIB":
                    add(entity.dxf.text, entity.dxf.insert, entity.dxf.height)
                elif kind == "MTEXT":
                    add(entity.plain_text(), entity.dxf.insert, entity.dxf.char_height)
                elif kind == "INSERT":
                    for attrib in entity.attribs:
                        add(attrib.dxf.text, attrib.dxf.insert, attrib.dxf.height)
                    if depth < MAX_BLOCK_DEPTH:
                        # virtual_entities yields the block content transformed
                        # into world coordinates of this reference
                        walk(entity.virtual_entities(), depth + 1)
                elif kind == "DIMENSION" and depth < MAX_BLOCK_DEPTH:
                    walk(entity.virtual_entities(), depth + 1)
            except Exception as exc:  # entity-level corruption must not kill the page
                logger.warning("skipping unreadable %s entity: %s", kind, exc)

    walk(msp, 0)
    return found


def _extents(doc, msp):
    cache = ezdxf_bbox.Cache()
    extents = ezdxf_bbox.extents(msp, cache=cache)
    if not extents.has_data:
        raise ValueError("the CAD file contains no drawable entities")
    return extents


def cad_to_pdf(dxf_path: str | Path, pdf_out: str | Path) -> PageContent:
    """Render a DXF's model space to a one-page PDF and return its content.

    The returned :class:`PageContent` has ``text_blocks`` in the coordinate
    system of the produced PDF, exactly like ``dc_pdf.parse_pdf`` would give.
    """
    dxf_path = Path(dxf_path)
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    extents = _extents(doc, msp)

    span_x = max(extents.size.x, 1e-6)
    span_y = max(extents.size.y, 1e-6)
    margin = max(span_x, span_y) * PAGE_MARGIN_FRACTION
    min_x, min_y = extents.extmin.x - margin, extents.extmin.y - margin
    span_x += 2 * margin
    span_y += 2 * margin

    scale = MAX_PAGE_PT / max(span_x, span_y)
    page_width = max(MIN_PAGE_PT, span_x * scale)
    page_height = max(MIN_PAGE_PT, span_y * scale)
    transform = _Transform(min_x=min_x, min_y=min_y, scale=scale, page_height=page_height)

    figure = plt.figure(figsize=(page_width / 72.0, page_height / 72.0))
    ax = figure.add_axes([0, 0, 1, 1])
    ax.set_xlim(min_x, min_x + span_x)
    ax.set_ylim(min_y, min_y + span_y)
    ax.set_axis_off()
    try:
        context = RenderContext(doc)
        # CAD color 7 means "white on dark"; on paper it must become black.
        config = Configuration(
            background_policy=BackgroundPolicy.WHITE,
            color_policy=ColorPolicy.BLACK,
        )
        Frontend(context, MatplotlibBackend(ax, adjust_figure=False), config=config).draw_layout(
            msp, finalize=True
        )
        # draw_layout may re-fit limits; force ours back so the transform holds
        ax.set_xlim(min_x, min_x + span_x)
        ax.set_ylim(min_y, min_y + span_y)
        figure.savefig(str(pdf_out), format="pdf", facecolor="white")
    finally:
        plt.close(figure)

    blocks: list[TextBlock] = []
    for text, x, y, height in _text_entities(msp):
        width_units = max(len(text), 1) * height * GLYPH_WIDTH_FACTOR
        bbox = transform.rect(x, y, x + width_units, y + height)
        blocks.append(
            TextBlock(
                text=text,
                bbox=bbox,
                confidence=1.0,
                source=ExtractionSource.PDF_TEXT,
            )
        )
    blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))

    if not blocks:
        logger.warning("CAD file %s contains no text entities", dxf_path.name)

    return PageContent(
        page_number=1,
        width=math.ceil(page_width),
        height=math.ceil(page_height),
        text="\n".join(b.text for b in blocks),
        text_blocks=blocks,
        needs_ocr=False,
    )


def load_cad_document(
    path: str | Path, pdf_out: str | Path, oda_converter_path: str | None = None
) -> PageContent:
    """DWG or DXF in, rendered PDF + page content out."""
    path = Path(path)
    if path.suffix.lower() == ".dwg":
        from .convert import convert_dwg_to_dxf

        path = convert_dwg_to_dxf(path, oda_converter_path)
    return cad_to_pdf(path, pdf_out)
