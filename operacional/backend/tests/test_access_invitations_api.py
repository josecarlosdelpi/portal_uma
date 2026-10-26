"""Prepared access invitations: role scoping, audit and no credential issuance."""
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import get_db
from app.main import app
from app.models import AccessInvitation, AuditEvent, Base, Store, StoreGroup, User


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        for store in ("JOINVILLE", "TUBARAO", "ITAJAI"):
            db.add(Store(code=store, name=store))
        superadmin = User(
            id=uuid4(), auth_subject="trusted-oidc-superadmin",
            display_name="Owner", profile="administrator",
            is_superadmin=True, active=True,
        )
        normal = User(
            id=uuid4(), auth_subject="trusted-oidc-manager",
            display_name="Manager", profile="administrator",
            is_superadmin=False, active=True,
        )
        db.add_all([superadmin, normal])
        db.flush()
        db.add_all([
            StoreGroup(id=uuid4(), store_code=code, name=code, active=True)
            for code in ("JOINVILLE", "TUBARAO", "ITAJAI")
        ])
        db.commit()
    identity = {"user": superadmin}

    def actor():
        return identity["user"]

    def session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[current_user] = actor
    app.dependency_overrides[get_db] = session
    try:
        with TestClient(app) as client:
            yield client, identity, engine, superadmin, normal
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_prepare_invitation_never_creates_login_or_sends_password(env):
    client, identity, engine, superadmin, _ = env
    route = "/api/v1/admin/invitations"
    created = client.post(route, json={
        "email": "  Pessoa.Exemplo@Example.Test ",
        "display_name": "Pessoa Exemplo",
        "profile": "seller", "store_code": "JOINVILLE",
    })
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["email"] == "pessoa.exemplo@example.test"
    assert record["status"] == "prepared"
    assert record["delivery"] == "not_configured"
    assert record["profile"] == "seller"
    assert record["store_code"] == "JOINVILLE"
    assert record["revision"] == 1
    assert "password" not in record and "token" not in record
    assert len(client.get(route).json()) == 1
    assert client.post(route, json={
        "email": "pessoa.exemplo@example.test",
        "display_name": "Duplicado", "profile": "seller",
        "store_code": "TUBARAO",
    }).status_code == 409
    with Session(engine) as db:
        assert len(db.scalars(select(AccessInvitation)).all()) == 1
        assert len(db.scalars(select(User)).all()) == 2
        actions = [item.action for item in db.scalars(select(AuditEvent)).all()]
        assert actions == ["access.invitation.prepared"]


def test_cancel_and_reprepare_are_audited_and_not_deletions(env):
    client, identity, engine, _, _ = env
    route = "/api/v1/admin/invitations"
    saved = client.post(route, json={
        "email": "worker@example.test", "display_name": "Worker",
        "profile": "seller", "store_code": "ITAJAI",
    }).json()
    url = route + "/" + saved["id"]
    assert client.request("DELETE", url, json={"expected_revision": 2}).status_code == 409
    response = client.request("DELETE", url, json={"expected_revision": 1})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert response.json()["revision"] == 2
    assert client.request("DELETE", url, json={"expected_revision": 2}).status_code == 409
    revived = client.post(route, json={
        "email": "WORKER@EXAMPLE.TEST", "display_name": "Gestora",
        "profile": "administrator", "store_code": None,
    })
    assert revived.status_code == 201, revived.text
    assert revived.json()["id"] == saved["id"]
    assert revived.json()["status"] == "prepared"
    assert revived.json()["revision"] == 3
    assert revived.json()["store_code"] is None
    with Session(engine) as db:
        assert len(db.scalars(select(AccessInvitation)).all()) == 1
        events=[a.action for a in db.scalars(select(AuditEvent)).all()]
        assert events == [
            "access.invitation.prepared", "access.invitation.cancelled",
            "access.invitation.reopened",
        ]


@pytest.mark.parametrize("payload", [
    {"email": "semarroba", "display_name": "Teste Pessoa",
     "profile": "seller", "store_code": "JOINVILLE"},
    {"email": "alguem@example.test", "display_name": "Teste Pessoa",
     "profile": "seller", "store_code": None},
    {"email": "alguem@example.test", "display_name": "Teste Pessoa",
     "profile": "administrator", "store_code": "JOINVILLE"},
    {"email": "alguem@example.test", "display_name": "Teste Pessoa",
     "profile": "superadmin", "store_code": None},
])
def test_invalid_invitation_is_rejected(env, payload):
    client, _, engine, _, _ = env
    result = client.post("/api/v1/admin/invitations",json=payload)
    assert result.status_code == 422, result.text
    with Session(engine) as db:
        assert db.scalars(select(AccessInvitation)).first() is None


def test_sent_invitation_cannot_be_cancelled_as_a_draft(env):
    client, identity, engine, _, _ = env
    base = "/api/v1/admin/invitations"
    prepared = client.post(base, json={
        "email": "future@example.test",
        "display_name": "Future User", "profile": "seller",
        "store_code": "JOINVILLE",
    }).json()
    with Session(engine) as db:
        row = db.get(AccessInvitation, UUID(prepared["id"]))
        # Future provider integration may move the invitation to "sent".
        row.status = "sent"
        db.commit()
    attempt = client.request(
        "DELETE", base + "/" + prepared["id"],
        json={"expected_revision": prepared["revision"]},
    )
    assert attempt.status_code == 409
    recreate = client.post(base, json={
        "email": "future@example.test",
        "display_name": "Different", "profile": "administrator",
        "store_code": None,
    })
    assert recreate.status_code == 409
    with Session(engine) as db:
        assert db.get(AccessInvitation, UUID(prepared["id"])).status == "sent"


def test_only_superadmin_can_administer_invitations(env):
    client, identity, _, superadmin, other = env
    base = "/api/v1/admin/invitations"
    identity["user"] = other
    assert client.get(base).status_code == 403
    assert client.post(base, json={
        "email": "seller@example.test", "display_name": "Seller",
        "profile": "seller", "store_code": "JOINVILLE",
    }).status_code == 403
    identity["user"] = superadmin
    invite = client.post(base, json={
        "email": "seller@example.test", "display_name": "Seller",
        "profile": "seller", "store_code": "JOINVILLE",
    }).json()
    identity["user"] = other
    assert client.request("DELETE",base+"/"+invite["id"],json={
        "expected_revision": 1
    }).status_code == 403


def test_invitations_require_authentication():
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/invitations").status_code == 401
        assert client.post("/api/v1/admin/invitations", json={
            "email":"worker@example.test","display_name":"Worker",
            "profile":"seller","store_code":"JOINVILLE",
        }).status_code == 401
