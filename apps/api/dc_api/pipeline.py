"""The background analysis pipeline.

Executes the spec's 15 stages, recording each stage's status and duration on
the AnalysisRun row so the UI can show real progress instead of a fake
percentage.  Any failure marks the run ANALYSIS_FAILED with the stage name and
a readable error.
"""

from __future__ import annotations

import json
import logging
import time
import traceback

from dc_comparison import compare, verify_findings
from dc_extraction import extract_page_entities
from dc_matching import match_entities
from dc_ocr import create_ocr_provider
from dc_pdf import crop_region, parse_pdf, render_page, render_page_capped
from dc_schemas import (
    DocumentType,
    Entity,
    Finding,
    FindingStatus,
    FindingType,
    PageContent,
    Severity,
)
from dc_vision import create_vision_model

from .db import (
    AnalysisRun,
    Document,
    EntityRow,
    FindingRow,
    Page,
    VlmCache,
    session_scope,
    utcnow,
)
from .settings import settings
from .storage import cad_text_key, crop_key, get_storage, page_image_key


def _load_pages(project_id: str, document: Document, pdf_path: str) -> list[PageContent]:
    """Parse a document's PDF; for CAD uploads, use the exact CAD text layer.

    The rendered CAD PDF has glyph outlines instead of text, so the sidecar
    written at upload time (text pulled from DXF entities, already in PDF
    coordinates) replaces the parsed layer.
    """
    pages = parse_pdf(pdf_path)
    try:
        sidecar = get_storage().read(cad_text_key(project_id, document.id))
    except Exception:
        return pages
    cad_page = PageContent.model_validate_json(sidecar.decode("utf-8"))
    if pages:
        cad_page.width, cad_page.height = pages[0].width, pages[0].height
    logger.info("using CAD text sidecar for document %s", document.id)
    return [cad_page]

logger = logging.getLogger(__name__)

STAGES = [
    "validate_files",
    "parse_drawing",
    "render_drawing_pages",
    "extract_drawing_text",
    "ocr_drawing",
    "extract_drawing_entities",
    "parse_specification",
    "extract_specification",
    "normalize_entities",
    "match_entities",
    "compare",
    "verify_findings",
    "save_findings",
]


class PipelineError(RuntimeError):
    pass


def _entity_to_row(entity: Entity, page_ids: dict[tuple[str, int], str]) -> EntityRow:
    return EntityRow(
        id=entity.id,
        document_id=entity.document_id,
        page_id=page_ids.get((entity.document_id, entity.page)),
        page_number=entity.page,
        tag=entity.tag,
        type=entity.type,
        name=entity.name,
        data_json=json.loads(
            entity.model_dump_json(include={"parameters", "quantity", "context"})
        ),
        bbox_json=list(entity.bbox) if entity.bbox else None,
        confidence=entity.confidence,
        source=entity.source.value,
    )


def _finding_to_row(finding: Finding, project_id: str) -> FindingRow:
    return FindingRow(
        id=finding.id,
        project_id=project_id,
        type=finding.type.value,
        severity=finding.severity.value,
        status=finding.status.value,
        entity_key=finding.entity_key,
        parameter=finding.parameter,
        drawing_entity_id=finding.drawing_entity_id,
        spec_entity_id=finding.spec_entity_id,
        drawing_evidence_json=(
            finding.drawing_evidence.model_dump() if finding.drawing_evidence else None
        ),
        spec_evidence_json=finding.spec_evidence.model_dump() if finding.spec_evidence else None,
        values_json={
            "drawing": finding.drawing_value.model_dump() if finding.drawing_value else None,
            "specification": finding.spec_value.model_dump() if finding.spec_value else None,
        },
        explanation=finding.explanation,
        confidence=finding.confidence,
        extraction_confidence=finding.extraction_confidence,
        matching_confidence=finding.matching_confidence,
    )


