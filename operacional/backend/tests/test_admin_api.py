"""Unauthorized callers cannot enumerate users or alter store permission rules."""
from fastapi.testclient import TestClient
from app.main import app


def test_admin_endpoints_require_authenticated_identity():
    client = TestClient(app)
    routes = [
        ("/api/v1/admin/users", "get", None),
        ("/api/v1/admin/local-users", "post", {
            "username":"test-user", "display_name":"Test User", "profile":"seller",
            "store_code":"JOINVILLE"
        }),
        ("/api/v1/admin/users/00000000-0000-0000-0000-000000000001/reset-password","post",{}),
        ("/api/v1/admin/users/00000000-0000-0000-0000-000000000001","delete",{}),
        ("/api/v1/admin/invitations", "get", None),
        ("/api/v1/admin/invitations", "post", {"email": "worker@example.test", "display_name": "Worker", "profile": "seller", "store_code": "JOINVILLE"}),
        ("/api/v1/admin/users", "post", {"auth_subject": "x", "display_name": "Test", "profile": "seller", "store_code": "JOINVILLE"}),
        ("/api/v1/admin/groups", "get", None),
        ("/api/v1/admin/audit", "get", None),
        ("/api/v1/admin/groups/00000000-0000-0000-0000-000000000001/permissions", "put", {"permissions": ["sales.view"]}),
    ]
    for url, method, data in routes:
        response = client.request(method.upper(), url, json=data) if data is not None else client.request(method.upper(), url)
        assert response.status_code == 401, (method, url, response.text)
