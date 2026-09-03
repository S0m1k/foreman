"""Deterministic, grounded entity extraction from a drawing page.

Works purely on the text blocks (vector text layer or OCR output): finds tags,
then attaches measurements written in the same block or in blocks immediately
around it.  Everything produced here is grounded by construction — every value
comes with the exact source substring and the block bbox.
"""

from __future__ import annotations

import re

from dc_schemas import (
    BBox,
    Entity,
    ExtractionSource,
    PageContent,
    Quantity,
    TextBlock,
    units,
)

from .tags import find_tags

# A tag inside a sheet caption ("PLAN OV-05", "ЛИСТ 3 — СХЕМА ОВ") names the
# document, not a piece of equipment.
_CAPTION_WORDS = re.compile(
    r"\b(план|лист|схема|чертеж|чертёж|стадия|раздел|plan|sheet|layout|drawing|scheme|title)\b",
    re.IGNORECASE,
)

# How far below/right of a tag block another block may sit and still be
# considered "about" the same object (PDF points).
NEARBY_VERTICAL_GAP = 40.0
NEARBY_HORIZONTAL_OVERLAP_MIN = 0.3

# dimension -> default parameter name
DIMENSION_PARAM = {
    units.FLOW: "airflow",
    units.POWER: "power",
    units.VOLTAGE: "voltage",
    units.CURRENT: "current",
    units.MASS: "mass",
    units.LENGTH: "length",
    units.AREA: "area",
    units.VOLUME: "volume",
}

_TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("приточ", "air_handling_unit"),
    ("вентустановк", "air_handling_unit"),
    ("air handling", "air_handling_unit"),
    ("ahu", "air_handling_unit"),
    ("вентилятор", "fan"),
    ("fan", "fan"),
    ("насос", "pump"),
    ("pump", "pump"),
    ("клапан", "valve"),
    ("valve", "valve"),
    ("радиатор", "radiator"),
    ("radiator", "radiator"),
    ("конвектор", "convector"),
    ("бак", "tank"),
    ("емкост", "tank"),
    ("ёмкост", "tank"),
    ("tank", "tank"),
    ("щит", "panel"),
    ("panel", "panel"),
]


def guess_type(text: str) -> str | None:
    lowered = (text or "").lower()
    for keyword, type_name in _TYPE_KEYWORDS:
        if keyword in lowered:
            return type_name
    return None


def _x_overlap(a: BBox, b: BBox) -> float:
    left = max(a[0], b[0])
    right = min(a[2], b[2])
    if right <= left:
        return 0.0
    return (right - left) / max(1.0, min(a[2] - a[0], b[2] - b[0]))


def _is_nearby(anchor: BBox, other: BBox) -> bool:
    """True when ``other`` sits under/next to ``anchor`` closely enough."""
    vertical_gap = other[1] - anchor[3]
    if 0 <= vertical_gap <= NEARBY_VERTICAL_GAP:
        return _x_overlap(anchor, other) >= NEARBY_HORIZONTAL_OVERLAP_MIN
    return False


_QTY_PATTERN = re.compile(
    r"(\d+)\s*(?:шт\.?|штук|pcs|pc)(?!\w)", re.IGNORECASE | re.UNICODE
)


def _extract_quantity(text: str) -> Quantity | None:
    match = _QTY_PATTERN.search(text or "")
    if not match:
        return None
    return Quantity.of(float(match.group(1)), "pcs", raw=match.group(0))


def _extract_parameters(text: str) -> dict[str, Quantity]:
    """Measurements in ``text`` keyed by parameter name; first value wins."""
    parameters: dict[str, Quantity] = {}
    for measurement in units.find_measurements(text):
        if measurement.unit is None:
            continue  # a bare number in free text is not evidence of anything
        definition = units.lookup(measurement.unit)
        if definition is None or definition.dimension == units.COUNT:
            continue
        name = DIMENSION_PARAM.get(definition.dimension)
        if name and name not in parameters:
            parameters[name] = Quantity.of(measurement.value, measurement.unit, raw=measurement.raw)
    return parameters


def extract_drawing_entities(page: PageContent, document_id: str) -> list[Entity]:
    """Rule-based extraction of tagged entities from one drawing page."""
    entities: dict[str, Entity] = {}
    blocks = page.text_blocks
    for block in blocks:
        if _CAPTION_WORDS.search(block.text):
            continue
        for hit in find_tags(block.text):
            context_blocks: list[TextBlock] = [block] + [
                other for other in blocks if other is not block and _is_nearby(block.bbox, other.bbox)
            ]
            # Text after the tag inside its own line carries the strongest
            # signal; text *before* the tag belongs to whatever came earlier
            # and must never be attributed to this entity.
            own_tail = block.text[hit.end :] if hit.end <= len(block.text) else ""
            context_text = "\n".join([own_tail] + [b.text for b in context_blocks[1:]])
            parameters = _extract_parameters(own_tail) or _extract_parameters(context_text)
            quantity = _extract_quantity(own_tail) or _extract_quantity(context_text)
            display_context = "\n".join(b.text for b in context_blocks)
            confidence = min(hit.confidence, block.confidence)
            entity = Entity(
                document_id=document_id,
                page=page.page_number,
                tag=hit.tag,
                type=guess_type(display_context),
                parameters=parameters,
                quantity=quantity,
                bbox=block.bbox,
                confidence=confidence,
                source=block.source if block.source == ExtractionSource.OCR else ExtractionSource.PDF_TEXT,
                context=display_context[:500],
            )
            existing = entities.get(hit.tag)
            if existing is None or len(entity.parameters) > len(existing.parameters):
                entities[hit.tag] = entity
            elif existing is not None and existing.quantity is None and quantity is not None:
                existing.quantity = quantity
    return list(entities.values())
