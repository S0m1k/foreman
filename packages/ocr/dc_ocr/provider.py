"""OCR adapters.

The pipeline talks to :class:`OCRProvider` only.  Concrete engines (PaddleOCR
preferred, Tesseract as fallback) are imported lazily so the application runs
on machines where neither is installed — scanned pages are then simply
reported as unreadable instead of crashing the analysis.
"""

from __future__ import annotations

import io
import logging
from typing import Protocol

from dc_schemas import ExtractionSource, TextBlock

logger = logging.getLogger(__name__)


class OCRProvider(Protocol):
    name: str

    def extract(self, image: bytes, dpi: int) -> list[TextBlock]:
        """OCR a rendered page image (PNG bytes).

        Returned bboxes are in PDF points (72 dpi), matching the text layer
        coordinates, so downstream code never cares where a block came from.
        """
        ...


def _to_points(coord: float, dpi: int) -> float:
    return coord * 72.0 / dpi


class NullOCRProvider:
    """Used when no OCR engine is available; extracts nothing."""

    name = "none"

    def extract(self, image: bytes, dpi: int) -> list[TextBlock]:  # noqa: ARG002
        return []


class PaddleOCRProvider:
    name = "paddle"

    def __init__(self, lang: str = "ru") -> None:
        from paddleocr import PaddleOCR  # lazy: heavy import

        self._engine = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)

    def extract(self, image: bytes, dpi: int) -> list[TextBlock]:
        import numpy as np
        from PIL import Image

        array = np.array(Image.open(io.BytesIO(image)).convert("RGB"))
        result = self._engine.ocr(array, cls=True)
        blocks: list[TextBlock] = []
        for line in result or []:
            for quad, (text, confidence) in line or []:
                xs = [point[0] for point in quad]
                ys = [point[1] for point in quad]
                blocks.append(
                    TextBlock(
                        text=text,
                        bbox=(
                            _to_points(min(xs), dpi),
                            _to_points(min(ys), dpi),
                            _to_points(max(xs), dpi),
                            _to_points(max(ys), dpi),
                        ),
                        confidence=float(confidence),
                        source=ExtractionSource.OCR,
                    )
                )
        return blocks


class TesseractOCRProvider:
    name = "tesseract"

    def __init__(self, lang: str = "rus+eng") -> None:
        import pytesseract  # lazy

        self._pytesseract = pytesseract
        self._lang = lang

    def extract(self, image: bytes, dpi: int) -> list[TextBlock]:
        from PIL import Image

        data = self._pytesseract.image_to_data(
            Image.open(io.BytesIO(image)),
            lang=self._lang,
            output_type=self._pytesseract.Output.DICT,
        )
        blocks: list[TextBlock] = []
        for i, text in enumerate(data["text"]):
            text = (text or "").strip()
            if not text:
                continue
            confidence = float(data["conf"][i])
            if confidence < 0:
                continue
            left, top = float(data["left"][i]), float(data["top"][i])
            width, height = float(data["width"][i]), float(data["height"][i])
            blocks.append(
                TextBlock(
                    text=text,
                    bbox=(
                        _to_points(left, dpi),
                        _to_points(top, dpi),
                        _to_points(left + width, dpi),
                        _to_points(top + height, dpi),
                    ),
                    confidence=confidence / 100.0,
                    source=ExtractionSource.OCR,
                )
            )
        return blocks


def create_ocr_provider(kind: str = "auto") -> OCRProvider:
    """Build the configured OCR provider, degrading gracefully.

    ``auto`` tries PaddleOCR, then Tesseract, then falls back to no-op.
    """
    candidates: list[str]
    if kind == "auto":
        candidates = ["paddle", "tesseract", "none"]
    else:
        candidates = [kind]
    for candidate in candidates:
        try:
            if candidate == "paddle":
                return PaddleOCRProvider()
            if candidate == "tesseract":
                return TesseractOCRProvider()
            if candidate == "none":
                return NullOCRProvider()
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.warning("OCR provider %s unavailable: %s", candidate, exc)
    logger.warning("No OCR engine available; scanned pages will not be read")
    return NullOCRProvider()
