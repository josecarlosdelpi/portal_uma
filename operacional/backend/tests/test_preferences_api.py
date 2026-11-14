"""User navigation preferences: scope, validation and ordering."""
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
    AccessGroup, Base, GroupPermission, Store, User,
)
from tests.access_helpers import seed_admin_access, seed_group


@pytest.fixture
def env():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add(Store(code="JOINVILLE", name="Joinville"))
        admin = User(id=uuid4(), auth_subject="pref-admin", display_name="Admin",
                     profile="administrator", is_superadmin=False, active=True)
        joi = User(id=uuid4(), auth_subject="pref-joi", display_name="Vendedora Joi",
                   profile="seller", is_superadmin=False, active=True)
        db.add_all([admin, joi]); db.flush()
        seed_admin_access(db, admin)
        seed_group(db, "Vendedores Joinville", ["JOINVILLE"], ["training.view"], [joi])
        db.commit()
    actor = {"user": admin}
    def user_override(): return actor["user"]
    def db_override():
        with Session(engine) as db: yield db
    app.dependency_overrides[current_user] = user_override
    app.dependency_overrides[get_db] = db_override
    try:
        with TestClient(app) as client:
            yield client, actor, engine, admin, joi
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_defaults_and_roundtrip(env):
    c, actor, _, admin, joi = env
    r = c.get("/api/v1/me/preferences")
    assert r.status_code == 200
    assert r.json() == {"sidebar_pinned": True, "favorites": [], "store_colors": {}}
    r = c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": False, "favorites": ["training", "overview", "targets"]})
    assert r.status_code == 200, r.text
    assert r.json()["favorites"] == ["training", "overview", "targets"]
    again = c.get("/api/v1/me/preferences").json()
    assert again["sidebar_pinned"] is False
    assert again["favorites"] == ["training", "overview", "targets"]


def test_unknown_and_unauthorized_modules(env):
    c, actor, _, admin, joi = env
    assert c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": ["nonsense"]}).status_code == 422
    actor["user"] = joi
    # vendedor so tem training.view: modulos nao autorizados sao filtrados
    r = c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True,
        "favorites": ["training", "access", "closing", "targets"]})
    assert r.status_code == 200
    assert r.json()["favorites"] == ["training"]


def test_dedupe_and_per_user_isolation(env):
    c, actor, _, admin, joi = env
    c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": ["overview", "overview", "targets"]})
    assert c.get("/api/v1/me/preferences").json()["favorites"] == ["overview", "targets"]
    actor["user"] = joi
    assert c.get("/api/v1/me/preferences").json()["favorites"] == []
    c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": False, "favorites": ["training"]})
    actor["user"] = admin
    own = c.get("/api/v1/me/preferences").json()
    assert own["favorites"] == ["overview", "targets"]
    assert own["sidebar_pinned"] is True  # unaffected by seller's save


def test_hidden_favorites_survive_later_saves(env):
    """Revogar permissao nao apaga o favorito: ele retorna quando o acesso volta."""
    c, actor, engine, admin, joi = env
    actor["user"] = joi
    c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": ["training"]})
    # simula perda de permissao: limpa grants do grupo
    with Session(engine) as db:
        db.query(GroupPermission).delete(); db.commit()
    # usuario nao ve mais o favorito, mas o save de pin NAO pode apaga-lo
    assert c.get("/api/v1/me/preferences").json()["favorites"] == []
    c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": False, "favorites": []})
    with Session(engine) as db:
        gid = db.scalar(select(AccessGroup.id).where(
            AccessGroup.name == "Vendedores Joinville"))
        db.add(GroupPermission(group_id=gid, code="training.view", granted=True)); db.commit()
    again = c.get("/api/v1/me/preferences").json()
    assert again["favorites"] == ["training"]  # restaurado
    assert again["sidebar_pinned"] is False


