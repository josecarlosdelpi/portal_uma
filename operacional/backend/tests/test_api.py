"""The API must not grant access with fake or missing credentials."""
from fastapi.testclient import TestClient

from app.main import app


def test_health_does_not_require_login():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_protected_endpoints_reject_anonymous_callers():
    client = TestClient(app)
    for endpoint in ["/api/v1/me", "/api/v1/stores", "/api/v1/access/JOINVILLE/sales.view"]:
        assert client.get(endpoint).status_code == 401
