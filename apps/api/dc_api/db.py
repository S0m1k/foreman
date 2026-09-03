"""Database models and session management (SQLAlchemy 2.0).

JSON columns keep the flexible parts (parameters, evidence) while everything
queried or filtered on lives in real columns.  The schema works identically on
PostgreSQL (production) and SQLite (local development/tests).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .settings import settings


def _uuid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _uuid("prj"))
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    documents: Mapped[list["Document"]] = relationship(back_populates="project")
    findings: Mapped[list["FindingRow"]] = relationship(back_populates="project")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _uuid("doc"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # DRAWING | SPECIFICATION
    filename: Mapped[str] = mapped_column(String(512))
    storage_path: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64), default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="UPLOADED")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="documents")
    pages: Mapped[list["Page"]] = relationship(back_populates="document")


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _uuid("page"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    width: Mapped[float] = mapped_column(Float, default=0)
    height: Mapped[float] = mapped_column(Float, default=0)
    text: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    needs_ocr: Mapped[int] = mapped_column(Integer, default=0)

    document: Mapped[Document] = relationship(back_populates="pages")


class EntityRow(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    page_id: Mapped[str | None] = mapped_column(ForeignKey("pages.id"), nullable=True)
    page_number: Mapped[int] = mapped_column(Integer)
    tag: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    data_json: Mapped[dict] = mapped_column(JSON, default=dict)  # parameters, quantity, context
    bbox_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(20), default="heuristic")


class FindingRow(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    entity_key: Mapped[str] = mapped_column(String(64))
    parameter: Mapped[str | None] = mapped_column(String(64), nullable=True)
    drawing_entity_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    spec_entity_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    drawing_evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    spec_evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    values_json: Mapped[dict] = mapped_column(JSON, default=dict)  # drawing/spec values
    explanation: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    matching_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="findings")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _uuid("run"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="ANALYSIS_STARTED")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stages_json: Mapped[list] = mapped_column(JSON, default=list)  # [{stage,status,duration}]
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VlmCache(Base):
    """Cache of VLM calls keyed by (document hash, page, model, prompt version)."""

    __tablename__ = "vlm_cache"

    cache_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --- engine / session ------------------------------------------------------

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Iterator:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
