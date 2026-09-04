"""Celery application for the analysis worker."""

from __future__ import annotations

from celery import Celery
from dc_api.settings import settings

app = Celery(
    "foreman",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # analyses are long; one at a time per worker
    broker_connection_retry_on_startup=True,
)
app.autodiscover_tasks(["dc_worker"])
