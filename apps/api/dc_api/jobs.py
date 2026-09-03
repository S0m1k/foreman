"""Job dispatch: inline thread for dev, Celery for docker-compose."""

from __future__ import annotations

import logging
import threading

from .settings import settings

logger = logging.getLogger(__name__)


def dispatch_analysis(project_id: str, run_id: str) -> None:
    if settings.job_backend == "celery":
        from dc_worker.tasks import analyze_project

        analyze_project.delay(project_id, run_id)
        return

    from .pipeline import run_analysis

    thread = threading.Thread(
        target=run_analysis, args=(project_id, run_id), name=f"analysis-{project_id}", daemon=True
    )
    thread.start()
