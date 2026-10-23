"""FastAPI application: projects, documents, analysis, findings, evidence."""

from __future__ import annotations

import logging

from dc_pdf import compute_sha256
from fastapi import Depends, FastAPI, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import (
    AnalysisRun,
    Document,
    FindingRow,
    Project,
    get_session,
    init_db,
    utcnow,
)
from .jobs import dispatch_analysis
from .schemas_api import (
    AnalysisOut,
    DocumentOut,
    EvidenceOut,
    FindingOut,
    ProjectCreate,
    ProjectOut,
    StageOut,
    ValueOut,
)
from .settings import settings
from .storage import document_key, get_storage
from .takeoff_routes import router as takeoff_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Foreman — AI Drawing Checker", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(takeoff_router)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# --- helpers ---------------------------------------------------------------


def _project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


def _latest_run(session: Session, project_id: str) -> AnalysisRun | None:
    return (
        session.query(AnalysisRun)
        .filter_by(project_id=project_id)
        .order_by(AnalysisRun.started_at.desc())
        .first()
    )


def _project_out(session: Session, project: Project) -> ProjectOut:
    run = _latest_run(session, project.id)
    return ProjectOut(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        updated_at=project.updated_at,
        document_count=session.query(Document).filter_by(project_id=project.id).count(),
        finding_count=session.query(FindingRow).filter_by(project_id=project.id).count(),
        analysis_status=run.status if run else None,
    )


def _document_names(session: Session, project_id: str) -> dict[str, str]:
    docs = session.query(Document).filter_by(project_id=project_id).all()
    return {d.id: d.filename for d in docs}


def _value_out(payload: dict | None) -> ValueOut | None:
    if not payload:
        return None
    value, unit = payload.get("value"), payload.get("unit")
    display = None
    if value is not None:
        formatted = f"{value:,.10g}".replace(",", " ")
        display = f"{formatted} {unit}" if unit else formatted
    return ValueOut(value=value, unit=unit, raw=payload.get("raw"), display=display)


def _evidence_out(payload: dict | None, names: dict[str, str]) -> EvidenceOut | None:
    if not payload:
        return None
    return EvidenceOut(**payload, document_filename=names.get(payload.get("document_id", "")))


def _finding_out(row: FindingRow, names: dict[str, str]) -> FindingOut:
    values = row.values_json or {}
    return FindingOut(
        id=row.id,
        project_id=row.project_id,
        type=row.type,
        severity=row.severity,
        status=row.status,
        entity=row.entity_key,
        parameter=row.parameter,
        drawing_value=_value_out(values.get("drawing")),
        specification_value=_value_out(values.get("specification")),
        drawing_evidence=_evidence_out(row.drawing_evidence_json, names),
        specification_evidence=_evidence_out(row.spec_evidence_json, names),
        explanation=row.explanation,
        confidence=row.confidence,
        extraction_confidence=row.extraction_confidence,
        matching_confidence=row.matching_confidence,
        created_at=row.created_at,
    )


# --- projects --------------------------------------------------------------


@app.post("/api/projects", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)):
    if not payload.name.strip():
        raise HTTPException(422, "project name must not be empty")
    project = Project(name=payload.name.strip())
    session.add(project)
    session.commit()
    return _project_out(session, project)


@app.get("/api/projects", response_model=list[ProjectOut])
def list_projects(session: Session = Depends(get_session)):
    projects = session.query(Project).order_by(Project.created_at.desc()).all()
    return [_project_out(session, p) for p in projects]


