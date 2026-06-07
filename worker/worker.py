from __future__ import annotations

from app.core.settings import get_settings


class LocalCeleryApp:
    """Import-safe Celery stand-in for tests and key-less local demos.

    The real Celery app is used when the dependency is installed. This fallback
    only keeps ``import worker.tasks`` working in environments without the Phase 3
    worker dependencies; it cannot dispatch. ``.delay``/``.s`` therefore raise
    rather than silently running work in-process or returning a fake signature.
    """

    def task(self, *args: object, **kwargs: object):
        del args, kwargs

        def decorator(func):
            def _unavailable(*_a: object, **_kw: object):
                raise RuntimeError(
                    "Celery is not installed; worker dispatch is unavailable in this environment."
                )

            func.delay = _unavailable
            func.s = _unavailable
            return func

        return decorator


def create_celery_app():
    settings = get_settings()
    try:
        from celery import Celery
    except ImportError:
        return LocalCeleryApp()

    app = Celery(
        "intellidocs_ai",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["worker.tasks"],
    )
    app.conf.update(
        task_track_started=True,
        task_time_limit=300,
        task_soft_time_limit=240,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        result_expires=3600,
    )
    return app


celery_app = create_celery_app()
