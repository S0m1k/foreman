"""Specification extraction.

Specifications are mostly tables (position / name / unit / quantity /
characteristics).  Primary path: PyMuPDF ``find_tables``; fallback: line-based
parsing of the text layer for text-shaped specifications.  Both paths keep the
page and bbox of every row so findings can point back at the exact cell.
"""

from __future__ import annotations

import logging

import pymupdf

from dc_pdf import clean_text

from dc_schemas import Entity, ExtractionSource, PageContent, Quantity, units

from .rules import _extract_parameters, _extract_quantity, guess_type
from .tags import find_tags

logger = logging.getLogger(__name__)

# header cell -> column role
_HEADER_ROLES: list[tuple[tuple[str, ...], str]] = [
    (("поз", "обознач", "марка", "tag", "position", "поз."), "tag"),
    (("наимен", "name", "описан", "description"), "name"),
    (("кол", "кол-во", "количест", "qty", "quantity"), "quantity"),
    (("ед", "unit", "изм"), "unit"),
    (("расход", "airflow", "производит"), "airflow"),
    (("мощн", "power"), "power"),
    (("напряж", "voltage"), "voltage"),
    (("ток", "current"), "current"),
    (("масса", "вес", "mass", "weight"), "mass"),
    (("характер", "characteristic", "параметр", "техничес"), "characteristics"),
]


def _role_for_header(cell_text: str) -> str | None:
    lowered = (cell_text or "").strip().lower()
    if not lowered:
        return None
    for keywords, role in _HEADER_ROLES:
        if any(lowered.startswith(k) or k in lowered for k in keywords):
            return role
    return None


def _row_bbox(row_cells: list) -> tuple[float, float, float, float] | None:
    boxes = [c for c in row_cells if c is not None]
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _entity_from_row(
    roles: dict[int, str],
    cells: list[str],
    bbox: tuple[float, float, float, float] | None,
    page_number: int,
    document_id: str,
) -> Entity | None:
    values = {roles[i]: (cells[i] or "").strip() for i in roles if i < len(cells)}
    tag_text = values.get("tag", "")
    hits = find_tags(tag_text)
    if not hits:
        return None
    tag = hits[0].tag

    parameters: dict[str, Quantity] = {}
    unit_hint = values.get("unit")
    for role in ("airflow", "power", "voltage", "current", "mass"):
        cell = values.get(role)
        if not cell:
            continue
        found = units.find_measurements(cell)
        if found:
            m = found[0]
            parameters[role] = Quantity.of(m.value, m.unit, raw=cell.strip())

    quantity: Quantity | None = None
    quantity_cell = values.get("quantity")
    if quantity_cell:
        number = units.parse_number(quantity_cell)
        if number is None:
            quantity = _extract_quantity(quantity_cell)
        else:
            unit = "pcs" if not unit_hint or units.lookup(unit_hint) is None else unit_hint
            quantity = Quantity.of(number, unit, raw=quantity_cell.strip())

    name = values.get("name") or None
    row_text = " | ".join(c for c in cells if c)
    # A free-form characteristics column carries dimension-typed measurements.
    characteristics = values.get("characteristics")
    if characteristics:
        for param_name, param_value in _extract_parameters(characteristics).items():
            parameters.setdefault(param_name, param_value)
    if not parameters:
        # characteristics sometimes live inside the name column
        parameters = _extract_parameters(name or row_text)

    return Entity(
        document_id=document_id,
        page=page_number,
        tag=tag,
        type=guess_type(f"{tag} {name or ''} {row_text}"),
        name=name,
        parameters=parameters,
        quantity=quantity,
        bbox=bbox,
        confidence=min(hits[0].confidence + 0.05, 1.0),
        source=ExtractionSource.TABLE,
        context=row_text[:500],
    )


def extract_tables_from_page(
    pdf_path: str, page_number: int, document_id: str
) -> list[Entity]:
    """Extract specification rows from detected tables on one page."""
    entities: list[Entity] = []
    with pymupdf.open(pdf_path) as doc:
        page = doc[page_number - 1]
        try:
            tables = page.find_tables()
        except Exception as exc:  # pragma: no cover - library edge cases
            logger.warning("find_tables failed on page %d: %s", page_number, exc)
            return []
        for table in tables.tables:
            rows = table.extract()
            if len(rows) < 2:
                continue
            header = [clean_text(str(c or "")) for c in rows[0]]
            roles = {
                i: role
                for i, cell in enumerate(header)
                if (role := _role_for_header(cell)) is not None
            }
            if "tag" not in roles.values():
                continue
            try:
                row_objects = list(table.rows)
            except Exception:  # pragma: no cover
                row_objects = []
            for index, row in enumerate(rows[1:], start=1):
                cells = [clean_text(str(c or "")) for c in row]
                bbox = None
                if index < len(row_objects):
                    bbox = _row_bbox(list(getattr(row_objects[index], "cells", []) or []))
                entity = _entity_from_row(roles, cells, bbox, page_number, document_id)
                if entity is not None:
                    entities.append(entity)
    return entities


def extract_spec_lines(page: PageContent, document_id: str) -> list[Entity]:
    """Fallback for text-shaped specifications: one entity per tag-led line."""
    entities: list[Entity] = []
    for block in page.text_blocks:
        for line in block.text.splitlines():
            hits = find_tags(line)
            if not hits or hits[0].start > 12:
                continue  # only lines that *start* with a tag look like rows
            tag = hits[0].tag
            tail = line[hits[0].end :]
            entity = Entity(
                document_id=document_id,
                page=page.page_number,
                tag=tag,
                type=guess_type(line),
                name=None,
                parameters=_extract_parameters(tail),
                quantity=_extract_quantity(tail),
                bbox=block.bbox,
                confidence=min(hits[0].confidence, block.confidence),
                source=block.source,
                context=line[:500],
            )
            entities.append(entity)
    return entities


def merge_by_tag(primary: list[Entity], secondary: list[Entity]) -> list[Entity]:
    """Union of two extraction passes; the primary pass wins on collisions."""
    from dc_matching import normalize_tag

    seen = {normalize_tag(e.tag): e for e in primary}
    merged = list(primary)
    for entity in secondary:
        key = normalize_tag(entity.tag)
        existing = seen.get(key)
        if existing is None:
            merged.append(entity)
            seen[key] = entity
            continue
        # enrich, never overwrite
        for name, quantity in entity.parameters.items():
            existing.parameters.setdefault(name, quantity)
        if existing.quantity is None and entity.quantity is not None:
            existing.quantity = entity.quantity
        if existing.name is None and entity.name:
            existing.name = entity.name
    return merged
