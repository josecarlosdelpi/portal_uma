"""Daily tasks: ownership, editing, audit, and tenant isolation without ERP."""
from datetime import date
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
    AuditEvent, Base, DailyTask, GroupMembership, GroupPermission,
    Store, StoreGroup, User,
)


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        for code in ("JOINVILLE", "TUBARAO", "ITAJAI"):
            db.add(Store(code=code, name=code))
        admin = User(
            id=uuid4(), auth_subject="daily-admin", display_name="Admin",
            profile="administrator", is_superadmin=False, active=True
        )
        joi = User(
            id=uuid4(), auth_subject="daily-joi", display_name="Vendedor Joi",
            profile="seller", is_superadmin=False, active=True
        )
        tub = User(
            id=uuid4(), auth_subject="daily-tub", display_name="Vendedor Tub",
            profile="seller", is_superadmin=False, active=True
        )
        db.add_all([admin, joi, tub])
        db.flush()
        for code, seller in (("JOINVILLE", joi), ("TUBARAO", tub)):
            group = StoreGroup(id=uuid4(), store_code=code, name=code, active=True)
            db.add(group)
            db.flush()
            db.add(GroupMembership(user_id=seller.id, group_id=group.id))
            db.add(GroupPermission(group_id=group.id, code="daily_tasks.view", granted=True))
        db.commit()
    actor = {"user": admin}
    app.dependency_overrides[current_user] = lambda: actor["user"]
    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = session
    try:
        with TestClient(app) as client:
            yield client, actor, engine, admin, joi, tub
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_create_edit_complete_reopen_delete_and_audit(env):
    c, actor, engine, admin, joi, _ = env
    url = "/api/v1/daily-tasks/JOINVILLE"
    initial = c.get(url + "/2026-10-26")
    assert initial.status_code == 200
    assert initial.json()["summary"]["total"] == 0

    body = {
        "date": "2026-10-26", "title": "Conferir atendimento do dia",
        "details": "Verificar retornos pendentes",
        "priority": "alta", "assignee_id": str(joi.id),
    }
    created = c.post(url, json=body)
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["status"] == "pendente" and item["revision"] == 1
    assert item["assignee"] == "Vendedor Joi"
    assert item["priority"] == "alta"
    uid = item["id"]

    listing = c.get(url + "/2026-10-26").json()
    assert listing["summary"] == {
        "total": 1, "pending": 1, "in_progress": 0, "completed": 0
    }
    status_url = url + "/" + uid
    outdated = c.put(status_url, json={
        **body, "status": "concluida", "expected_revision": 0
    })
    assert outdated.status_code == 422
    updated = c.put(status_url, json={
        **body, "status": "concluida", "expected_revision": 1
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["completed_at"] is not None
    assert c.get(url + "/2026-10-26").json()["summary"]["completed"] == 1
    assert c.put(status_url, json={
        **body, "status": "pendente", "expected_revision": 1
    }).status_code == 409
    reopened = c.put(status_url, json={
        **body, "date": "2026-10-27", "status": "em_andamento", "expected_revision": 2
    })
    assert reopened.status_code == 200
    assert reopened.json()["completed_at"] is None
    assert c.get(url + "/2026-10-26").json()["summary"]["total"] == 0
    assert c.get(url + "/2026-10-27").json()["summary"]["in_progress"] == 1

    assert c.request("DELETE", status_url, json={"expected_revision": 1}).status_code == 409
    removed = c.request("DELETE", status_url, json={"expected_revision": 3})
    assert removed.status_code == 200, removed.text
    assert removed.json()["deleted"] is True
    assert c.get(url + "/2026-10-27").json()["items"] == []
    assert c.put(status_url, json={**body, "status": "pendente",
                                   "expected_revision": 4}).status_code == 404
    with Session(engine) as db:
        record = db.get(DailyTask, __import__("uuid").UUID(uid))
        assert record.deleted_at is not None
        events = [row.action for row in db.scalars(select(AuditEvent))]
        assert events[-4:] == [
            "daily_task.created", "daily_task.updated",
            "daily_task.updated", "daily_task.deleted"
        ]


def test_store_scope_assignee_validation_and_read_only_sellers(env):
    c, actor, engine, admin, joi, tub = env
    url = "/api/v1/daily-tasks/JOINVILLE"
    body = {
        "date": "2026-10-26", "title": "Rever demandas pendentes",
        "priority": "normal", "assignee_id": str(tub.id),
    }
    assert c.post(url, json=body).status_code == 422
    created = c.post(url, json={**body, "assignee_id": str(joi.id)})
    assert created.status_code == 201
    task_id = created.json()["id"]
    actor["user"] = joi
    assert c.get(url + "/2026-10-26").status_code == 200
    assert c.get("/api/v1/daily-tasks/TUBARAO/2026-10-26").status_code == 403
    assert c.post(url, json={**body, "assignee_id": str(joi.id)}).status_code == 403
    assert c.put(url + "/" + task_id, json={
        **body, "assignee_id": str(joi.id),
        "status": "concluida", "expected_revision": 1,
    }).status_code == 403
    assert c.request("DELETE", url + "/" + task_id,
                     json={"expected_revision": 1}).status_code == 403
    actor["user"] = tub
    assert c.get(url + "/2026-10-26").status_code == 403
    assert c.get("/api/v1/daily-tasks/TUBARAO/2026-10-26").json()["items"] == []
    actor["user"] = admin
    assert c.put("/api/v1/daily-tasks/TUBARAO/" + task_id,json={
        **body, "status": "concluida", "expected_revision": 1,
    }).status_code == 404
    assert c.request("DELETE", "/api/v1/daily-tasks/TUBARAO/"+task_id,
                     json={"expected_revision":1}).status_code == 404
    assert c.get("/api/v1/daily-tasks/INEXISTENTE/2026-10-26").status_code == 404


def test_reject_invalid_dates_and_unknown_fields(env):
    c, *_ = env
    url = "/api/v1/daily-tasks/JOINVILLE"
    assert c.get(url + "/2019-01-01").status_code == 422
    assert c.post(url, json={
        "date": "2026-10-26", "title": "OK", "priority": "alta"
    }).status_code == 422
    assert c.post(url, json={
        "date": "2026-10-26", "title": "Tarefa válida",
        "priority": "urgente"
    }).status_code == 422
    assert c.post(url, json={
        "date": "2026-10-26", "title": "Tarefa válida",
        "priority": "normal", "admin_override": True
    }).status_code == 422


def test_daily_tasks_authentication_required():
    with TestClient(app) as c:
        assert c.get("/api/v1/daily-tasks/JOINVILLE/2026-10-26").status_code == 401
        assert c.post("/api/v1/daily-tasks/JOINVILLE", json={
            "date":"2026-10-26","title":"Teste protegido"
        }).status_code == 401
