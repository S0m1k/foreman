"""Unit parsing and normalisation.

Values coming out of drawings and specifications are written in a mix of
Latin and Cyrillic notation (``m3/h`` vs ``м³/ч``).  Before any comparison can
happen every measurement is converted to one canonical unit per physical
dimension, so that ``15000 m3/h`` and ``15000 м³/ч`` compare equal while
``15 m`` and ``15 mm`` do not.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# --- dimensions ------------------------------------------------------------

LENGTH = "length"
AREA = "area"
VOLUME = "volume"
FLOW = "volumetric_flow"
MASS = "mass"
POWER = "power"
VOLTAGE = "voltage"
CURRENT = "current"
COUNT = "count"

CANONICAL_UNIT: dict[str, str] = {
    LENGTH: "m",
    AREA: "m2",
    VOLUME: "m3",
    FLOW: "m3/h",
    MASS: "kg",
    POWER: "kW",
    VOLTAGE: "V",
    CURRENT: "A",
    COUNT: "pcs",
}


@dataclass(frozen=True)
class UnitDef:
    """A unit alias: which dimension it belongs to and how to reach canonical."""

    dimension: str
    factor: float
    symbol: str  # display symbol in Latin notation


def _key(raw: str) -> str:
    """Fold a written unit into a lookup key.

    Superscripts, spaces, dots and case are irrelevant; ``М³/Ч``, ``m3 / h``
    and ``m3/h`` all collapse to ``m3/h``-shaped keys within their own script.
    """
    s = unicodedata.normalize("NFKC", raw or "").strip()
    s = s.replace("²", "2").replace("³", "3")
    s = s.replace("·", "*").replace("×", "*")
    s = re.sub(r"[\s  ]+", "", s)
    s = s.strip(".,;:")
    return s.lower()


def _defs() -> dict[str, UnitDef]:
    table: dict[str, UnitDef] = {}

    def add(aliases: list[str], dimension: str, factor: float, symbol: str) -> None:
        for alias in aliases:
            table[_key(alias)] = UnitDef(dimension, factor, symbol)

    # length -> m
    add(["mm", "мм"], LENGTH, 0.001, "mm")
    add(["cm", "см"], LENGTH, 0.01, "cm")
    add(["dm", "дм"], LENGTH, 0.1, "dm")
    add(["m", "м"], LENGTH, 1.0, "m")
    add(["km", "км"], LENGTH, 1000.0, "km")
    # area -> m2
    add(["mm2", "мм2"], AREA, 1e-6, "mm2")
    add(["cm2", "см2"], AREA, 1e-4, "cm2")
    add(["m2", "м2"], AREA, 1.0, "m2")
    # volume -> m3
    add(["mm3", "мм3"], VOLUME, 1e-9, "mm3")
    add(["cm3", "см3"], VOLUME, 1e-6, "cm3")
    add(["l", "л", "ltr", "liter", "litre"], VOLUME, 0.001, "l")
    add(["m3", "м3"], VOLUME, 1.0, "m3")
    # volumetric flow -> m3/h
    add(["m3/h", "м3/ч", "m3/hour", "куб.м/ч"], FLOW, 1.0, "m3/h")
    add(["l/s", "л/с"], FLOW, 3.6, "l/s")
    add(["l/min", "л/мин"], FLOW, 0.06, "l/min")
    add(["m3/s", "м3/с"], FLOW, 3600.0, "m3/s")
    # mass -> kg
    add(["g", "г"], MASS, 0.001, "g")
    add(["kg", "кг"], MASS, 1.0, "kg")
    add(["t", "т", "ton", "тонн"], MASS, 1000.0, "t")
    # power -> kW
    add(["w", "вт"], POWER, 0.001, "W")
    add(["kw", "квт"], POWER, 1.0, "kW")
    add(["mw", "мвт"], POWER, 1000.0, "MW")
    # voltage -> V
    add(["v", "в"], VOLTAGE, 1.0, "V")
    add(["kv", "кв"], VOLTAGE, 1000.0, "kV")
    # current -> A
    add(["a", "а"], CURRENT, 1.0, "A")
    add(["ma", "ма"], CURRENT, 0.001, "mA")
    # count -> pcs
    add(["pcs", "pc", "шт", "шт.", "ед", "ед.", "штук"], COUNT, 1.0, "pcs")
    return table


UNIT_DEFS: dict[str, UnitDef] = _defs()

# Longest-first so that "мм" wins over "м" when scanning free text.
UNIT_ALIASES_BY_LENGTH: list[str] = sorted(UNIT_DEFS, key=len, reverse=True)


def lookup(unit: str | None) -> UnitDef | None:
    """Resolve a written unit to its definition, or ``None`` if unknown."""
    if not unit:
        return None
    return UNIT_DEFS.get(_key(unit))


def canonicalize(
    value: float | None, unit: str | None
) -> tuple[float | None, str | None, str | None]:
    """Convert ``value``/``unit`` into ``(canonical_value, canonical_unit, dimension)``.

    Unknown units are passed through untouched rather than guessed at, so that
    a comparison can decide for itself whether it trusts them.
    """
    if value is None:
        return None, None, None
    definition = lookup(unit)
    if definition is None:
        return value, (unit or None), None
    return (
        value * definition.factor,
        CANONICAL_UNIT[definition.dimension],
        definition.dimension,
    )


def same_dimension(unit_a: str | None, unit_b: str | None) -> bool:
    """True when both units describe the same physical quantity."""
    a, b = lookup(unit_a), lookup(unit_b)
    if a is None or b is None:
        return _key(unit_a or "") == _key(unit_b or "")
    return a.dimension == b.dimension


# --- number parsing --------------------------------------------------------

_THOUSANDS_COMMA = re.compile(r"^\d{1,3}(,\d{3})+$")
_THOUSANDS_DOT = re.compile(r"^\d{1,3}(\.\d{3})+$")


def parse_number(text: str) -> float | None:
    """Parse a number written in Russian or English convention.

    ``15 000``, ``15,000`` and ``15000`` are all fifteen thousand, while
    ``15,5`` and ``15.5`` are both fifteen and a half.
    """
    if text is None:
        return None
    s = unicodedata.normalize("NFKC", str(text)).strip()
    s = re.sub(r"[\s  ']", "", s)
    s = s.replace("−", "-").replace("–", "-")
    if not s:
        return None
    negative = s.startswith("-")
    s = s.lstrip("+-")
    if not re.fullmatch(r"[\d.,]+", s):
        return None

    if "," in s and "." in s:
        # Whichever separator comes last is the decimal point.
        decimal_sep = "," if s.rfind(",") > s.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        s = s.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif _THOUSANDS_COMMA.fullmatch(s):
        s = s.replace(",", "")
    elif _THOUSANDS_DOT.fullmatch(s):
        s = s.replace(".", "")
    elif "," in s:
        s = s.replace(",", ".")

    if s.count(".") > 1:
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


# Units contain digits ("m3", "м²"), so the scanner matches against the known
# alias table instead of a generic character class.
_UNIT_ALTERNATION = "|".join(re.escape(a) for a in UNIT_ALIASES_BY_LENGTH)

# A space only groups thousands when it is followed by exactly three digits,
# otherwise "01 15000" would be read as a single number.
_NUMBER_PATTERN = (
    r"[-+]?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?"
    r"|[-+]?\d+(?:[.,]\d+)?"
)

_MEASUREMENT = re.compile(
    rf"(?P<number>{_NUMBER_PATTERN})\s*(?P<unit>{_UNIT_ALTERNATION})?(?![\w²³])",
    re.IGNORECASE | re.UNICODE,
)


@dataclass(frozen=True)
class Measurement:
    """A number plus optional unit, with the exact source span it came from."""

    value: float
    unit: str | None
    raw: str
    start: int
    end: int


def _normalize_for_scan(text: str) -> str:
    """NFKC plus superscript folding; what measurement spans refer to."""
    s = unicodedata.normalize("NFKC", text)
    return s.replace("²", "2").replace("³", "3")


def find_measurements(text: str) -> list[Measurement]:
    """Return every number/unit pair in ``text``, in order of appearance.

    Spans refer to the NFKC-normalised text, which is what callers should keep
    as evidence for the value.
    """
    if not text:
        return []
    normalized = _normalize_for_scan(text)
    found: list[Measurement] = []
    for match in _MEASUREMENT.finditer(normalized):
        value = parse_number(match.group("number"))
        if value is None:
            continue
        unit = match.group("unit")
        found.append(
            Measurement(
                value=value,
                unit=unit.strip() if unit else None,
                raw=match.group(0).strip(),
                start=match.start(),
                end=match.end(),
            )
        )
    return found


def parse_measurement(text: str) -> tuple[float | None, str | None]:
    """Pull ``(value, unit)`` out of a fragment such as ``15 000 м³/ч``."""
    found = find_measurements(text)
    if not found:
        return None, None
    return found[0].value, found[0].unit
