"""PDF parsing, rendering and cropping.

A page comes back as :class:`dc_schemas.PageContent` with the extracted text
layer (when there is one) preserved block-by-block with coordinates.  Scanned
pages carry ``needs_ocr=True`` so the pipeline knows to run the OCR adapter.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf

from dc_schemas import BBox, ExtractionSource, PageContent, TextBlock

# Below this many characters per page we assume the text layer is unusable and
# the page is (mostly) a scan.
MIN_TEXT_CHARS_PER_PAGE = 32

DEFAULT_RENDER_DPI = 200
CROP_RENDER_DPI = 400
PDF_BASE_DPI = 72.0


def compute_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_text(text: str) -> str:
    """Fix common cmap quirks: soft hyphens for '-', nbsp variants for ' '."""
    return (
        (text or "")
        .replace("­", "-")
        .replace(" ", " ")
        .replace(" ", " ")
    )


def _page_blocks(page: pymupdf.Page) -> list[TextBlock]:
    """One TextBlock per rendered *line*.

    PyMuPDF's block-level grouping happily merges unrelated callouts that sit
    on the same baseline; lines are the atomic unit drawings actually use.
    """
    blocks: list[TextBlock] = []
    for raw_block in page.get_text("dict").get("blocks", []):
        for line in raw_block.get("lines", []):
            text = clean_text("".join(span.get("text", "") for span in line.get("spans", []))).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line.get("bbox", raw_block.get("bbox", (0, 0, 0, 0)))
            blocks.append(
                TextBlock(
                    text=text,
                    bbox=(float(x0), float(y0), float(x1), float(y1)),
                    confidence=1.0,
                    source=ExtractionSource.PDF_TEXT,
                )
            )
    return blocks


def needs_ocr(page_text: str, block_count: int) -> bool:
    """Heuristic: a vector page has a meaningful amount of extractable text."""
    return len((page_text or "").strip()) < MIN_TEXT_CHARS_PER_PAGE or block_count == 0


def parse_pdf(path: str | Path) -> list[PageContent]:
    """Extract text layer and geometry for every page of ``path``."""
    pages: list[PageContent] = []
    with pymupdf.open(path) as doc:
        for index, page in enumerate(doc):
            text = clean_text(page.get_text("text") or "")
            blocks = _page_blocks(page)
            pages.append(
                PageContent(
                    page_number=index + 1,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    text=text,
                    text_blocks=blocks,
                    needs_ocr=needs_ocr(text, len(blocks)),
                )
            )
    return pages


def render_page(path: str | Path, page_number: int, dpi: int = DEFAULT_RENDER_DPI) -> bytes:
    """Render one page (1-based) to PNG bytes."""
    with pymupdf.open(path) as doc:
        page = doc[page_number - 1]
        pixmap = page.get_pixmap(dpi=dpi)
        return pixmap.tobytes("png")


def crop_region(
    path: str | Path,
    page_number: int,
    bbox: BBox,
    dpi: int = CROP_RENDER_DPI,
    padding: float = 12.0,
) -> bytes:
    """Render a padded crop of ``bbox`` (PDF points) at high DPI to PNG bytes."""
    with pymupdf.open(path) as doc:
        page = doc[page_number - 1]
        x0, y0, x1, y1 = bbox
        clip = pymupdf.Rect(x0 - padding, y0 - padding, x1 + padding, y1 + padding)
        clip = clip & page.rect  # never leave the page
        if clip.is_empty:
            clip = page.rect
        pixmap = page.get_pixmap(dpi=dpi, clip=clip)
        return pixmap.tobytes("png")


def bbox_to_pixels(bbox: BBox, dpi: int) -> tuple[int, int, int, int]:
    """Convert a PDF-point bbox to pixel coordinates at ``dpi``."""
    scale = dpi / PDF_BASE_DPI
    x0, y0, x1, y1 = bbox
    return round(x0 * scale), round(y0 * scale), round(x1 * scale), round(y1 * scale)