@app.get("/api/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, session: Session = Depends(get_session)):
    return _project_out(session, _project_or_404(session, project_id))


# --- documents -------------------------------------------------------------


@app.post("/api/projects/{project_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    project_id: str,
    file: UploadFile,
    type: str = Query(pattern="^(DRAWING|SPECIFICATION)$"),
    session: Session = Depends(get_session),
):
    import tempfile
    from pathlib import Path

    from dc_cad import CadConversionError, is_cad_file, load_cad_document

    from .storage import cad_text_key, raw_document_key

    _project_or_404(session, project_id)
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in (".pdf", ".dxf", ".dwg"):
        raise HTTPException(422, "supported formats: PDF, DXF, DWG")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"file exceeds {settings.max_upload_mb} MB")
    if extension == ".pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(422, "file is not a valid PDF")

    # Several files per type are allowed (sheets, albums); duplicates by
    # content are rejected to keep re-uploads idempotent.
    import hashlib

    digest = hashlib.sha256(data).hexdigest()
    existing = (
        session.query(Document)
        .filter_by(project_id=project_id, type=type, sha256=digest)
        .first()
    )
    if existing is not None:
        raise HTTPException(409, f"this file is already uploaded as {existing.filename!r}")
    document = Document(
        project_id=project_id,
        type=type,
        filename=filename,
        storage_path="",
    )
    session.add(document)
    session.flush()
    key = document_key(project_id, document.id)
    storage = get_storage()

    if is_cad_file(filename):
        # CAD flow: keep the original, render a PDF for the pipeline, and
        # store the CAD text layer (exact coordinates, no OCR) as a sidecar.
        with tempfile.TemporaryDirectory(prefix="foreman_cad_") as tmp:
            source = Path(tmp) / f"upload{extension}"
            source.write_bytes(data)
            pdf_path = Path(tmp) / "rendered.pdf"
            try:
                page = load_cad_document(source, pdf_path, settings.oda_converter_path)
            except CadConversionError as exc:
                session.rollback()
                raise HTTPException(422, str(exc)) from exc
            except Exception as exc:
                session.rollback()
                raise HTTPException(422, f"could not read CAD file: {exc}") from exc
            storage.save(key, pdf_path.read_bytes())
            storage.save(raw_document_key(project_id, document.id, extension), data)
            storage.save(
                cad_text_key(project_id, document.id),
                page.model_dump_json().encode("utf-8"),
            )
    else:
        storage.save(key, data)

    document.storage_path = key
    document.sha256 = compute_sha256(storage.local_path(key))
    session.commit()
    return DocumentOut(
        id=document.id,
        project_id=project_id,
        type=document.type,
        filename=document.filename,
        page_count=document.page_count,
        status=document.status,
        created_at=document.created_at,
    )


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: str, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "document not found")
    from .db import EntityRow, Page

    session.query(EntityRow).filter_by(document_id=document_id).delete()
    session.query(Page).filter_by(document_id=document_id).delete()
    session.delete(document)
    session.commit()
    return Response(status_code=204)


@app.get("/api/projects/{project_id}/documents", response_model=list[DocumentOut])
def list_documents(project_id: str, session: Session = Depends(get_session)):
    _project_or_404(session, project_id)
    docs = session.query(Document).filter_by(project_id=project_id).all()
    return [
        DocumentOut(
            id=d.id, project_id=project_id, type=d.type, filename=d.filename,
            page_count=d.page_count, status=d.status, created_at=d.created_at,
        )
        for d in docs
    ]


# --- analysis --------------------------------------------------------------


@app.post("/api/projects/{project_id}/analyze", response_model=AnalysisOut, status_code=202)
def start_analysis(project_id: str, session: Session = Depends(get_session)):
    _project_or_404(session, project_id)
    types = {d.type for d in session.query(Document).filter_by(project_id=project_id).all()}
    if types != {"DRAWING", "SPECIFICATION"} and not {"DRAWING", "SPECIFICATION"} <= types:
        raise HTTPException(422, "upload both a drawing and a specification first")
    running = (
        session.query(AnalysisRun)
        .filter_by(project_id=project_id, status="ANALYSIS_STARTED")
        .first()
    )
    if running is not None:
        raise HTTPException(409, "analysis already running for this project")
    run = AnalysisRun(project_id=project_id)
    session.add(run)
    session.commit()
    dispatch_analysis(project_id, run.id)
    return _analysis_out(run)


