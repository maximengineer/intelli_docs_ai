from app.api.routes_health import health, ready


def test_health_and_ready_contracts() -> None:
    assert health() == {"status": "alive"}

    payload = ready()

    assert payload["status"] in {"ready", "not_ready"}
    assert "database" in payload["checks"]
    assert "vector_store" in payload["checks"]
    assert payload["vector_store_backend"] in {"memory", "postgres"}