class _StageTracker:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.stages: list[dict] = [{"stage": s, "status": "PENDING"} for s in STAGES]

    def _flush(self) -> None:
        with session_scope() as session:
            run = session.get(AnalysisRun, self.run_id)
            if run is not None:
                run.stages_json = [dict(s) for s in self.stages]

    def run(self, stage: str, fn, *args, **kwargs):
        entry = next(s for s in self.stages if s["stage"] == stage)
        entry["status"] = "RUNNING"
        self._flush()
        started = time.monotonic()
        try:
            result = fn(*args, **kwargs)
        except Exception:
            entry["status"] = "FAILED"
            entry["duration"] = round(time.monotonic() - started, 2)
            self._flush()
            raise
        entry["status"] = "DONE"
        entry["duration"] = round(time.monotonic() - started, 2)
        self._flush()
        return result

    def note(self, stage: str, text: str) -> None:
        """Live progress note on a running stage (shown in the UI)."""
        entry = next(s for s in self.stages if s["stage"] == stage)
        entry["note"] = text
        self._flush()

    def skip(self, stage: str, note: str = "") -> None:
        entry = next(s for s in self.stages if s["stage"] == stage)
        entry["status"] = "SKIPPED"
        if note:
            entry["note"] = note
        self._flush()


def _vlm_cached(vision_model, document_sha: str, page_number: int):
    """Wrap a vision model so page extractions hit the cache table."""
    if vision_model is None:
        return None

    import hashlib

    class _CachedExtract:
        def __getattr__(self, item):
            return getattr(vision_model, item)

        def extract_entities(self, image, context):
            # image hash in the key: tiled pages issue several calls per page
            image_sha = hashlib.sha256(image).hexdigest()[:16]
            key = (
                f"{document_sha}:{page_number}:{image_sha}"
                f":{vision_model.version}:{settings.prompt_version}"
            )
            with session_scope() as session:
                cached = session.get(VlmCache, key)
                if cached is not None:
                    return cached.result_json
            result = vision_model.extract_entities(image, context)
            with session_scope() as session:
                session.merge(VlmCache(cache_key=key, result_json=result))
            return result

    return _CachedExtract()


def _ocr_pages(pdf_path: str, pages: list[PageContent], ocr) -> None:
    """Fill text blocks for scanned pages in place."""
    for page in pages:
        if not page.needs_ocr:
            continue
        image, used_dpi = render_page_capped(
            pdf_path, page.page_number, dpi=settings.ocr_render_dpi
        )
        blocks = ocr.extract(image, dpi=used_dpi)
        if blocks:
            page.text_blocks = blocks
            page.text = "\n".join(b.text for b in blocks)


def _persist_pages(project_id: str, document: Document, pages: list[PageContent]) -> dict:
    storage = get_storage()
    page_ids: dict[tuple[str, int], str] = {}
    with session_scope() as session:
        for page in pages:
            key = page_image_key(project_id, document.id, page.page_number)
            image = render_page(
                storage.local_path(document.storage_path),
                page.page_number,
                dpi=settings.page_render_dpi,
            )
            storage.save(key, image)
            row = Page(
                document_id=document.id,
                page_number=page.page_number,
                width=page.width,
                height=page.height,
                text=page.text,
                image_path=key,
                needs_ocr=int(page.needs_ocr),
            )
            session.add(row)
            session.flush()
            page_ids[(document.id, page.page_number)] = row.id
        session.query(Document).filter_by(id=document.id).update(
            {"page_count": len(pages), "status": "PROCESSED"}
        )
    return page_ids


def _save_crops(project_id: str, findings: list[Finding], pdf_paths: dict[str, str]) -> None:
    storage = get_storage()
    for finding in findings:
        for side, evidence in (("drawing", finding.drawing_evidence), ("spec", finding.spec_evidence)):
            if evidence is None or evidence.bbox is None:
                continue
            pdf_path = pdf_paths.get(evidence.document_id)
            if not pdf_path:
                continue
            try:
                image = crop_region(pdf_path, evidence.page, evidence.bbox)
            except Exception as exc:
                logger.warning("crop failed for %s/%s: %s", finding.id, side, exc)
                continue
            key = crop_key(project_id, finding.id, side)
            storage.save(key, image)
            evidence.crop_path = key


