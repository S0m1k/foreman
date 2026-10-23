"""API request/response schemas."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str


class ProjectOut(BaseModel):
    id: str
    name: str
    created_at: dt.datetime
    updated_at: dt.datetime
    document_count: int = 0
    finding_count: int = 0
    analysis_status: str | None = None


class DocumentOut(BaseModel):
    id: str
    project_id: str
    type: str
    filename: str
    page_count: int
    status: str
    created_at: dt.datetime


class StageOut(BaseModel):
    stage: str
    status: str
    duration: float | None = None
    note: str | None = None


class AnalysisOut(BaseModel):
    id: str
    project_id: str
    status: str
    error: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    stages: list[StageOut] = []
    started_at: dt.datetime
    finished_at: dt.datetime | None = None


class EvidenceOut(BaseModel):
    document_id: str
    page: int
    bbox: list[float] | None = None
    snippet: str | None = None
    crop_path: str | None = None
    document_filename: str | None = None


class ValueOut(BaseModel):
    value: float | None = None
    unit: str | None = None
    raw: str | None = None
    display: str | None = None


class FindingOut(BaseModel):
    id: str
    project_id: str
    type: str
    severity: str
    status: str
    entity: str
    parameter: str | None = None
    drawing_value: ValueOut | None = None
    specification_value: ValueOut | None = None
    drawing_evidence: EvidenceOut | None = None
    specification_evidence: EvidenceOut | None = None
    explanation: str
    confidence: float
    extraction_confidence: float
    matching_confidence: float
    created_at: dt.datetime


# --- duct takeoff ----------------------------------------------------------


class TakeoffProgressOut(BaseModel):
    step: str  # classify | spec | measure
    done: int
    total: int
    document: str | None = None


class TakeoffSheetSummaryOut(BaseModel):
    document_id: str
    filename: str
    page: int
    kind: str  # plan | schematic | specification | other
    title: str | None = None
    scale: int | None = None
    run_count: int = 0
    length_m: float = 0.0


class SystemTotalOut(BaseModel):
    system: str
    measured_m: float
    spec_m: float | None = None


class TakeoffOut(BaseModel):
    id: str
    project_id: str
    status: str  # RUNNING | COMPLETED | FAILED
    error: str | None = None
    progress: TakeoffProgressOut | None = None
    sheets: list[TakeoffSheetSummaryOut] = []
    systems: list[SystemTotalOut] = []
    started_at: dt.datetime
    finished_at: dt.datetime | None = None


class TakeoffRunOut(BaseModel):
    id: int
    system: str | None = None
    confidence: str
    section: str | None = None
    width_mm: int | None = None
    insulated: bool
    length_m: float
    p0: list[float]
    p1: list[float]


class TakeoffSheetOut(BaseModel):
    takeoff_id: str
    document_id: str
    filename: str
    page: int
    title: str | None = None
    scale: int | None = None
    width: float
    height: float
    image_url: str
    runs: list[TakeoffRunOut]
    overrides: dict[str, str]
    spec_m: dict[str, float]
    # each system's length on the project's other plan sheets, edits applied,
    # so the screen can show live project totals while this sheet is edited
    other_sheets_m: dict[str, float]


class TakeoffOverridesIn(BaseModel):
    overrides: dict[str, str] = Field(max_length=10_000)
