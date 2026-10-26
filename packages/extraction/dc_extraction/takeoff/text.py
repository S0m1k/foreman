"""Read PDF text through a repair for shifted Cyrillic.

AutoCAD exports some fonts without a ToUnicode map. Their glyphs keep the
font's internal order, so every Cyrillic letter extracts moved by one
constant offset - "План" becomes "ǚǶǫǸ" - and the offset differs per font
(+0x245, +0x247 and +0x1D6 in the corpus). Spaces come out as control or
Latin-1 characters, which also glues whole lines into one "word".

The offset is found per page, not per word: a two-letter callout like "П1"
fits many offsets, but a page of titles and notes fits only the real one.
Each candidate offset is scored by how well the letters it produces match
Russian letter frequencies; a second font on the same page gets its own
offset from whatever letters the first one did not explain.
"""

from __future__ import annotations

import math
import re

import pymupdf

# Russian letter frequencies, % - enough to tell a real offset from a wrong one.
_FREQ = dict(zip("оеаинтсрвлкмдпуяыьгзбчйхжшюцщэфъё", (
    10.97, 8.45, 8.01, 7.35, 6.70, 6.26, 5.47, 4.73, 4.54, 4.40, 3.49, 3.21, 2.98, 2.81,
    2.62, 2.01, 1.90, 1.74, 1.70, 1.65, 1.59, 1.44, 1.21, 0.97, 0.94, 0.73, 0.64, 0.48,
    0.36, 0.32, 0.26, 0.04, 0.04), strict=True))
_RARE = 0.02  # other Cyrillic - Kazakh letters, Ѐ..ӿ outside the Russian alphabet

# Characters a broken font produces for letters, and for everything else.
_SUSPECT = (0x0100, 0x03FF)
_CYRILLIC = (0x0400, 0x04FF)
_JUNK = re.compile(r"[\x00-\x08\x0e-\x1f\x80-\xff]")
SOFT_HYPHEN = "\u00ad"  # these exports use it for a plain hyphen

MIN_SUSPECT = 8          # fewer shifted-looking letters than this: leave the page alone
MIN_COVERAGE = 0.6       # share of a token's suspect letters an offset must turn Cyrillic
MIN_MEAN_LOG = math.log(1.2)  # mean log-frequency of a real offset's letters
MAX_FONTS = 3


def _is_suspect(ch: str) -> bool:
    return _SUSPECT[0] <= ord(ch) <= _SUSPECT[1]


def _log_freq(code: int) -> float | None:
    if not _CYRILLIC[0] <= code <= _CYRILLIC[1]:
        return None
    return math.log(_FREQ.get(chr(code).lower(), _RARE))


def detect_shifts(text: str) -> list[int]:
    """Offsets that turn this text's shifted letters into plausible Russian."""
    remaining = [ord(c) for c in text if _is_suspect(c)]
    shifts: list[int] = []
    while len(remaining) >= MIN_SUSPECT and len(shifts) < MAX_FONTS:
        lo, hi = min(remaining), max(remaining)
        best, best_score = None, -math.inf
        for shift in range(_CYRILLIC[0] - hi, _CYRILLIC[1] - lo + 1):
            logs = [lf for c in remaining if (lf := _log_freq(c + shift)) is not None]
            if len(logs) < MIN_SUSPECT:
                continue
            # reward explaining many letters with common ones
            score = sum(logs) + 2.0 * len(logs)
            if score > best_score:
                best, best_score = shift, score
        if best is None:
            break
        explained = [c for c in remaining if _log_freq(c + best) is not None]
        if sum(_log_freq(c + best) for c in explained) / len(explained) < MIN_MEAN_LOG:
            break
        shifts.append(best)
        remaining = [c for c in remaining if _log_freq(c + best) is None]
    return shifts


def _repair_token(token: str, shifts: list[int]) -> str:
    suspects = [ord(c) for c in token if _is_suspect(c)]
    if not suspects or not shifts:
        return token

    def fit(shift: int) -> tuple[float, float]:
        logs = [lf for c in suspects if (lf := _log_freq(c + shift)) is not None]
        return len(logs) / len(suspects), sum(logs)

    shift = max(shifts, key=fit)
    if fit(shift)[0] < MIN_COVERAGE:
        return token
    out = []
    for ch in token:
        if _is_suspect(ch):
            code = ord(ch) + shift
            out.append(chr(code) if _CYRILLIC[0] <= code <= _CYRILLIC[1] else " ")
        else:
            out.append("-" if ch == SOFT_HYPHEN else " " if _JUNK.match(ch) else ch)
    return re.sub(" +", " ", "".join(out)).strip()


def repair(text: str, shifts: list[int]) -> str:
    if not shifts:
        return text
    return re.sub(r"[^\s]+", lambda m: _repair_token(m.group(0), shifts), text)


def repair_text(text: str) -> str:
    return repair(text, detect_shifts(text))


def page_text(page: pymupdf.Page) -> str:
    return repair_text(page.get_text())


def page_words(page: pymupdf.Page) -> list[tuple]:
    """`page.get_text("words")`, repaired; a restored space splits the word,
    sharing its box between the parts by character count."""
    words = page.get_text("words")
    shifts = detect_shifts(" ".join(w[4] for w in words))
    if not shifts:
        return words
    out: list[tuple] = []
    for x0, y0, x1, y1, text, *rest in words:
        fixed = _repair_token(text, shifts)
        parts = fixed.split(" ")
        if len(parts) == 1:
            out.append((x0, y0, x1, y1, fixed, *rest))
            continue
        total = max(1, len(fixed))
        cursor = 0
        for part in parts:
            a = x0 + (x1 - x0) * cursor / total
            b = x0 + (x1 - x0) * (cursor + len(part)) / total
            out.append((a, y0, b, y1, part, *rest))
            cursor += len(part) + 1
    return out
