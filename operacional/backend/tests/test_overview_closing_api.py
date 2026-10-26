"""Public API invariants for management overview and 7-slide archive workflows."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import get_db
from app.main import app
from app.models import (
    AuditEvent, Base, GroupMembership, GroupPermission, MonthlyClosingArchive,
    Store, StoreGroup, User,
)


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        for code in ("JOINVILLE", "ITAJAI", "TUBARAO"):
            session.add(Store(code=code, name=code))
        admin = User(id=uuid4(), auth_subject="admin-test", display_name="Admin",
                     profile="administrator", active=True, is_superadmin=False)
        seller = User(id=uuid4(), auth_subject="seller-test", display_name="Vendedor",
                      profile="seller", active=True, is_superadmin=False)
        no_overview = User(id=uuid4(), auth_subject="seller-no-overview",
                           display_name="Vendedor Restrito", profile="seller",
                           active=True, is_superadmin=False)
        session.add_all([admin, seller, no_overview])
        session.flush()
        group = StoreGroup(id=uuid4(), name="Joinville", store_code="JOINVILLE", active=True)
        session.add(group)
        session.flush()
        session.add_all([
            GroupMembership(user_id=seller.id, group_id=group.id),
            GroupMembership(user_id=no_overview.id, group_id=group.id),
            GroupPermission(group_id=group.id, code="overview.view", granted=True),
            GroupPermission(group_id=group.id, code="monthly_closing.view", granted=True),
        ])
        session.commit()

    actor = {"user": admin}

    def db_override():
        with Session(engine) as db:
            yield db

    def actor_override():
        return actor["user"]

    app.dependency_overrides[current_user] = actor_override
    app.dependency_overrides[get_db] = db_override
    try:
        with TestClient(app) as client:
            yield client, actor, engine, admin, seller, no_overview
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def base_content():
    return {
        "opening": "Agradecimento ao time",
        "stores": {"JOINVILLE": "Boa evolução", "TUBARAO": "", "ITAJAI": ""},
        "opportunities": "Aprimorar retorno aos clientes",
        "wins": "Rotina mais organizada",
        "improvements": "Registrar próximos passos",
        "notices": "Revisar calendário",
        "notes": {"JOINVILLE": "", "TUBARAO": "", "ITAJAI": ""},
        "priorities": [],
    }


def priority(index):
    return {
        "id": f"p-{index}", "what": f"Ação {index}", "owner": "Gestão",
        "scope": "all", "due": "2026-11-15", "status": "pendente",
    }


def test_consolidated_overview_hides_sales_without_erp(env):
    client, *_ = env
    out = client.get("/api/v1/overview/2026/10")
    assert out.status_code == 200, out.text
    data = out.json()
    assert data["scope"] == "consolidated"
    assert {s["code"] for s in data["stores"]} == {"ITAJAI", "JOINVILLE", "TUBARAO"}
    assert data["summary"]["monthly_target"] is None
    assert data["summary"]["revenue"] is None
    assert data["source"]["sales_updated_at"] is None
    assert all(s["attainment_percent"] is None for s in data["stores"])


def test_seller_overview_only_their_store_without_target_permission(env):
    client, actor, _, _, seller, _ = env
    actor["user"] = seller
    data = client.get("/api/v1/overview/2026/10").json()
    assert data["scope"] == "store"
    assert [s["code"] for s in data["stores"]] == ["JOINVILLE"]
    assert data["stores"][0]["target_visibility"] == "restricted"
    assert data["stores"][0]["target"] is None
    assert client.get("/api/v1/monthly-closing/2026/10").status_code == 403
    assert client.get("/api/v1/monthly-closing/2026/10/archives").status_code == 403
    assert client.put("/api/v1/monthly-closing/2026/10", json={
        "draft": base_content(), "expected_revision": 0
    }).status_code == 403


def test_seller_missing_overview_permission_is_denied(env):
    client, actor, engine, _, _, restricted = env
    actor["user"] = restricted
    with Session(engine) as session:
        session.execute(GroupPermission.__table__.delete().where(
            GroupPermission.code == "overview.view"
        ))
        session.commit()
    assert client.get("/api/v1/overview/2026/10").status_code == 403


def test_closing_has_seven_slides_total_twenty_minutes(env):
    client, *_ = env
    response = client.get("/api/v1/monthly-closing/2026/10")
    assert response.status_code == 200
    data = response.json()
    assert data["durations"] == [1, 3, 5, 3, 2, 2, 4]
    assert sum(data["durations"]) == 20
    assert data["revision"] == 0
    assert data["draft"]["priorities"] == []
    assert data["data"]["total_target"] is None
    assert data["data"]["revenue"] is None
    assert data["sales_data_complete"] is False


def test_save_draft_requires_revision_and_archives_require_priorities(env):
    client, _, engine, *_ = env
    route = "/api/v1/monthly-closing/2026/10"
    content = base_content()
    first = client.put(route, json={"draft": content, "expected_revision": 0})
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == 1
    assert client.put(route, json={"draft": content, "expected_revision": 0}).status_code == 409
    assert client.post(route + "/archives", json={"expected_revision": 1}).status_code == 422
    content["priorities"] = [priority(1), priority(2), priority(3)]
    saved = client.put(route, json={"draft": content, "expected_revision": 1})
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 2

    archived = client.post(route + "/archives", json={"expected_revision": 2})
    assert archived.status_code == 201, archived.text
    a = archived.json()
    assert a["version"] == 1
    assert a["snapshot"]["state"] == "partial_sales_pending"
    assert a["snapshot"]["draft"]["opening"] == "Agradecimento ao time"
    assert a["snapshot"]["data"]["revenue"] is None
    assert a["snapshot"]["durations"] == [1, 3, 5, 3, 2, 2, 4]

    content["opening"] = "Mensagem revisada"
    revised = client.put(route, json={"draft": content, "expected_revision": 2})
    assert revised.status_code == 200
    second = client.post(route + "/archives", json={"expected_revision": 3})
    assert second.status_code == 201, second.text
    assert second.json()["version"] == 2

    # Archive #1 must not change after newer edits or archives.
    first_id = a["id"]
    frozen = client.get(route + "/archives/" + first_id)
    assert frozen.status_code == 200
    assert frozen.json()["snapshot"]["draft"]["opening"] == "Agradecimento ao time"
    assert client.get(route + "/archives").json()[0]["version"] == 2
    with Session(engine) as db:
        archives = db.scalars(select(MonthlyClosingArchive)).all()
        assert len(archives) == 2
        actions = [entry.action for entry in db.scalars(select(AuditEvent))]
        assert "closing.draft.updated" in actions
        assert "closing.archived" in actions


def test_previous_month_priorities_are_available(env):
    client, *_ = env
    october = base_content()
    october["priorities"] = [priority(i) for i in (1,2,3)]
    october["priorities"][1]["status"] = "concluida"
    assert client.put("/api/v1/monthly-closing/2026/10",json={
        "draft":october,"expected_revision":0
    }).status_code==200
    assert client.post("/api/v1/monthly-closing/2026/10/archives",json={
        "expected_revision":1
    }).status_code==201
    next_month = client.get("/api/v1/monthly-closing/2026/11").json()
    assert [x["id"] for x in next_month["previous_pending"]] == ["p-1","p-3"]


def test_invalid_content_and_five_priority_limit(env):
    client, *_ = env
    route="/api/v1/monthly-closing/2026/10"
    wrong=base_content()
    wrong["priorities"]=[priority(i) for i in range(1,7)]
    assert client.put(route,json={"draft":wrong,"expected_revision":0}).status_code==422
    wrong["priorities"]=[priority(1),priority(1)]
    assert client.put(route,json={"draft":wrong,"expected_revision":0}).status_code==422
    wrong=base_content()
    wrong["stores"]["OUTRA_LOJA"]="Visível"
    assert client.put(route,json={"draft":wrong,"expected_revision":0}).status_code==422
    wrong=base_content()
    wrong["opening"]="x"*2100
    assert client.put(route,json={"draft":wrong,"expected_revision":0}).status_code==422


def test_unauthenticated_requests_do_not_open_overview_or_closing():
    client=TestClient(app)
    assert client.get("/api/v1/overview/2026/10").status_code==401
    assert client.get("/api/v1/monthly-closing/2026/10").status_code==401
