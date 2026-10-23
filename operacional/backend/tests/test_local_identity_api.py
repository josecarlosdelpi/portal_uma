"""Senha local sem e-mail, obrigatoriedade de troca, exclusao e auditoria."""
from uuid import UUID, uuid4
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import get_db
from app.local_identity import LocalAuthError, password_matches
from app.bootstrap_local import provision_initial_local_superadmin
from app.main import app
from app.models import Base, LocalCredential, LocalSession, AuditEvent, Store, StoreGroup, User


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        for code in ("JOINVILLE", "TUBARAO", "ITAJAI"):
            db.add(Store(code=code, name=code))
        admin = User(
            id=uuid4(), auth_subject="test-oidc-admin",
            display_name="Admin", profile="administrator",
            is_superadmin=True, active=True,
        )
        manager = User(
            id=uuid4(), auth_subject="test-oidc-manager",
            display_name="Manager", profile="administrator",
            is_superadmin=False, active=True,
        )
        db.add_all([admin, manager])
        db.flush()
        db.add_all([
            StoreGroup(id=uuid4(),store_code=code,name=code,active=True)
            for code in ("JOINVILLE","TUBARAO","ITAJAI")
        ])
        db.commit()
    acting = {"user": admin}

    def actor_override():
        return acting["user"]

    def db_override():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[current_user] = actor_override
    app.dependency_overrides[get_db] = db_override
    try:
        with TestClient(app) as client:
            yield client, acting, engine, admin, manager, actor_override
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def create_seller(client, username="bruno", store="JOINVILLE"):
    response = client.post("/api/v1/admin/local-users",json={
        "username":username,"display_name":"Colaborador Teste",
        "profile":"seller","store_code":store,
    })
    assert response.status_code==201, response.text
    return response.json()


def test_user_creation_requires_no_email_and_password_is_one_time(env):
    client, _, engine, _, _, _ = env
    result = create_seller(client, "Bruno")
    secret = result["temporary_password"]
    assert len(secret)==20
    assert result["username"]=="bruno"
    assert result["must_change_password"] is True
    assert "email" not in result
    assert client.post("/api/v1/admin/local-users",json={
        "username":"BRUNO","display_name":"Duplicado",
        "profile":"seller","store_code":"ITAJAI"
    }).status_code==409
    names=client.get("/api/v1/admin/users").json()
    created=[item for item in names if item["id"]==result["id"]]
    assert len(created)==1
    with Session(engine) as db:
        cred = db.get(LocalCredential, UUID(result["id"]))
        assert cred.password_hash != secret
        assert password_matches(cred.password_hash, secret)
        assert cred.must_change_password is True
        details=json.dumps([a.details for a in db.scalars(select(AuditEvent)).all()])
        assert secret not in details


def test_first_login_cannot_access_data_until_password_changed(env):
    client, identity, engine, admin, _, actor_override = env
    row=create_seller(client,"r.fernandes")
    login=client.post("/api/v1/local-auth/login",json={
        "username":"R.FERNANDES","password":row["temporary_password"]
    })
    assert login.status_code==200,login.text
    assert login.json()["must_change_password"] is True
    assert login.headers["cache-control"]=="no-store"
    token=login.json()["access_token"]
    # Remove OIDC test override to exercise the real auth guard.
    app.dependency_overrides.pop(current_user)
    assert client.get("/api/v1/me",headers={"Authorization":"Bearer "+token}).status_code==403
    assert client.get("/api/v1/admin/users",headers={"Authorization":"Bearer "+token}).status_code==403
    bad=client.post("/api/v1/local-auth/change-password",json={
        "new_password":"short"
    },headers={"Authorization":"Bearer "+token})
    assert bad.status_code==422
    same=client.post("/api/v1/local-auth/change-password",json={
        "new_password":row["temporary_password"]
    },headers={"Authorization":"Bearer "+token})
    assert same.status_code==422
    changed=client.post("/api/v1/local-auth/change-password",json={
        "new_password":"minha-nova-senha-forte-2026"
    },headers={"Authorization":"Bearer "+token})
    assert changed.status_code==200,changed.text
    assert changed.json()["must_change_password"] is False
    full=changed.json()["access_token"]
    assert client.get("/api/v1/me",headers={"Authorization":"Bearer "+full}).status_code==200
    assert client.get("/api/v1/me",headers={"Authorization":"Bearer "+token}).status_code==401
    assert client.post("/api/v1/local-auth/login",json={
        "username":"r.fernandes","password":row["temporary_password"]
    }).status_code==401
    assert client.post("/api/v1/local-auth/login",json={
        "username":"r.fernandes","password":"minha-nova-senha-forte-2026"
    }).status_code==200
    assert client.post("/api/v1/local-auth/logout",
        headers={"Authorization":"Bearer "+full}).status_code==200
    assert client.get("/api/v1/me",headers={"Authorization":"Bearer "+full}).status_code==401
    app.dependency_overrides[current_user]=actor_override


