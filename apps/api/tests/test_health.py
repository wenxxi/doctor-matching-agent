from fastapi.testclient import TestClient

import app.main as main
from app.database import get_database_url, get_engine
from app.main import app


client = TestClient(app)


def test_app_health_does_not_require_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_database_url.cache_clear()
    get_engine.cache_clear()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_db_health_fails_gracefully_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_database_url.cache_clear()
    get_engine.cache_clear()

    response = client.get("/db/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "detail": "DATABASE_URL is not configured",
    }


def test_db_health_returns_database_status(monkeypatch):
    monkeypatch.setattr(
        main,
        "check_database_connection",
        lambda: {"status": "ok", "database": "connected"},
    )

    response = client.get("/db/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
