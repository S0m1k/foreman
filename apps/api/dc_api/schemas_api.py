"""API request/response schemas."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


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
