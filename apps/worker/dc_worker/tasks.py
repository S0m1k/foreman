"""Celery tasks."""

from __future__ import annotations

from dc_api.db import init_db
from dc_api.pipeline import run_analysis

from .celery_app import app


@app.task(name="foreman.analyze_project")
def analyze_project(project_id: str, run_id: str) -> None:
    init_db()
    run_analysis(project_id, run_id)
