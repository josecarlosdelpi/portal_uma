"""Operational workflows: all rows scoped, writes audited and conflicts rejected."""
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
    AuditEvent, Base, GroupMembership, GroupPermission, Store, StoreGroup, User,
)


@pytest.fixture
def env():
    engine=create_engine("sqlite+pysqlite://",connect_args={"check_same_thread":False},
                         poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        for code in ("JOINVILLE","ITAJAI","TUBARAO"):
            db.add(Store(code=code,name=code))
        admin=User(id=uuid4(),auth_subject="ops-admin",display_name="Admin Operacional",
                   profile="administrator",is_superadmin=False,active=True)
        seller=User(id=uuid4(),auth_subject="ops-seller",display_name="Vendedor Joinville",
                    profile="seller",is_superadmin=False,active=True)
        other=User(id=uuid4(),auth_subject="ops-other",display_name="Vendedor Tubarao",
                   profile="seller",is_superadmin=False,active=True)
        db.add_all([admin,seller,other]);db.flush()
        j=StoreGroup(id=uuid4(),store_code="JOINVILLE",name="Joinville",active=True)
        t=StoreGroup(id=uuid4(),store_code="TUBARAO",name="Tubarao",active=True)
        db.add_all([j,t]);db.flush()
        db.add_all([
            GroupMembership(user_id=seller.id,group_id=j.id),
            GroupMembership(user_id=other.id,group_id=t.id),
            GroupPermission(group_id=j.id,code="reviews.view",granted=True),
            GroupPermission(group_id=j.id,code="supplies.view",granted=True),
            GroupPermission(group_id=j.id,code="telemarketing.view",granted=True),
        ])
        db.commit()
    identity={"actor":admin}
    def override_user():return identity["actor"]
    def override_db():
        with Session(engine) as db:yield db
    app.dependency_overrides[current_user]=override_user
    app.dependency_overrides[get_db]=override_db
    try:
        with TestClient(app) as client:
            yield client,identity,engine,admin,seller,other
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_reviews_have_one_non_cumulative_reward_and_delivery(env):
    client,identity,engine,_,seller,_=env
    route="/api/v1/operations/reviews/JOINVILLE/2026/10"
    empty=client.get("/api/v1/operations/reviews/2026/10").json()
    assert len(empty["stores"])==3
    assert empty["stores"][0]["count"] is None
    r=client.put(route,json={"count":10,"checked_on":"2026-10-23","expected_revision":0})
    assert r.status_code==200,r.text
    assert r.json()["tier"]=="simbolico"
    assert r.json()["delivered_on"] is None
    assert client.put(route,json={"count":20,"checked_on":"2026-10-23","expected_revision":0}).status_code==409
    r=client.put(route,json={"count":20,"checked_on":"2026-10-23",
                            "delivered_on":"2026-10-23","expected_revision":1})
    assert r.status_code==200,r.text
    assert r.json()["tier"]=="maior"
    assert r.json()["reward_per_seller"]=="maior"
    assert r.json()["revision"]==2
    assert client.put(route,json={"count":4,"checked_on":"2026-10-23",
                                  "delivered_on":"2026-10-23","expected_revision":2}).status_code==422
    identity["actor"]=seller
    visible=client.get("/api/v1/operations/reviews/2026/10").json()
    assert [x["store_code"] for x in visible["stores"]]==["JOINVILLE"]
    assert visible["stores"][0]["count"]==20
    assert client.put(route,json={"count":5,"checked_on":"2026-10-23","expected_revision":2}).status_code==403
    with Session(engine) as db:
        events=db.scalars(select(AuditEvent)).all()
        assert len([ev for ev in events if ev.action=="reviews.checked"])==2


def test_stock_movement_is_transactional_and_has_no_negative_balance(env):
    client,identity,engine,admin,seller,_=env
    create=client.post("/api/v1/operations/supplies/materials",json={
        "name":"Papel toalha","unit":"pacote",
        "minima":{"JOINVILLE":4,"ITAJAI":2,"TUBARAO":3}
    })
    assert create.status_code==201,create.text
    material=create.json()["id"]
    first=client.get("/api/v1/operations/supplies/JOINVILLE").json()
    assert len(first["items"])==1 and first["items"][0]["balance"]==0
    route="/api/v1/operations/supplies/movements"
    payload={"store_code":"JOINVILLE","material_id":material,"kind":"entrada",
             "quantity":8,"note":"Estoque inicial","expected_revision":1}
    move=client.post(route,json=payload)
    assert move.status_code==201,move.text
    assert move.json()["resulting_balance"]==8
    payload.update(kind="retirada",quantity=9,expected_revision=2)
    assert client.post(route,json=payload).status_code==422
    payload.update(quantity=3)
    assert client.post(route,json=payload).status_code==201
    payload.update(expected_revision=2)
    assert client.post(route,json=payload).status_code==409
    items=client.get("/api/v1/operations/supplies/JOINVILLE").json()["items"]
    assert items[0]["balance"]==5 and items[0]["minimum"]==4
    assert client.get("/api/v1/operations/supplies/TUBARAO").json()["items"][0]["balance"]==0
    history=client.get("/api/v1/operations/supplies/JOINVILLE/movements").json()
    assert len(history)==2
    assert set(row["actor"] for row in history)=={"Admin Operacional"}
    identity["actor"]=seller
    assert client.get("/api/v1/operations/supplies/ITAJAI").status_code==403
    assert client.get("/api/v1/operations/supplies/JOINVILLE").status_code==200
    assert client.post(route,json={**payload,"expected_revision":3}).status_code==403
    assert client.post("/api/v1/operations/supplies/materials",json={
        "name":"Papel extra","unit":"pacote","minima":{"JOINVILLE":0,"ITAJAI":0,"TUBARAO":0}
    }).status_code==403


def test_contact_log_requires_client_and_active_seller_same_store(env):
    client,identity,engine,_,seller,other=env
    customer=client.post("/api/v1/operations/contacts/JOINVILLE/clients",json={
        "name":"Oficina Teste","origin":"google","phone":"0000000"
    })
    assert customer.status_code==201,customer.text
    cid=customer.json()["id"]
    assert client.post("/api/v1/operations/contacts/JOINVILLE/clients",json={
        "name":"  OFICINA    TESTE ","origin":"google"
    }).status_code==409
    assert len(client.get("/api/v1/operations/contacts/JOINVILLE/team").json())==1
    call={"client_id":cid,"seller_id":str(seller.id),"date":"2026-10-20",
          "outcome":"sem_resposta","next_on":"2026-10-28","note":"Primeira tentativa"}
    wrong=client.post("/api/v1/operations/contacts/TUBARAO/calls",json=call)
    assert wrong.status_code==422
    assert client.post("/api/v1/operations/contacts/JOINVILLE/calls",json={
        **call,"seller_id":str(other.id)
    }).status_code==422
    result=client.post("/api/v1/operations/contacts/JOINVILLE/calls",json=call)
    assert result.status_code==201,result.text
    record=result.json()
    assert record["seller"]=="Vendedor Joinville"
    updated=client.put("/api/v1/operations/contacts/JOINVILLE/calls/"+record["id"],json={
        "date":"2026-10-20","outcome":"whatsapp","next_on":"2026-10-30",
        "note":"Consegui contato","expected_revision":1
    })
    assert updated.status_code==200,updated.text
    assert updated.json()["revision"]==2
    assert client.put("/api/v1/operations/contacts/JOINVILLE/calls/"+record["id"],json={
        "date":"2026-10-20","outcome":"outro","expected_revision":1
    }).status_code==409
    identity["actor"]=seller
    own=client.get("/api/v1/operations/contacts/JOINVILLE/2026/10/calls")
    assert own.status_code==200 and len(own.json()["items"])==1
    assert client.get("/api/v1/operations/contacts/TUBARAO/2026/10/calls").status_code==403
    assert client.post("/api/v1/operations/contacts/JOINVILLE/calls",json=call).status_code==403
    assert client.get("/api/v1/operations/contacts/TUBARAO/clients").status_code==403
    with Session(engine) as db:
        actions=[entry.action for entry in db.scalars(select(AuditEvent)).all()]
        assert "telemarketing.call.created" in actions
        assert "telemarketing.call.corrected" in actions


def test_no_identity_still_requires_login():
    with TestClient(app) as client:
        assert client.get("/api/v1/operations/reviews/2026/10").status_code==401
        assert client.get("/api/v1/operations/supplies/JOINVILLE").status_code==401
        assert client.get("/api/v1/operations/contacts/JOINVILLE/clients").status_code==401
