"""Per-document extraction orchestration.

Deterministic extraction always runs (it is grounded by construction).  When a
vision model is configured its output is validated against the page text and
merged in as *enrichment* — the VLM interprets, the code decides.
"""

from __future__ import annotations

import logging

from dc_pdf import render_region, tile_grid
from dc_schemas import BBox, DocumentType, Entity, PageContent
from dc_vision import VisionModel, VisionModelError

from .grounding import ground_vlm_entities, vlm_bbox_to_points
from .rules import extract_drawing_entities
from .tables import extract_spec_lines, extract_tables_from_page, merge_by_tag

logger = logging.getLogger(__name__)

# Large sheets are fed to the VLM as overlapping square tiles: an A1 plan at
# full size is unreadable for any current model.  600 pt tiles at 200 dpi are
# ~1670 px — dense enough for small callout text.  A1 -> 12 tiles, A4 -> 1.
VLM_TILE_PT = 400.0
VLM_TILE_OVERLAP_PT = 60.0
VLM_TILE_DPI = 200
# A telephone-book sheet must not turn into hours of inference: above this
# budget the tile size grows (and DPI effectively drops) instead.
MAX_VLM_TILES_PER_PAGE = 24


def _page_tiles(width: float, height: float) -> list[BBox]:
    tile, overlap = VLM_TILE_PT, VLM_TILE_OVERLAP_PT
    tiles = tile_grid(width, height, tile, overlap)
    while len(tiles) > MAX_VLM_TILES_PER_PAGE:
        tile *= 1.5
        overlap = tile * 0.15
        tiles = tile_grid(width, height, tile, overlap)
    return tiles


def _intersects(a: BBox, b: BBox) -> bool:
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def _vlm_extract_tiled(
    pdf_path: str,
    page: PageContent,
    document_id: str,
    document_type: DocumentType,
    vision_model: VisionModel,
) -> list[Entity]:
    """Run VLM extraction tile by tile and merge grounded results."""
    import time

    tiles = _page_tiles(page.width, page.height)
    merged: list[Entity] = []
    for index, tile in enumerate(tiles):
        started = time.monotonic()
        image = render_region(pdf_path, page.page_number, tile, dpi=VLM_TILE_DPI)
        tile_text = "\n".join(
            block.text for block in page.text_blocks if _intersects(block.bbox, tile)
        )
        try:
            raw = vision_model.extract_entities(
                image,
                {
                    "document_type": document_type.value,
                    "page_number": page.page_number,
                    "page_text": tile_text,
                },
            )
        except VisionModelError as exc:
            logger.warning(
                "VLM failed on %s p.%d tile %d/%d: %s",
                document_id, page.page_number, index + 1, len(tiles), exc,
            )
            continue
        entities = ground_vlm_entities(raw, page, document_id, strict=not page.needs_ocr)
        logger.info(
            "VLM %s p.%d tile %d/%d: %.1fs, %d grounded entities",
            document_id, page.page_number, index + 1, len(tiles),
            time.monotonic() - started, len(entities),
        )
        for entity in entities:
            bbox = vlm_bbox_to_points(entity.bbox, VLM_TILE_DPI)
            if bbox is not None:
                entity.bbox = (
                    bbox[0] + tile[0], bbox[1] + tile[1],
                    bbox[2] + tile[0], bbox[3] + tile[1],
                )
        merged = merge_by_tag(merged, entities)
    return merged


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
    if deterministic and not page.needs_ocr:
        # Vector page that already yielded grounded entities: the VLM would
        # mostly re-read what the text layer said, at minutes per page.
        return deterministic
    if document_type == DocumentType.SPECIFICATION and not page.needs_ocr:
        # A vector specification page without detectable rows is almost always
        # a drawing sheet bound into the album (plans, details, schemes) —
        # tiling those through the VLM costs minutes each and yields entities
        # that do not belong in the specification side of the comparison.
        logger.info(
            "skipping VLM for vector spec page %d (no table rows found)", page.page_number
        )
        return deterministic

    vlm_entities = _vlm_extract_tiled(pdf_path, page, document_id, document_type, vision_model)
    logger.info(
        "page %d: %d deterministic + %d grounded VLM entities",
        page.page_number, len(deterministic), len(vlm_entities),
    )
    return merge_by_tag(deterministic, vlm_entities)