def test_middle_favorite_keeps_position(env):
    """Favorito no meio da lista perde permissao, volta a posicao original."""
    c, actor, engine, admin, joi = env
    actor["user"] = joi
    with Session(engine) as db:
        gid = db.scalar(select(AccessGroup.id).where(
            AccessGroup.name == "Vendedores Joinville"))
        for code in ("targets.view", "reviews.view"):
            db.add(GroupPermission(group_id=gid, code=code, granted=True))
        db.commit()
    c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": ["targets", "training", "reviews"]})
    assert c.get("/api/v1/me/preferences").json()["favorites"] == [
        "targets", "training", "reviews"]
    # perde acesso ao item do meio
    with Session(engine) as db:
        db.query(GroupPermission).filter(GroupPermission.code == "training.view").delete()
        db.commit()
    assert c.get("/api/v1/me/preferences").json()["favorites"] == ["targets", "reviews"]
    # continua usando: muda pin e reordena os visiveis
    c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": False, "favorites": ["reviews", "targets"]})
    assert c.get("/api/v1/me/preferences").json()["favorites"] == ["reviews", "targets"]
    # permissao volta: training reaparece na posicao original (meio)
    with Session(engine) as db:
        db.add(GroupPermission(group_id=gid, code="training.view", granted=True))
        db.commit()
    got = c.get("/api/v1/me/preferences").json()
    assert got["favorites"] == ["reviews", "training", "targets"]
    assert got["sidebar_pinned"] is False


def test_order_moves_and_pruning(env):
    c, actor, _, admin, joi = env
    c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": ["a", "overview"]})
    assert c.get("/api/v1/me/preferences").status_code == 200
    # unknown key is rejected outright
    assert c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": ["access"]}).status_code == 200
    # admin nao e superadmin: 'access' filtrado
    assert c.get("/api/v1/me/preferences").json()["favorites"] == []


def test_store_colors_roundtrip_and_validation(env):
    c, *_ = env
    r = c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": [],
        "store_colors": {"JOINVILLE": "#112233", "ITAJAI": "#aAbBcC"}})
    assert r.status_code == 200
    assert r.json()["store_colors"] == {"JOINVILLE": "#112233", "ITAJAI": "#aAbBcC"}
    again = c.get("/api/v1/me/preferences").json()
    assert again["store_colors"]["JOINVILLE"] == "#112233"
    # PUT sem store_colors preserva as cores gravadas
    r = c.put("/api/v1/me/preferences", json={"sidebar_pinned": False, "favorites": []})
    assert r.json()["store_colors"]["ITAJAI"] == "#aAbBcC"
    # dict vazio limpa as cores
    r = c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": [], "store_colors": {}})
    assert r.json()["store_colors"] == {}


def test_store_colors_rejected_values(env):
    c, *_ = env
    bad_hex = c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": [],
        "store_colors": {"JOINVILLE": "verde"}})
    assert bad_hex.status_code == 422
    bad_store = c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": [],
        "store_colors": {"NARNIA": "#112233"}})
    assert bad_store.status_code == 422


def test_sales_module_can_be_favorited(env):
    """Regressao: 'sales' era rejeitado como modulo desconhecido (422)."""
    c, actor, engine, admin, joi = env
    actor["user"] = joi
    # Sem sales.view: descartado silenciosamente, mas nunca 422 de desconhecido.
    r = c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": ["sales"]})
    assert r.status_code == 200, r.text
    assert r.json()["favorites"] == []
    # Com a permissao: favorita, desfavorita e persiste como os demais modulos.
    with Session(engine) as db:
        group = db.scalar(select(AccessGroup).where(
            AccessGroup.name == "Vendedores Joinville"))
        db.add(GroupPermission(group_id=group.id, code="sales.view", granted=True))
        db.commit()
    r = c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": ["sales", "training"]})
    assert r.status_code == 200
    assert r.json()["favorites"] == ["sales", "training"]
    again = c.get("/api/v1/me/preferences").json()
    assert again["favorites"] == ["sales", "training"]
    r = c.put("/api/v1/me/preferences", json={
        "sidebar_pinned": True, "favorites": ["training"]})
    assert r.json()["favorites"] == ["training"]
    assert c.get("/api/v1/me/preferences").json()["favorites"] == ["training"]
