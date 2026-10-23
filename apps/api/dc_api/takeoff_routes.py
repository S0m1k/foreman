"""Duct takeoff routes: run, sheets summary, one sheet, edits, XLSX export."""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import quote

from dc_extraction.takeoff import write_xlsx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from . import takeoff_view as view
from .db import Document, Project, TakeoffRun, get_session
from .jobs import dispatch_takeoff
from .schemas_api import (
    SystemTotalOut,
    TakeoffOut,
    TakeoffOverridesIn,
    TakeoffProgressOut,
    TakeoffRunOut,
    TakeoffSheetOut,
    TakeoffSheetSummaryOut,
)

router = APIRouter(prefix="/api")

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORT_HEADER = ["Система", "Сечение", "Изоляция", "Длина, м"]
# Sharp enough to read callouts at the sheet screen's top zoom, small enough
# (~17 Mpx for an A0 plan) for a browser to draw.
SHEET_IMAGE_MAX_SIDE = 6000


def _latest(session: Session, project_id: str) -> TakeoffRun | None:
    return (
        session.query(TakeoffRun)
        .filter_by(project_id=project_id)
        .order_by(TakeoffRun.started_at.desc())
        .first()
    )


def _run_or_404(session: Session, takeoff_id: str) -> TakeoffRun:
    run = session.get(TakeoffRun, takeoff_id)
    if run is None:
        raise HTTPException(404, "takeoff not found")
    return run


def _completed(run: TakeoffRun) -> dict:
    if run.status != "COMPLETED" or not run.result_json:
        raise HTTPException(409, f"takeoff is {run.status.lower()}")
    return run.result_json


def _takeoff_out(run: TakeoffRun) -> TakeoffOut:
    result = run.result_json or {}
    overrides = run.overrides_json or {}
    sheets = []
    for document_id, document in result.get("documents", {}).items():
        for sheet in document["sheets"]:
            sheets.append(TakeoffSheetSummaryOut(
                document_id=document_id,
                filename=document["filename"],
                page=sheet["page"],
                kind=sheet["kind"],
                title=sheet["title"],
                scale=sheet["scale"],
                run_count=len(sheet["runs"]),
                length_m=view.sheet_length(document_id, sheet, overrides),
            ))
    return TakeoffOut(
        id=run.id,
        project_id=run.project_id,
        status=run.status,
        error=run.error,
        progress=TakeoffProgressOut(**run.progress_json) if run.progress_json else None,
        sheets=sheets,
        systems=[SystemTotalOut(**s) for s in view.systems_summary(result, overrides)],
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _sheet_out(run: TakeoffRun, document_id: str, page: int) -> TakeoffSheetOut:
    result = _completed(run)
    sheet = view.find_plan_sheet(result, document_id, page)
    if sheet is None:
        raise HTTPException(404, "no takeoff for this sheet - only plan sheets are measured")
    overrides = run.overrides_json or {}
    key = view.sheet_key(document_id, page)
    return TakeoffSheetOut(
        takeoff_id=run.id,
        document_id=document_id,
        filename=result["documents"][document_id]["filename"],
        page=page,
        title=sheet["title"],
        scale=sheet["scale"],
        width=sheet["width"],
        height=sheet["height"],
        image_url=f"/api/documents/{document_id}/pages/{page}.png?max_side={SHEET_IMAGE_MAX_SIDE}",
        runs=[TakeoffRunOut(**r) for r in sheet["runs"]],
        overrides=overrides.get(key, {}),
        spec_m=view.spec_lengths(result),
        other_sheets_m=view.measured_by_system(result, overrides, skip=key),
    )


@router.post("/projects/{project_id}/takeoff", response_model=TakeoffOut, status_code=202)
def start_takeoff(project_id: str, session: Session = Depends(get_session)):
    if session.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    if not session.query(Document).filter_by(project_id=project_id, type="DRAWING").count():
        raise HTTPException(422, "upload a drawing first")
    latest = _latest(session, project_id)
    if latest is not None and latest.status == "RUNNING":
        raise HTTPException(409, "takeoff already running for this project")
    run = TakeoffRun(project_id=project_id)
    session.add(run)
    session.commit()
    dispatch_takeoff(project_id, run.id)
    return _takeoff_out(run)


@router.get("/projects/{project_id}/takeoff", response_model=TakeoffOut)
def get_takeoff(project_id: str, session: Session = Depends(get_session)):
    if session.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    run = _latest(session, project_id)
    if run is None:
        raise HTTPException(404, "no takeoff has been started for this project")
    return _takeoff_out(run)


@router.get("/takeoffs/{takeoff_id}/sheets/{document_id}/{page}", response_model=TakeoffSheetOut)
def get_takeoff_sheet(takeoff_id: str, document_id: str, page: int,
                      session: Session = Depends(get_session)):
    return _sheet_out(_run_or_404(session, takeoff_id), document_id, page)


@router.put("/takeoffs/{takeoff_id}/sheets/{document_id}/{page}/overrides",
            response_model=TakeoffSheetOut)
def put_takeoff_overrides(takeoff_id: str, document_id: str, page: int,
                          payload: TakeoffOverridesIn, session: Session = Depends(get_session)):
    run = _run_or_404(session, takeoff_id)
    result = _completed(run)
    sheet = view.find_plan_sheet(result, document_id, page)
    if sheet is None:
        raise HTTPException(404, "no takeoff for this sheet - only plan sheets are measured")
    try:
        clean = view.validate_overrides(sheet, payload.overrides, view.known_systems(result))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    key = view.sheet_key(document_id, page)
    others = {k: v for k, v in (run.overrides_json or {}).items() if k != key}
    # a new dict, not an in-place edit: the JSON column only notices reassignment
    run.overrides_json = {**others, key: clean} if clean else others
    session.commit()
    return _sheet_out(run, document_id, page)


@router.get("/takeoffs/{takeoff_id}/export.xlsx")
def export_takeoff(takeoff_id: str, session: Session = Depends(get_session)):
    run = _run_or_404(session, takeoff_id)
    rows = view.export_rows(_completed(run), run.overrides_json or {})
    with tempfile.TemporaryDirectory(prefix="foreman_xlsx_") as tmp:
        path = write_xlsx(Path(tmp) / "takeoff.xlsx", "Воздуховоды", EXPORT_HEADER, rows,
                          total_columns=["Длина, м"])
        data = path.read_bytes()
    filename = quote("ведомость-воздуховодов.xlsx")
    return Response(
        content=data,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition":
                 f"attachment; filename=takeoff.xlsx; filename*=UTF-8''{filename}"},
    )
