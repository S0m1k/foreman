"""Tag normalisation, including OCR-error tolerance.

``AHU 01``, ``AHU-01`` and ``ahu-01`` are the same tag.  A separate, more
aggressive folding maps common OCR confusions (``O``/``0``, Cyrillic/Latin
lookalikes) so that near-identical tags can still be matched — but only at a
lower confidence level, never silently.
"""

from __future__ import annotations

import re
import unicodedata

_SEPARATORS = re.compile(r"[\s\-–—_./\\]+")

# Cyrillic -> Latin lookalike folding (uppercase). Applied only for the fuzzy
# comparison key, never for display.
_HOMOGLYPHS = str.maketrans(
    {
        "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
        "О": "O", "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X",
    }
)

# Digit/letter OCR confusions, applied to the letter part vs digit part safely:
# we fold both ways into a single canonical symbol.
_OCR_FOLD = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "З": "3"})


def normalize_tag(tag: str) -> str:
    """Case/separator-insensitive form of a tag: ``AHU 01`` -> ``AHU01``."""
    s = unicodedata.normalize("NFKC", tag or "").strip()
    s = _SEPARATORS.sub("", s)
    return s.upper()


def strip_leading_zeros(tag_norm: str) -> str:
    """``AHU01`` -> ``AHU1`` so zero-padding differences do not split objects."""
    return re.sub(r"(?<=\D)0+(?=\d)", "", tag_norm)


def fuzzy_key(tag: str) -> str:
    """Aggressive folding for OCR-tolerant comparison (never for display)."""
    s = strip_leading_zeros(normalize_tag(tag))
    s = s.translate(_HOMOGLYPHS)
    s = s.translate(_OCR_FOLD)
    return s
