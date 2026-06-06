import logging

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
    checks = {
        "config": True,
        "database": database,
        "vector_store": vector_store,
    }
    database_ready = checks["database"] or not settings.require_database_ready
    is_ready = checks["config"] and checks["vector_store"] and database_ready
    return {
        "status": "ready" if is_ready else "not_ready",
        "checks": checks,
        "database_required": settings.require_database_ready,
        "vector_store_backend": settings.vector_store_backend,
    }
