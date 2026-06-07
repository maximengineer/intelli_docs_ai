from app.api import routes_health
from app.api.routes_health import health, ready
from app.core.settings import get_settings


def test_health_and_ready_contracts() -> None:
    assert health() == {"status": "alive"}

    payload = ready()

    assert payload["status"] in {"ready", "not_ready"}
    assert "database" in payload["checks"]
    assert "vector_store" in payload["checks"]
    assert payload["vector_store_backend"] in {"memory", "postgres"}


def test_celery_ready_requires_worker(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMENT_PROCESSING_BACKEND", "celery")
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("REQUIRE_DATABASE_READY", "true")
    monkeypatch.setattr(routes_health, "check_database_ready", lambda database_url: True)
    monkeypatch.setattr(routes_health, "ensure_pgvector_schema", lambda *args, **kwargs: True)
    monkeypatch.setattr(routes_health, "_check_tcp_url", lambda url: True)
    monkeypatch.setattr(routes_health, "_check_celery_worker", lambda broker, backend: False)
    get_settings.cache_clear()
    try:
        payload = ready()
    finally:
        get_settings.cache_clear()

    assert payload["status"] == "not_ready"
    assert payload["checks"]["celery_worker"] is False


def test_celery_ready_passes_when_worker_responds(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMENT_PROCESSING_BACKEND", "celery")
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("REQUIRE_DATABASE_READY", "true")
    monkeypatch.setattr(routes_health, "check_database_ready", lambda database_url: True)
    monkeypatch.setattr(routes_health, "ensure_pgvector_schema", lambda *args, **kwargs: True)
    monkeypatch.setattr(routes_health, "_check_tcp_url", lambda url: True)
    monkeypatch.setattr(routes_health, "_check_celery_worker", lambda broker, backend: True)
    get_settings.cache_clear()
    try:
        payload = ready()
    finally:
        get_settings.cache_clear()

    assert payload["status"] == "ready"
    assert payload["checks"]["celery_worker"] is True


def test_celery_ready_rejects_memory_state_backend(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMENT_PROCESSING_BACKEND", "celery")
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "memory")
    monkeypatch.setattr(routes_health, "_check_tcp_url", lambda url: True)
    monkeypatch.setattr(routes_health, "_check_celery_worker", lambda broker, backend: True)
    get_settings.cache_clear()
    try:
        payload = ready()
    finally:
        get_settings.cache_clear()

    assert payload["status"] == "not_ready"
    assert payload["checks"]["config"] is False