def _analysis_out(run: AnalysisRun) -> AnalysisOut:
    return AnalysisOut(
        id=run.id,
        project_id=run.project_id,
        status=run.status,
        error=run.error,
        model=run.model,
        prompt_version=run.prompt_version,
        stages=[StageOut(**s) for s in (run.stages_json or [])],
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@app.get("/api/projects/{project_id}/analysis", response_model=AnalysisOut)
def get_analysis(project_id: str, session: Session = Depends(get_session)):
    _project_or_404(session, project_id)
    run = _latest_run(session, project_id)
    if run is None:
        raise HTTPException(404, "no analysis has been started for this project")
    return _analysis_out(run)


# --- findings --------------------------------------------------------------


@app.get("/api/projects/{project_id}/findings", response_model=list[FindingOut])
def list_findings(
    project_id: str,
    severity: str | None = Query(default=None, pattern="^(HIGH|MEDIUM|LOW)$"),
    status: str | None = Query(
        default=None, pattern="^(OPEN|CONFIRMED|FALSE_POSITIVE|NEEDS_REVIEW)$"
    ),
    session: Session = Depends(get_session),
):
    _project_or_404(session, project_id)
    query = session.query(FindingRow).filter_by(project_id=project_id)
    if severity:
        query = query.filter_by(severity=severity)
    if status:
        query = query.filter_by(status=status)
    names = _document_names(session, project_id)
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    rows = sorted(query.all(), key=lambda r: (severity_order.get(r.severity, 3), -r.confidence))
    return [_finding_out(r, names) for r in rows]


@app.get("/api/findings/{finding_id}", response_model=FindingOut)
def get_finding(finding_id: str, session: Session = Depends(get_session)):
    row = session.get(FindingRow, finding_id)
    if row is None:
        raise HTTPException(404, "finding not found")
    return _finding_out(row, _document_names(session, row.project_id))


def _set_finding_status(finding_id: str, status: str, session: Session) -> FindingOut:
    row = session.get(FindingRow, finding_id)
    if row is None:
        raise HTTPException(404, "finding not found")
    row.status = status
    project = session.get(Project, row.project_id)
    if project is not None:
        project.updated_at = utcnow()
    session.commit()
    return _finding_out(row, _document_names(session, row.project_id))


@app.post("/api/findings/{finding_id}/confirm", response_model=FindingOut)
def confirm_finding(finding_id: str, session: Session = Depends(get_session)):
    return _set_finding_status(finding_id, "CONFIRMED", session)


@app.post("/api/findings/{finding_id}/false-positive", response_model=FindingOut)
def false_positive_finding(finding_id: str, session: Session = Depends(get_session)):
    return _set_finding_status(finding_id, "FALSE_POSITIVE", session)


# --- evidence images -------------------------------------------------------


def _fitted_page(document: Document, page_number: int, max_side: int) -> bytes:
    """A display-sized page image, rendered once and kept in storage."""
    from dc_pdf import render_page_fit

    from .storage import page_image_key

    storage = get_storage()
    key = page_image_key(document.project_id, document.id, page_number).replace(
        ".png", f".max{max_side}.png"
    )
    try:
        return storage.read(key)
    except Exception:
        pass  # not rendered yet
    try:
        data = render_page_fit(
            storage.local_path(document.storage_path), page_number, max_side,
            dpi=settings.page_render_dpi,
        )
    except Exception as exc:
        raise HTTPException(404, f"page unavailable: {exc}") from exc
    storage.save(key, data)
    return data


@app.get("/api/findings/{finding_id}/evidence/{side}.png")
def finding_evidence_image(finding_id: str, side: str, session: Session = Depends(get_session)):
    if side not in ("drawing", "spec"):
        raise HTTPException(404, "side must be drawing or spec")
    row = session.get(FindingRow, finding_id)
    if row is None:
        raise HTTPException(404, "finding not found")
    evidence = row.drawing_evidence_json if side == "drawing" else row.spec_evidence_json
    if not evidence or not evidence.get("crop_path"):
        raise HTTPException(404, "no evidence crop for this side")
    try:
        data = get_storage().read(evidence["crop_path"])
    except Exception as exc:
        raise HTTPException(404, f"evidence image unavailable: {exc}") from exc
    return Response(content=data, media_type="image/png")


@app.get("/api/documents/{document_id}/pages/{page_number}.png")
def page_image(
    document_id: str,
    page_number: int,
    max_side: int | None = Query(default=None, ge=256, le=8192),
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "document not found")
    from .storage import page_image_key

    if max_side is not None:
        return Response(content=_fitted_page(document, page_number, max_side),
                        media_type="image/png")
    try:
        data = get_storage().read(page_image_key(document.project_id, document_id, page_number))
    except Exception:
        # fall back to rendering on the fly
        from dc_pdf import render_page

        try:
            data = render_page(
                get_storage().local_path(document.storage_path),
                page_number,
                dpi=settings.page_render_dpi,
            )
        except Exception as exc:
            raise HTTPException(404, f"page unavailable: {exc}") from exc
    return Response(content=data, media_type="image/png")
