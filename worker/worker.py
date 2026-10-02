from __future__ import annotations

from app.core.settings import get_settings
from celery import Celery


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "intellidocs_ai",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["worker.tasks"],
    )
    app.conf.update(
        task_track_started=True,
        # Same limits the document tasks declare, so no task (e.g. the chord
        # errback) runs under a different, hardcoded budget.
        task_time_limit=settings.celery_task_time_limit_seconds,
        task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        result_expires=3600,
    )
    return app


celery_app = create_celery_app()
