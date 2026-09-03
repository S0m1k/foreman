"""Conservative equipment-tag detection.

A tag is something like ``AHU-01``, ``V-17``, ``П-1``, ``ВК-3``, ``K-12a``.
The detector is deliberately strict — the MVP would rather miss a tag than
flood the user with false positives (norm references, paper sizes, pipe
diameters and sheet numbers all look tag-shaped).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from dc_schemas import units

# Letter prefixes that are *not* equipment tags.
_BLACKLIST_PREFIXES = {
    # norms / documents
    "ГОСТ", "СНИП", "СП", "СТО", "ТУ", "DIN", "EN", "ISO", "IEC", "ANSI",
    # sheet / page references (bare "P"/"Л" stay allowed: real tag prefixes)
    "ЛИСТ", "СТР", "PAGE", "PG", "РИС", "FIG",
    # pipe / electrical attributes
    "DN", "PN", "DU", "ДУ", "РУ", "IP", "PH", "RAL", "UN", "Ø",
}

# Single Latin/Cyrillic "A1".."A5" are almost always paper formats.
_PAPER_SIZE = re.compile(r"^[AА][0-5]$")

_TAG = re.compile(
    r"(?<![\w/№-])"
    r"(?P<letters>[A-ZА-ЯЁ]{1,4})"
    r"(?P<sep>[-–—.]| )?"
    r"(?P<digits>\d{1,3})"
    r"(?P<suffix>\.\d{1,2}|[a-zа-яё])?"
    r"(?!\w)",
    re.UNICODE,
)


@dataclass(frozen=True)
class TagHit:
    tag: str
    start: int
    end: int
    confidence: float


def _plausible(letters: str, sep: str | None, digits: str) -> float | None:
    """Return a confidence for the candidate, or None to reject it."""
    upper = letters.upper()
    if upper in _BLACKLIST_PREFIXES:
        return None
    if units.lookup(letters) is not None and (sep or "") in ("", " "):
        # "3 м2"-style fragments; unit-looking prefixes need a hyphen to count.
        return None
    if _PAPER_SIZE.match(upper + digits):
        return None
    if sep == " " and len(letters) < 2:
        # "В 3" is far more likely prose than a tag.
        return None
    if not sep and len(letters) == 1:
        # "П1" is a common vent tag but risky; keep at reduced confidence.
        return 0.7
    return 0.9 if sep != " " else 0.8


def find_tags(text: str) -> list[TagHit]:
    """Find equipment-tag candidates in free text, with source spans."""
    if not text:
        return []
    normalized = unicodedata.normalize("NFKC", text)
    hits: list[TagHit] = []
    for match in _TAG.finditer(normalized):
        letters = match.group("letters")
        sep = match.group("sep")
        digits = match.group("digits")
        confidence = _plausible(letters, sep, digits)
        if confidence is None:
            continue
        raw = match.group(0)
        # Canonical written form keeps the original characters but a single
        # hyphen as separator when the source used a space.
        tag = raw if sep != " " else f"{letters}-{digits}{match.group('suffix') or ''}"
        hits.append(TagHit(tag=tag.strip(), start=match.start(), end=match.end(), confidence=confidence))
    return hits
