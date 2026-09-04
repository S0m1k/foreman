"""PDF parsing and rendering built on PyMuPDF."""

from .processor import (
    clean_text,
    compute_sha256,
    crop_region,
    needs_ocr,
    parse_pdf,
    render_page,
    render_page_capped,
)

__all__ = ["clean_text", "compute_sha256", "crop_region", "needs_ocr", "parse_pdf", "render_page"]