def run_analysis(project_id: str, run_id: str) -> None:
    """Execute the full pipeline for one project's drawing + specification."""
    logger.info("analysis started: project=%s run=%s", project_id, run_id)
    tracker = _StageTracker(run_id)
    storage = get_storage()
    try:
        # 1. validate ------------------------------------------------------
        def validate():
            with session_scope() as session:
                docs = session.query(Document).filter_by(project_id=project_id).all()
                drawing = next((d for d in docs if d.type == "DRAWING"), None)
                spec = next((d for d in docs if d.type == "SPECIFICATION"), None)
            if drawing is None or spec is None:
                raise PipelineError(
                    "Both a drawing PDF and a specification PDF must be uploaded."
                )
            return drawing, spec

        drawing_doc, spec_doc = tracker.run("validate_files", validate)
        drawing_pdf = storage.local_path(drawing_doc.storage_path)
        spec_pdf = storage.local_path(spec_doc.storage_path)

        try:
            vlm_extra = json.loads(settings.vlm_extra_json) if settings.vlm_extra_json else None
        except ValueError:
            logger.warning("VLM_EXTRA_JSON is not valid JSON; ignoring")
            vlm_extra = None
        vision_model = create_vision_model(
            settings.vlm_base_url,
            settings.vlm_model,
            api_key=settings.vlm_api_key,
            prompts_dir=settings.prompts_dir,
            prompt_version=settings.prompt_version,
            timeout=settings.vlm_timeout,
            max_tokens=settings.vlm_max_tokens,
            extra_body=vlm_extra,
        )
        with session_scope() as session:
            run = session.get(AnalysisRun, run_id)
            run.model = vision_model.name if vision_model else "deterministic-only"
            run.model_version = vision_model.version if vision_model else None
            run.prompt_version = settings.prompt_version

        # 2-3. parse + render drawing -------------------------------------
        drawing_pages = tracker.run(
            "parse_drawing", _load_pages, project_id, drawing_doc, drawing_pdf
        )
        drawing_page_ids = tracker.run(
            "render_drawing_pages", _persist_pages, project_id, drawing_doc, drawing_pages
        )
        tracker.skip("extract_drawing_text", "done during parse")

        # 5. OCR when needed ----------------------------------------------
        if any(p.needs_ocr for p in drawing_pages):
            ocr = create_ocr_provider(settings.ocr_provider)
            tracker.run("ocr_drawing", _ocr_pages, drawing_pdf, drawing_pages, ocr)
        else:
            tracker.skip("ocr_drawing", "text layer sufficient")

        # 6. drawing entities ---------------------------------------------
        def extract_drawing():
            entities: list[Entity] = []
            for page in drawing_pages:
                tracker.note(
                    "extract_drawing_entities",
                    f"page {page.page_number}/{len(drawing_pages)}",
                )
                logger.info("drawing extraction: page %d/%d", page.page_number, len(drawing_pages))
                model = _vlm_cached(vision_model, drawing_doc.sha256, page.page_number)
                entities += extract_page_entities(
                    drawing_pdf, page, drawing_doc.id, DocumentType.DRAWING, model
                )
            return entities

        drawing_entities = tracker.run("extract_drawing_entities", extract_drawing)
        if not drawing_entities:
            # Comparing an empty drawing against a full specification would
            # bury the user in bogus MISSING_ON_DRAWING findings.  Refuse.
            scanned = any(p.needs_ocr for p in drawing_pages)
            hint = (
                "the drawing appears to be a scan without a text layer and no OCR "
                "engine is configured (set OCR_PROVIDER and install one)"
                if scanned
                else "no equipment tags were recognised on the drawing"
            )
            raise PipelineError(
                f"No entities were extracted from the drawing: {hint}. "
                "Analysis was stopped to avoid flooding the results with "
                "false MISSING_ON_DRAWING findings."
            )

        # 7-8. specification ----------------------------------------------
        spec_pages = tracker.run(
            "parse_specification", _load_pages, project_id, spec_doc, spec_pdf
        )
        spec_page_ids = _persist_pages(project_id, spec_doc, spec_pages)
        if any(p.needs_ocr for p in spec_pages):
            ocr = create_ocr_provider(settings.ocr_provider)
            _ocr_pages(spec_pdf, spec_pages, ocr)

        def extract_spec():
            entities: list[Entity] = []
            for page in spec_pages:
                tracker.note(
                    "extract_specification",
                    f"page {page.page_number}/{len(spec_pages)}, {len(entities)} entities so far",
                )
                logger.info(
                    "spec extraction: page %d/%d (%d entities so far)",
                    page.page_number, len(spec_pages), len(entities),
                )
                model = _vlm_cached(vision_model, spec_doc.sha256, page.page_number)
                entities += extract_page_entities(
                    spec_pdf, page, spec_doc.id, DocumentType.SPECIFICATION, model
                )
            return entities

        spec_entities = tracker.run("extract_specification", extract_spec)

        # 9. normalisation happens inside Quantity.of; persist entities ----
        def persist_entities():
            page_ids = {**drawing_page_ids, **spec_page_ids}
            with session_scope() as session:
                for document_id in (drawing_doc.id, spec_doc.id):
                    session.query(EntityRow).filter_by(document_id=document_id).delete()
                for entity in drawing_entities + spec_entities:
                    session.add(_entity_to_row(entity, page_ids))

        tracker.run("normalize_entities", persist_entities)

        # 10-12. match, compare, verify ------------------------------------
        matches = tracker.run("match_entities", match_entities, drawing_entities, spec_entities)
        candidates = tracker.run("compare", compare, matches)
        findings = tracker.run(
            "verify_findings",
            verify_findings,
            candidates,
            vision_model,
            drawing_pdf,
            spec_pdf,
        )

        # A drawing that covers a fraction of the specification (a single
        # floor plan vs a project-wide schedule) makes "missing on drawing"
        # weak evidence: keep those findings but route them to review.
        drawing_tag_count = len({e.tag for e in drawing_entities})
        spec_tag_count = len({e.tag for e in spec_entities})
        if spec_tag_count and drawing_tag_count / spec_tag_count < 0.5:
            for finding in findings:
                if finding.type == FindingType.MISSING_ON_DRAWING:
                    finding.status = FindingStatus.NEEDS_REVIEW
                    finding.severity = Severity.MEDIUM
                    finding.explanation += (
                        " Note: the drawing contains far fewer systems than the "
                        "specification (likely a partial sheet), so absence on "
                        "this sheet is weak evidence."
                    )

        # 13-14. save findings + evidence crops ----------------------------
        def save():
            _save_crops(
                project_id,
                findings,
                {drawing_doc.id: drawing_pdf, spec_doc.id: spec_pdf},
            )
            with session_scope() as session:
                session.query(FindingRow).filter_by(project_id=project_id).delete()
                for finding in findings:
                    session.add(_finding_to_row(finding, project_id))
                run = session.get(AnalysisRun, run_id)
                run.status = "ANALYSIS_COMPLETED"
                run.finished_at = utcnow()

        tracker.run("save_findings", save)
        logger.info(
            "analysis completed: project=%s entities=%d/%d findings=%d",
            project_id, len(drawing_entities), len(spec_entities), len(findings),
        )
    except Exception as exc:
        logger.error("analysis failed: project=%s: %s\n%s", project_id, exc, traceback.format_exc())
        with session_scope() as session:
            run = session.get(AnalysisRun, run_id)
            if run is not None:
                run.status = "ANALYSIS_FAILED"
                run.error = f"{type(exc).__name__}: {exc}"
                run.finished_at = utcnow()
