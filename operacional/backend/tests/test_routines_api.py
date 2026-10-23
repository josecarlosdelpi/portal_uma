"""Security and business-rule tests for ERP-independent weekly/marketing/training modules."""
from datetime import date
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import get_db
from app.main import app
from app.models import Base,Store,User,GroupMembership,GroupPermission,StoreGroup,AuditEvent


@pytest.fixture
def env():
    engine=create_engine("sqlite+pysqlite://",connect_args={"check_same_thread":False},
                         poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        for code in ("JOINVILLE","TUBARAO","ITAJAI"):
            db.add(Store(code=code,name=code))
        admin=User(id=uuid4(),auth_subject="more-admin",display_name="Admin",
                   profile="administrator",is_superadmin=False,active=True)
        joi=User(id=uuid4(),auth_subject="more-joi",display_name="Vendedor Joi",
                 profile="seller",is_superadmin=False,active=True)
        tub=User(id=uuid4(),auth_subject="more-tub",display_name="Vendedor Tub",
                 profile="seller",is_superadmin=False,active=True)
        db.add_all([admin,joi,tub]);db.flush()
        group=StoreGroup(id=uuid4(),store_code="JOINVILLE",name="Joinville",active=True)
        db.add(group);db.flush()
        db.add(GroupMembership(user_id=joi.id,group_id=group.id))
        for permission in ["checklist.view","whatsapp_status.view","instagram.view","training.view"]:
            db.add(GroupPermission(group_id=group.id,code=permission,granted=True))
        db.commit()
    actor={"user":admin}
    def user_override():return actor["user"]
    def db_override():
        with Session(engine) as db:yield db
    app.dependency_overrides[current_user]=user_override
    app.dependency_overrides[get_db]=db_override
    try:
        with TestClient(app) as client:
            yield client,actor,engine,admin,joi,tub
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_checklist_weekly_tasks_and_calls_goals(env):
    c,actor,engine,_,seller,_=env
    route="/api/v1/routines/checklist/JOINVILLE/2026-10-23"
    initial=c.get(route)
    assert initial.status_code==200
    assert initial.json()["week_start"]=="2026-10-19"
    assert initial.json()["calls"]=={"count":0,"target":20,"reached":False,"confirmed":False}
    data={"reference":"2026-10-19","title":"Conferir limpeza",
          "details":"Limpeza geral","frequency":"weekly","day":4}
    new=c.post("/api/v1/routines/checklist/JOINVILLE/tasks",json=data)
    assert new.status_code==201,new.text
    tid=new.json()["id"]
    assert c.get(route).json()["items"][0]["title"]=="Conferir limpeza"
    mark=c.put(f"/api/v1/routines/checklist/JOINVILLE/tasks/{tid}/check",json={
        "reference":"2026-10-19","done":True})
    assert mark.status_code==200,mark.text
    assert c.get(route).json()["items"][0]["done"] is True
    future=c.put(f"/api/v1/routines/checklist/JOINVILLE/tasks/{tid}/check",json={
        "reference":"2030-01-01","done":True})
    assert future.status_code==422
    goal=c.put("/api/v1/routines/checklist/JOINVILLE/calls-goal",json={
        "reference":"2026-10-19","goal":24,"confirmed":True})
    assert goal.status_code==200,goal.text
    assert c.get(route).json()["calls"]["target"]==24
    changed=c.put(f"/api/v1/routines/checklist/JOINVILLE/tasks/{tid}",json={
        **data,"title":"Conferir estoque"})
    assert changed.status_code==200,changed.text
    # Versions from old weeks survive the new version.
    assert c.get(route).json()["items"][0]["title"]=="Conferir estoque"
    actor["user"]=seller
    assert c.get(route).status_code==200
    assert c.get("/api/v1/routines/checklist/TUBARAO/2026-10-23").status_code==403
    assert c.post("/api/v1/routines/checklist/JOINVILLE/tasks",json=data).status_code==403
    with Session(engine) as db:
        actions=[row.action for row in db.scalars(select(AuditEvent))]
        assert "checklist.task.verified" in actions
        assert "checklist.calls.validated" in actions


def test_status_calendar_deduplicates_products_annually(env):
    c,actor,_,_,seller,_=env
    r="/api/v1/routines/whatsapp/2026-10-20"
    posted=c.put(r,json={"product_code":"MM 22002","category":"Promoções",
                          "note":"","status":"planejado","expected_revision":0})
    assert posted.status_code==200,posted.text
    assert posted.json()["status"]=="planejado"
    assert c.put("/api/v1/routines/whatsapp/2026-10-21",json={
        "product_code":" mm    22002 ","status":"planejado","expected_revision":0
    }).status_code==409
    assert c.put(r,json={"product_code":"MM 22002","status":"publicado",
                         "expected_revision":0}).status_code==409
    done=c.put(r,json={"product_code":"MM 22002","status":"publicado",
                       "expected_revision":1})
    assert done.status_code==200,done.text
    assert done.json()["published_on"] is not None
    assert c.put("/api/v1/routines/whatsapp/2026-10-25",json={
        "product_code":"A","status":"planejado","expected_revision":0
    }).status_code==422
    assert c.put("/api/v1/routines/whatsapp/2027-10-20",json={
        "product_code":"MM 22002","status":"planejado","expected_revision":0
    }).status_code==200
    assert c.put("/api/v1/routines/whatsapp/2026-10-20/day-off",json={
        "off":True,"reason":"Feriado"
    }).status_code==409
    off=c.put("/api/v1/routines/whatsapp/2026-10-22/day-off",json={
        "off":True,"reason":"Sem postagem"
    })
    assert off.status_code==200
    assert c.put("/api/v1/routines/whatsapp/2026-10-22",json={
        "product_code":"NOVO","status":"planejado","expected_revision":0
    }).status_code==422
    payload=c.get("/api/v1/routines/whatsapp/2026/10").json()
    assert len(payload["posts"])==1
    assert payload["attachments_enabled"] is False
    actor["user"]=seller
    assert c.get("/api/v1/routines/whatsapp/2026/10").status_code==200
    assert c.put("/api/v1/routines/whatsapp/2026-10-23",json={
        "product_code":"ABC","status":"planejado","expected_revision":0
    }).status_code==403


def test_instagram_is_manual_and_store_bound(env):
    c,actor,_,_,seller,_=env
    initial=c.get("/api/v1/routines/instagram/2026/10").json()
    assert initial["stores"][0]["planned"] is None
    save=c.put("/api/v1/routines/instagram/JOINVILLE/2026/10",json={
        "planned":12,"completed":7,"expected_revision":0
    })
    assert save.status_code==200,save.text
    assert save.json()["revision"]==1
    assert c.put("/api/v1/routines/instagram/JOINVILLE/2026/10",json={
        "planned":12,"completed":8,"expected_revision":0
    }).status_code==409
    actor["user"]=seller
    data=c.get("/api/v1/routines/instagram/2026/10").json()
    assert [row["store_code"] for row in data["stores"]]==["JOINVILLE"]
    assert data["stores"][0]["completed"]==7
    assert c.put("/api/v1/routines/instagram/JOINVILLE/2026/10",json={
        "planned":14,"completed":9,"expected_revision":1
    }).status_code==403


def test_training_metadata_never_fabricates_signature(env):
    c,actor,_,_,seller,other=env
    body={"participant_id":str(seller.id),"procedure":"POP-COM-01",
          "version":"0.1","instructor":"Gestão","happened_on":"2026-10-21T09:00:00",
          "step":"participou"}
    wrong=c.post("/api/v1/routines/trainings/JOINVILLE",json={
        **body,"participant_id":str(other.id)
    })
    assert wrong.status_code==422
    valid=c.post("/api/v1/routines/trainings/JOINVILLE",json=body)
    assert valid.status_code==201,valid.text
    assert valid.json()["signed"] is False
    assert valid.json()["document_attached"] is False
    actor["user"]=seller
    assert len(c.get("/api/v1/routines/trainings/JOINVILLE").json())==1
    assert c.get("/api/v1/routines/trainings/TUBARAO").status_code==403
    assert c.post("/api/v1/routines/trainings/JOINVILLE",json=body).status_code==403


def test_all_routes_reject_unauthenticated():
    with TestClient(app) as c:
        for route in [
            "/api/v1/routines/checklist/JOINVILLE/2026-10-23",
            "/api/v1/routines/whatsapp/2026/10",
            "/api/v1/routines/instagram/2026/10",
            "/api/v1/routines/trainings/JOINVILLE",
        ]:
            assert c.get(route).status_code==401
