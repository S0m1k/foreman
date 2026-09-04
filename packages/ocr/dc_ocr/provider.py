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


_TESSERACT_CANDIDATES = [
    "C:/Program Files/Tesseract-OCR/tesseract.exe",
    "C:/Program Files (x86)/Tesseract-OCR/tesseract.exe",
    "/usr/bin/tesseract",
]
_TESSDATA_CANDIDATES = [
    "D:/Foreman/storage/tessdata",
    "./storage/tessdata",
]


def _find_tesseract() -> str | None:
    import os
    import shutil
    from pathlib import Path

    for candidate in [os.environ.get("TESSERACT_CMD"), *_TESSERACT_CANDIDATES]:
        if candidate and Path(candidate).exists():
            return candidate
    return shutil.which("tesseract")


def _find_tessdata(binary: str, lang: str) -> str | None:
    """A tessdata dir containing every requested language, or None for default."""
    import os
    from pathlib import Path

    required = lang.split("+")
    default = Path(binary).parent / "tessdata"
    for candidate in [os.environ.get("TESSDATA_PREFIX"), str(default), *_TESSDATA_CANDIDATES]:
        if not candidate:
            continue
        directory = Path(candidate)
        if all((directory / f"{code}.traineddata").exists() for code in required):
            return str(directory)
    return None


class TesseractOCRProvider:
    name = "tesseract"

    def __init__(self, lang: str = "rus+eng") -> None:
        import pytesseract  # lazy

        binary = _find_tesseract()
        if binary is None:
            raise RuntimeError("tesseract executable not found")
        pytesseract.pytesseract.tesseract_cmd = binary
        self._pytesseract = pytesseract
        tessdata = _find_tessdata(binary, lang)
        if tessdata is None:
            logger.warning("no tessdata dir with %s found; falling back to eng", lang)
            lang = "eng"
            tessdata = _find_tessdata(binary, lang)
        self._lang = lang
        self._config = ""
        if tessdata:
            # env var instead of --tessdata-dir: config args break on quoted
            # Windows paths inside pytesseract
            import os

            os.environ["TESSDATA_PREFIX"] = tessdata
        # fail fast so create_ocr_provider("auto") can fall through
        pytesseract.get_tesseract_version()
        logger.info("tesseract ready: %s lang=%s tessdata=%s", binary, lang, tessdata)

    def extract(self, image: bytes, dpi: int) -> list[TextBlock]:
        from PIL import Image

        data = self._pytesseract.image_to_data(
            Image.open(io.BytesIO(image)),
            lang=self._lang,
            config=self._config,
            output_type=self._pytesseract.Output.DICT,
        )
        # Group word boxes into their printed line: tags and their values must
        # stay together ("15 000 м3/ч" is one measurement, not three words).
        lines: dict[tuple, dict] = {}
        for i, word in enumerate(data["text"]):
            word = (word or "").strip()
            confidence = float(data["conf"][i])
            if not word or confidence < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            left, top = float(data["left"][i]), float(data["top"][i])
            right, bottom = left + float(data["width"][i]), top + float(data["height"][i])
            line = lines.setdefault(
                key,
                {"words": [], "confs": [], "x0": left, "y0": top, "x1": right, "y1": bottom},
            )
            line["words"].append(word)
            line["confs"].append(confidence)
            line["x0"] = min(line["x0"], left)
            line["y0"] = min(line["y0"], top)
            line["x1"] = max(line["x1"], right)
            line["y1"] = max(line["y1"], bottom)

        blocks: list[TextBlock] = []
        for line in lines.values():
            blocks.append(
                TextBlock(
                    text=" ".join(line["words"]),
                    bbox=(
                        _to_points(line["x0"], dpi),
                        _to_points(line["y0"], dpi),
                        _to_points(line["x1"], dpi),
                        _to_points(line["y1"], dpi),
                    ),
                    confidence=min(line["confs"]) / 100.0,
                    source=ExtractionSource.OCR,
                )
            )
        blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
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
