import logging
import socket
from urllib.parse import urlparse

from fastapi import APIRouter

from app.core.settings import get_settings
from app.storage.database import check_database_ready, ensure_pgvector_schema

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def ready() -> dict[str, object]:
    settings = get_settings()
    database = check_database_ready(settings.database_url)
    vector_store = True
    if settings.vector_store_backend == "postgres":
        try:
            vector_store = bool(
                settings.database_url
                and database
                and ensure_pgvector_schema(
                    settings.database_url,
                    dimension=settings.postgres_vector_dimension,
                    operator_class=settings.postgres_vector_operator_class,
                    index_type=settings.postgres_vector_index_type,
                )
            )
        except Exception:
            logger.warning("vector_store_readiness_check_failed", exc_info=True)
            vector_store = False
    config = not (
        settings.document_processing_backend == "celery"
        and settings.vector_store_backend != "postgres"
    )
    checks = {
        "config": config,
        "database": database,
        "vector_store": vector_store,
    }
    if settings.document_processing_backend == "celery":
        checks["celery_broker"] = _check_tcp_url(settings.celery_broker_url)
        checks["celery_result_backend"] = _check_tcp_url(settings.celery_result_backend)
        checks["celery_worker"] = (
            _check_celery_worker(settings.celery_broker_url, settings.celery_result_backend)
            if checks["celery_broker"] and checks["celery_result_backend"]
            else False
        )
    database_ready = checks["database"] or not settings.require_database_ready
    runtime_ready = all(value for name, value in checks.items() if name not in {"database"})
    is_ready = runtime_ready and database_ready
    return {
        "status": "ready" if is_ready else "not_ready",
        "checks": checks,
        "database_required": settings.require_database_ready,
        "vector_store_backend": settings.vector_store_backend,
    }


def _check_tcp_url(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.hostname:
        return False
    port = parsed.port or (6379 if parsed.scheme == "redis" else None)
    if port is None:
        return False
    try:
        with socket.create_connection((parsed.hostname, port), timeout=2.0):
            return True
    except OSError:
        logger.warning("tcp_readiness_check_failed url=%s", url)
        return False


def _check_celery_worker(broker_url: str, result_backend: str) -> bool:
    try:
        from celery import Celery

        celery_app = Celery("intellidocs_readiness", broker=broker_url, backend=result_backend)
        replies = celery_app.control.inspect(timeout=1.0).ping() or {}
        return bool(replies)
    except Exception:
        logger.warning("celery_worker_readiness_check_failed", exc_info=True)
        return False
