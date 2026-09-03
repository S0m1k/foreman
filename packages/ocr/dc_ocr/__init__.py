"""OCR adapters (PaddleOCR / Tesseract / none)."""

from .provider import (
    NullOCRProvider,
    OCRProvider,
    PaddleOCRProvider,
    TesseractOCRProvider,
    create_ocr_provider,
)

__all__ = [
    "NullOCRProvider",
    "OCRProvider",
    "PaddleOCRProvider",
    "TesseractOCRProvider",
    "create_ocr_provider",
]
