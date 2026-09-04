"""Hallucination control for VLM output.

A vision model may only *interpret* the page — it is never trusted to invent.
Every entity it returns is checked against the page text (vector layer + OCR):

* the tag must literally occur on the page;
* every parameter value must occur on the page (via its ``raw`` string or the
  bare number);
* ungrounded parameters are dropped; entities with ungrounded tags are dropped.

What survives is, by construction, evidence-backed.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from dc_schemas import Entity, ExtractionSource, PageContent, Quantity

from .tags import find_tags

logger = logging.getLogger(__name__)


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "")
    s = s.replace("²", "2").replace("³", "3")
    s = re.sub(r"[\s  \-–—_./\\]+", "", s)
    return s.upper()


def _number_variants(value: float) -> set[str]:
    variants = {f"{value:g}"}
    if float(value).is_integer():
        integer = int(value)
        variants.add(str(integer))
        variants.add(f"{integer:,}".replace(",", ""))  # plain digits
    return variants


def _value_grounded(quantity: Quantity, folded_page: str) -> bool:
    if quantity.raw and _fold(quantity.raw) in folded_page:
        return True
    if quantity.value is None:
        return False
    return any(v in folded_page for v in _number_variants(quantity.value))


# On scanned pages the "text layer" is OCR output that may itself be garbage;
# an ungrounded-but-plausible VLM tag is then kept at this confidence so the
# finding routes to NEEDS_REVIEW instead of being either trusted or lost.
LENIENT_UNGROUNDED_CONFIDENCE = 0.6


def ground_vlm_entities(
    raw: dict[str, Any],
    page: PageContent,
    document_id: str,
    strict: bool = True,
) -> list[Entity]:
    """Validate and convert a VLM extraction reply into grounded entities.

    ``strict=False`` (scanned pages): a tag missing from the (OCR) text layer
    is kept with capped confidence instead of dropped — the OCR text cannot be
    trusted as ground truth there.  Parameter *values* are still required to
    be grounded; numbers are where hallucinations hurt most.
    """
    folded_page = _fold(page.text + "\n" + "\n".join(b.text for b in page.text_blocks))
    grounded: list[Entity] = []
    for item in raw.get("entities", []) or []:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or "").strip()
        if not tag or not find_tags(tag):
            continue
        tag_grounded = _fold(tag) in folded_page
        if not tag_grounded and strict:
            logger.info("dropping ungrounded VLM entity %r (tag not on page)", tag)
            continue

        parameters: dict[str, Quantity] = {}
        for name, payload in (item.get("parameters") or {}).items():
            if not isinstance(payload, dict):
                continue
            value = payload.get("value")
            if value is None:
                continue  # "value: null, confidence: 0" convention — nothing to keep
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            quantity = Quantity.of(value, payload.get("unit"), raw=payload.get("raw"))
            if _value_grounded(quantity, folded_page):
                parameters[str(name)] = quantity
            else:
                logger.info("dropping ungrounded VLM parameter %s=%s for %s", name, value, tag)

        quantity_field = None
        quantity_payload = item.get("quantity")
        if isinstance(quantity_payload, dict) and quantity_payload.get("value") is not None:
            try:
                count = float(quantity_payload["value"])
                candidate = Quantity.of(count, quantity_payload.get("unit") or "pcs",
                                        raw=quantity_payload.get("raw"))
                if _value_grounded(candidate, folded_page):
                    quantity_field = candidate
            except (TypeError, ValueError):
                pass

        entity_type = item.get("type")
        if entity_type is not None:
            entity_type = str(entity_type)

        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        if not tag_grounded:
            confidence = min(confidence, LENIENT_UNGROUNDED_CONFIDENCE)

        bbox = item.get("bbox")
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
            bbox = None
        else:
            try:
                bbox = tuple(float(v) for v in bbox)
            except (TypeError, ValueError):
                bbox = None

        grounded.append(
            Entity(
                document_id=document_id,
                page=page.page_number,
                tag=tag,
                type=entity_type,
                name=(str(item["name"]) if item.get("name") else None),
                parameters=parameters,
                quantity=quantity_field,
                bbox=bbox,
                confidence=confidence,
                source=ExtractionSource.VLM,
                context=None,
            )
        )
    return grounded


def vlm_bbox_to_points(bbox, dpi: int):
    """VLM bboxes are in rendered-image pixels; convert back to PDF points."""
    if bbox is None:
        return None
    scale = 72.0 / dpi
    return tuple(float(v) * scale for v in bbox)
