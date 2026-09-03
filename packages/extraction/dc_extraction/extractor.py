"""Per-document extraction orchestration.

Deterministic extraction always runs (it is grounded by construction).  When a
vision model is configured its output is validated against the page text and
merged in as *enrichment* — the VLM interprets, the code decides.
"""

from __future__ import annotations

import logging

from dc_pdf import render_page
from dc_schemas import DocumentType, Entity, PageContent
from dc_vision import VisionModel, VisionModelError

from .grounding import ground_vlm_entities, vlm_bbox_to_points
from .rules import extract_drawing_entities
from .tables import extract_spec_lines, extract_tables_from_page, merge_by_tag

logger = logging.getLogger(__name__)

VLM_RENDER_DPI = 150


def extract_page_entities(
    pdf_path: str,
    page: PageContent,
    document_id: str,
    document_type: DocumentType,
    vision_model: VisionModel | None = None,
) -> list[Entity]:
    """Extract entities for one page: deterministic first, VLM as enrichment."""
    if document_type == DocumentType.SPECIFICATION:
        deterministic = extract_tables_from_page(pdf_path, page.page_number, document_id)
        fallback = extract_spec_lines(page, document_id)
        deterministic = merge_by_tag(deterministic, fallback)
    else:
        deterministic = extract_drawing_entities(page, document_id)

    if vision_model is None:
        return deterministic

    try:
        image = render_page(pdf_path, page.page_number, dpi=VLM_RENDER_DPI)
        raw = vision_model.extract_entities(
            image,
            {
                "document_type": document_type.value,
                "page_number": page.page_number,
                "page_text": page.text,
            },
        )
    except VisionModelError as exc:
        logger.warning(
            "VLM extraction failed on %s page %d: %s — keeping deterministic result",
            document_id, page.page_number, exc,
        )
        return deterministic

    vlm_entities = ground_vlm_entities(raw, page, document_id)
    for entity in vlm_entities:
        entity.bbox = vlm_bbox_to_points(entity.bbox, VLM_RENDER_DPI)
    logger.info(
        "page %d: %d deterministic + %d grounded VLM entities",
        page.page_number, len(deterministic), len(vlm_entities),
    )
    return merge_by_tag(deterministic, vlm_entities)
