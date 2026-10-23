"""Full HTTP and database tests without any private ERP data or real tokens."""
from datetime import date
from decimal import Decimal
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
    AuditEvent, Base, GroupMembership, GroupPermission,
    Store, StoreGroup, User,
)


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        for code in ("JOINVILLE", "ITAJAI", "TUBARAO"):
            db.add(Store(code=code, name=code))
        admin = User(id=uuid4(), auth_subject="test-admin-oidc", display_name="Admin",
                     profile="administrator", active=True, is_superadmin=False)
        seller = User(id=uuid4(), auth_subject="test-seller-oidc", display_name="Seller",
                      profile="seller", active=True, is_superadmin=False)
        denied = User(id=uuid4(), auth_subject="test-denied-oidc", display_name="No module",
                      profile="seller", active=True, is_superadmin=False)
        db.add_all([admin, seller, denied])
        db.flush()
        group = StoreGroup(id=uuid4(), store_code="JOINVILLE", name="Joinville", active=True)
        db.add(group)
        db.flush()
        db.add_all([
            GroupMembership(user_id=seller.id, group_id=group.id),
            GroupMembership(user_id=denied.id, group_id=group.id),
            GroupPermission(group_id=group.id, code="targets.view", granted=True),
        ])
        db.commit()

    active_actor = {"current": admin}

    def db_override():
        with Session(engine) as db:
            yield db

    def user_override():
        return active_actor["current"]

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[current_user] = user_override
    try:
        with TestClient(app) as client:
            yield client, active_actor, engine, admin, seller, denied
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_denies_seller_cross_store_and_write(env):
    client, identity, _, _, seller, _ = env
    identity["current"] = seller
    current = client.get("/api/v1/targets/JOINVILLE/2026/10")
    assert current.status_code == 200
    assert current.json()["target"]["amount"] is None
    assert current.json()["sales"]["monthly_revenue"] is None
    assert client.get("/api/v1/targets/TUBARAO/2026/10").status_code == 403
    assert client.put("/api/v1/targets/JOINVILLE/2026/10/goal", json={
        "amount": "50000.00", "expected_revision": 0
    }).status_code == 403


def test_admin_can_write_goal_and_preserve_audit(env):
    client, identity, engine, admin, _, _ = env
    response = client.put("/api/v1/targets/JOINVILLE/2026/10/goal", json={
        "amount": "35000.00", "expected_revision": 0,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target"]["amount"] == "35000.00"
    assert body["target"]["revision"] == 1
    assert body["working_day_count"] == len(body["base_plan"])
    assert sum(Decimal(day["base_daily_target"]) for day in body["base_plan"]) == Decimal("35000.00")
    assert body["sales"]["status"] == "awaiting_official_import"
    assert body["sales"]["attainment_percent"] is None
    assert client.put("/api/v1/targets/JOINVILLE/2026/10/goal", json={
        "amount": "40000.00", "expected_revision": 0,
    }).status_code == 409
    with Session(engine) as session:
        events = session.scalars(select(AuditEvent)).all()
        assert len(events) == 1
        assert events[0].actor_id == admin.id
        assert events[0].action == "target.goal.updated"
        assert events[0].details["before"] is None
        assert events[0].details["after"] == "35000.00"


def test_revision_and_idempotency(env):
    client, *_ = env
    route = "/api/v1/targets/ITAJAI/2026/10/goal"
    initial = client.put(route, json={"amount": "100.00", "expected_revision": 0})
    assert initial.status_code == 200
    no_change = client.put(route, json={"amount": "100.00", "expected_revision": 1})
    assert no_change.status_code == 200
    assert no_change.json()["target"]["revision"] == 1
    changed = client.put(route, json={"amount": "101.00", "expected_revision": 1})
    assert changed.status_code == 200
    assert changed.json()["target"]["revision"] == 2


def test_daily_minimum_versioned_and_audited(env):
    client, _, engine, *_ = env
    route = "/api/v1/targets/ITAJAI/minimum"
    reply = client.put(route, json={"amount": "700.00", "expected_revision": 0})
    assert reply.status_code == 200
    assert reply.json()["revision"] == 1
    assert client.put(route, json={"amount": "800.00", "expected_revision": 0}).status_code == 409
    body = client.get("/api/v1/targets/ITAJAI/2026/10").json()
    assert body["minimum"]["amount"] == "700.00"
    assert body["sales"]["dynamic_day_plan"] is None
    with Session(engine) as session:
        logs = session.scalars(select(AuditEvent)).all()
        assert any(log.action == "target.minimum.updated" for log in logs)


def test_weekday_exclusions_per_store_and_audit(env):
    client, _, engine, *_ = env
    route = "/api/v1/targets/JOINVILLE/2026/10/calendar"
    bad = client.put(route, json={"days_off": ["2026-10-10"], "expected_revision": 0})
    assert bad.status_code == 422
    assert client.put(route, json={"days_off": ["2026-10-12","2026-10-12"],
                                    "expected_revision": 0}).status_code == 422
    response = client.put(route, json={"days_off": ["2026-10-12"], "expected_revision": 0})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target"]["revision"] == 1
    assert "2026-10-12" not in [day["date"] for day in body["base_plan"]]
    assert client.put(route, json={"days_off": ["2026-10-13"],
                                   "expected_revision": 0}).status_code == 409
    assert client.get("/api/v1/targets/TUBARAO/2026/10").json()["days_off"] == []
    with Session(engine) as session:
        assert any(log.action == "target.calendar.updated" for log in session.scalars(select(AuditEvent)))


def test_rejects_close_entire_month_with_existing_goal(env):
    client, *_ = env
    start = client.put("/api/v1/targets/JOINVILLE/2026/10/goal", json={
        "amount": "350.00", "expected_revision": 0,
    })
    assert start.status_code == 200
    dates = [date.fromisoformat(day["date"]) for day in start.json()["base_plan"]]
    route = "/api/v1/targets/JOINVILLE/2026/10/calendar"
    result = client.put(route, json={
        "days_off": [value.isoformat() for value in dates], "expected_revision": 1,
    })
    assert result.status_code == 422


@pytest.mark.parametrize("value", ["-5.00", "0.00", "NaN", "1.001", "1000000000000"])
def test_rejects_invalid_goal_values(env, value):
    client, *_ = env
    reply = client.put("/api/v1/targets/JOINVILLE/2026/10/goal", json={
        "amount": value, "expected_revision": 0,
    })
    assert reply.status_code == 422


def test_absent_permission_remains_restricted(env):
    client, identity, engine, _, _, denied = env
    identity["current"] = denied
    with Session(engine) as session:
        session.execute(GroupPermission.__table__.delete())
        session.commit()
    assert client.get("/api/v1/targets/JOINVILLE/2026/10").status_code == 403
    assert client.get("/api/v1/targets/UNKNOWN/2026/10").status_code == 404


def test_unknown_store_does_not_accept_writes(env):
    client, *_ = env
    reply = client.put("/api/v1/targets/UNKNOWN/2026/10/goal", json={
        "amount": "100.00", "expected_revision": 0,
    })
    assert reply.status_code == 404


def test_unauthenticated_call_remains_denied():
    client = TestClient(app)
    assert client.get("/api/v1/targets/JOINVILLE/2026/10").status_code == 401
