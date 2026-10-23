"""Background duct takeoff over a project's drawings."""

from __future__ import annotations

import logging

import pymupdf
from dc_extraction.takeoff import SpecSystem, parse_specification, run_album

from .db import Document, TakeoffRun, session_scope, utcnow
from .storage import get_storage

logger = logging.getLogger(__name__)

# Writing progress on every classified page of a 90-page album is noise.
_PROGRESS_EVERY = 10


class TakeoffError(Exception):
    pass


def _update(run_id: str, **fields) -> None:
    with session_scope() as session:
        run = session.get(TakeoffRun, run_id)
        if run is not None:
            for name, value in fields.items():
                setattr(run, name, value)


def _merge_specs(specs: list[dict[str, SpecSystem]]) -> dict[str, SpecSystem]:
    """A project's specification may be split across several files."""
    merged: dict[str, SpecSystem] = {}
    for spec in specs:
        for name, entry in spec.items():
            into = merged.setdefault(name, SpecSystem(name))
            into.length_m += entry.length_m
            for section, length in entry.sections.items():
                into.sections[section] = into.sections.get(section, 0.0) + length
            into.equipment.update(entry.equipment)
    return merged


def _spec_json(spec: dict[str, SpecSystem]) -> dict:
    return {
        name: {"length_m": round(entry.length_m, 2),
               "sections": {k: round(v, 2) for k, v in entry.sections.items()}}
        for name, entry in spec.items()
    }


def run_takeoff(project_id: str, run_id: str) -> None:
    """Measure every plan sheet of the project's drawings against its specification.

    The specification comes from uploaded SPECIFICATION files when there are
    any, otherwise from the specification sheets inside the drawings album.
    """
    logger.info("takeoff started: project=%s run=%s", project_id, run_id)
    storage = get_storage()
    try:
        with session_scope() as session:
            docs = session.query(Document).filter_by(project_id=project_id).all()
            drawings = [(d.id, d.filename, d.storage_path) for d in docs if d.type == "DRAWING"]
            specs = [d.storage_path for d in docs if d.type == "SPECIFICATION"]
        if not drawings:
            raise TakeoffError("Загрузите хотя бы один чертёж.")

        _update(run_id, progress_json={"step": "spec", "done": 0, "total": 1, "document": None})
        sources = specs or [path for _, _, path in drawings]
        parsed = []
        for key in sources:
            with pymupdf.open(storage.local_path(key)) as doc:
                parsed.append(parse_specification(doc))
        spec = _merge_specs(parsed)

        documents: dict[str, dict] = {}
        for document_id, filename, key in drawings:
            def report(step: str, done: int, total: int, name: str = filename) -> None:
                if step == "measure" or done == total or done % _PROGRESS_EVERY == 0:
                    _update(run_id, progress_json={"step": step, "done": done,
                                                   "total": total, "document": name})

            with pymupdf.open(storage.local_path(key)) as doc:
                album = run_album(doc, spec=spec, on_progress=report)
            documents[document_id] = {"filename": filename, "sheets": album.to_json()["sheets"]}

        _update(run_id, status="COMPLETED", progress_json=None, finished_at=utcnow(),
                result_json={"spec": _spec_json(spec), "documents": documents})
        logger.info("takeoff completed: run=%s", run_id)
    except Exception as exc:  # the run must end in a terminal state whatever happened
        logger.exception("takeoff failed: run=%s", run_id)
        message = str(exc) if isinstance(exc, TakeoffError) else f"Ошибка обработки: {exc}"
        _update(run_id, status="FAILED", error=message, progress_json=None, finished_at=utcnow())