def test_reset_and_delete_revoke_sessions_and_keep_history(env):
    client, identity, engine, admin, _, actor_override = env
    row=create_seller(client)
    temp=row["temporary_password"]
    login=client.post("/api/v1/local-auth/login",json={
        "username":"bruno","password":temp
    }).json()
    forced=client.post("/api/v1/local-auth/change-password",json={
        "new_password":"Senha pessoal segura de teste 2026"
    },headers={"Authorization":"Bearer "+login["access_token"]}).json()
    full=forced["access_token"]
    reset=client.post("/api/v1/admin/users/"+row["id"]+"/reset-password")
    assert reset.status_code==200,reset.text
    another=reset.json()["temporary_password"]
    assert another != temp
    assert another != "Senha pessoal segura de teste 2026"
    app.dependency_overrides.pop(current_user)
    assert client.get("/api/v1/me",headers={"Authorization":"Bearer "+full}).status_code==401
    assert client.post("/api/v1/local-auth/login",json={
        "username":"bruno","password":"Senha pessoal segura de teste 2026"
    }).status_code==401
    fresh=client.post("/api/v1/local-auth/login",json={
        "username":"bruno","password":another
    })
    assert fresh.status_code==200
    app.dependency_overrides[current_user]=actor_override
    deleted=client.request("DELETE","/api/v1/admin/users/"+row["id"])
    assert deleted.status_code==200,deleted.text
    assert deleted.json()["deleted"] is True
    assert all(item["id"] != row["id"] for item in client.get("/api/v1/admin/users").json())
    assert client.request("DELETE","/api/v1/admin/users/"+row["id"]).status_code==404
    assert client.patch("/api/v1/admin/users/"+row["id"]+"/active",json={"active":True}).status_code==404
    app.dependency_overrides.pop(current_user)
    assert client.get("/api/v1/me",headers={
        "Authorization":"Bearer "+fresh.json()["access_token"]
    }).status_code==401
    assert client.post("/api/v1/local-auth/login",json={
        "username":"bruno","password":another
    }).status_code==401
    app.dependency_overrides[current_user]=actor_override
    with Session(engine) as db:
        found=db.get(User,UUID(row["id"]))
        assert found is not None and found.deleted_at is not None
        assert found.active is False
        actions=[a.action for a in db.scalars(select(AuditEvent))]
        assert "user.deleted" in actions and "user.password_reset" in actions
        assert len(db.scalars(select(LocalSession).where(
            LocalSession.user_id == found.id
        )).all())>=2


def test_non_superadmin_cannot_create_reset_or_delete(env):
    client, identity, engine, admin, manager, _ = env
    row=create_seller(client)
    identity["user"]=manager
    create=client.post("/api/v1/admin/local-users",json={
        "username":"rafael","display_name":"Rafael",
        "profile":"seller","store_code":"JOINVILLE"
    })
    assert create.status_code==403
    assert client.post("/api/v1/admin/users/"+row["id"]+"/reset-password").status_code==403
    assert client.request("DELETE","/api/v1/admin/users/"+row["id"]).status_code==403
    identity["user"]=admin
    assert client.request("DELETE","/api/v1/admin/users/"+str(admin.id)).status_code==403


def test_invalid_username_and_roles_cannot_be_provisioned(env):
    client,*_=env
    for uname in ("ab","com espaço","nome@dominio","admin/1"):
        result=client.post("/api/v1/admin/local-users",json={
            "username":uname,"display_name":"Pessoa Teste",
            "profile":"seller","store_code":"JOINVILLE"
        })
        assert result.status_code==422,result.text
    assert client.post("/api/v1/admin/local-users",json={
        "username":"newowner","display_name":"Outro SuperAdmin",
        "profile":"superadmin","store_code":None
    }).status_code==422
    assert client.post("/api/v1/admin/local-users",json={
        "username":"jardel","display_name":"Jardel",
        "profile":"administrator","store_code":"JOINVILLE"
    }).status_code==422
    assert client.post("/api/v1/admin/local-users",json={
        "username":"rafael","display_name":"Rafael",
        "profile":"seller","store_code":None
    }).status_code==422


def test_login_wrong_password_then_lock_until_cooldown(env):
    client,*_=env
    row=create_seller(client)
    for _ in range(5):
        response=client.post("/api/v1/local-auth/login",json={
            "username":"bruno","password":"senha errada"
        })
        assert response.status_code==401
    response=client.post("/api/v1/local-auth/login",json={
        "username":"bruno","password":row["temporary_password"]
    })
    assert response.status_code==401


def test_initial_superadmin_bootstrap_creates_only_one_without_email():
    engine=create_engine("sqlite+pysqlite://",
        connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            user,passcode=provision_initial_local_superadmin(
                db,"uma-admin","SuperAdmin UMA"
            )
            assert user.is_superadmin is True
            assert len(passcode)==20
            assert db.get(LocalCredential,user.id) is not None
            with pytest.raises(LocalAuthError) as error:
                provision_initial_local_superadmin(db,"segundo","Outro SuperAdmin")
            assert error.value.status_code==409
    finally:
        engine.dispose()
