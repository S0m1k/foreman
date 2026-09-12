"""Read the designer's own specification out of the same PDF.

The "Спецификация оборудования, изделий и материалов" sheets carry, as plain
extractable text, every duct of every system with its section and its length in
metres, plus the equipment attached to each system. That gives two things for
free: a reference takeoff produced by a different person, and a hard ceiling -
a system's length measured on one floor plan cannot exceed its length for the
whole building.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field

import pymupdf

DUCT_RE = re.compile(r"стали\s+([⌀øØФ]?\s?\d+(?:\s?[xх×]\s?\d+)?)", re.IGNORECASE)
SYSTEM_RE = re.compile(r"^(В|П|ДВ|ПД|ДП)\d+(\.\d+)?[аб]?$")
EQUIPMENT_RE = re.compile(
    r"(КЛАПЪ-\(\d+\)-Н[ОЗ]\(?C?\)?-\d+x\d+|АДР[ -][\dхx]+|АРН[ -][\dхx]+|АМР[ -][\dхx]+)"
)
QUANTITY_RE = re.compile(r"шт\.?\s+(\d+)")

# Column geometry of the standard A3 specification form (PDF points).
X_SYSTEM_MAX = 100.0
X_NAME = (105.0, 135.0)
X_UNIT = (890.0, 930.0)
ROW_TOL = 4.0


@dataclass
class SpecSystem:
    name: str
    length_m: float = 0.0
    sections: dict[str, float] = field(default_factory=dict)
    equipment: collections.Counter = field(default_factory=collections.Counter)

    @property
    def widths_mm(self) -> set[int]:
        out = set()
        for section in self.sections:
            match = re.match(r"^Ø(\d+)$", section) or re.match(r"^(\d+)x", section)
            if match:
                out.add(int(match.group(1)))
        return out


def normalise_size(text: str) -> str:
    text = text.replace(" ", "").replace("х", "x").replace("×", "x")
    for char in "øØФф⌀":
        text = text.replace(char, "Ø")
    return text


def _rows(page: pymupdf.Page):
    lines: dict[int, list] = collections.defaultdict(list)
    for word in page.get_text("words"):
        lines[round(word[1] / ROW_TOL)].append(word)
    for key in sorted(lines):
        words = sorted(lines[key], key=lambda w: w[0])
        text = " ".join(w[4] for w in words)
        system = None
        for word in words:
            if word[0] < X_SYSTEM_MAX and SYSTEM_RE.match(word[4]):
                system = word[4]
        is_duct = any(X_NAME[0] <= w[0] <= X_NAME[1] and w[4].startswith("Воздуховод")
                      for w in words)
        quantity = None
        if is_duct:
            unit_at = next((i for i, w in enumerate(words)
                            if X_UNIT[0] <= w[0] <= X_UNIT[1] and w[4] == "м"), None)
            if unit_at is not None:
                for word in words[unit_at + 1:]:
                    try:
                        quantity = float(word[4].replace(",", "."))
                        break
                    except ValueError:
                        continue
        yield system, text, is_duct, quantity


def parse_specification(doc: pymupdf.Document) -> dict[str, SpecSystem]:
    """Return system name -> sections, lengths and equipment."""
    systems: dict[str, SpecSystem] = {}
    current: str | None = None
    for page in doc:
        text = page.get_text()
        if "Воздуховод" not in text and "Спецификация" not in text:
            continue
        for system, row, is_duct, quantity in _rows(page):
            if system:
                current = system
            if current is None:
                continue
            entry = systems.setdefault(current, SpecSystem(current))
            if is_duct and quantity is not None:
                match = DUCT_RE.search(row)
                if match:
                    size = normalise_size(match.group(1))
                    entry.sections[size] = entry.sections.get(size, 0.0) + quantity
                    entry.length_m += quantity
                continue
            mark = EQUIPMENT_RE.search(row)
            if mark:
                count = QUANTITY_RE.search(row)
                entry.equipment[mark.group(1)] += int(count.group(1)) if count else 1
    return systems


def unique_equipment(systems: dict[str, SpecSystem], scope: set[str] | None = None
                     ) -> dict[str, str]:
    """Equipment marks that belong to exactly one system in `scope`.

    Those are attribution anchors: a fire damper called out on the plan pins the
    duct it sits on to a single system.
    """
    owners: dict[str, set[str]] = collections.defaultdict(set)
    for name, entry in systems.items():
        if scope is not None and name not in scope:
            continue
        for mark in entry.equipment:
            owners[mark].add(name)
    return {mark: next(iter(names)) for mark, names in owners.items() if len(names) == 1}
