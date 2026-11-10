"""Regression tests: procedure versions, private files and training privacy."""
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import get_db
from app.main import app
from app.models import (
    Base, GroupMembership, GroupPermission, Store, StoreGroup, User,
)


@pytest.fixture
def env():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        for code in ("JOINVILLE", "TUBARAO", "ITAJAI"):
            db.add(Store(code=code, name=code))
        admin = User(id=uuid4(), auth_subject="proc-admin", display_name="Admin",
                     profile="administrator", is_superadmin=False, active=True)
        joi = User(id=uuid4(), auth_subject="proc-joi", display_name="Vendedora Joi",
                   profile="seller", is_superadmin=False, active=True)
        colega = User(id=uuid4(), auth_subject="proc-col", display_name="Colega Joi",
                      profile="seller", is_superadmin=False, active=True)
        tub = User(id=uuid4(), auth_subject="proc-tub", display_name="Vendedor Tub",
                   profile="seller", is_superadmin=False, active=True)
        db.add_all([admin, joi, colega, tub]); db.flush()
        for code, members in (("JOINVILLE", [joi, colega]), ("TUBARAO", [tub])):
            group = StoreGroup(id=uuid4(), store_code=code, name=code, active=True)
            db.add(group); db.flush()
            for member in members:
                db.add(GroupMembership(user_id=member.id, group_id=group.id))
            db.add(GroupPermission(group_id=group.id, code="training.view", granted=True))
        db.commit()
    actor = {"user": admin}
    def user_override(): return actor["user"]
    def db_override():
        with Session(engine) as db: yield db
    app.dependency_overrides[current_user] = user_override
    app.dependency_overrides[get_db] = db_override
    try:
        with TestClient(app) as client:
            yield client, actor, engine, admin, joi, colega, tub
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _proc(c, title="POP teste"):
    r = c.post("/api/v1/procedures", json={
        "title": title, "summary": "", "applies_to_all": True,
        "store_codes": [], "content_html": "<p>v1</p>"})
    assert r.status_code == 201, r.text
    return r.json()


def test_procedure_lifecycle_and_version_history(env):
    c, actor, _, admin, joi, *_ = env
    p = _proc(c); pid = p["id"]
    # publish v1
    r = c.post(f"/api/v1/procedures/{pid}/publish", json={"expected_revision": 1})
    assert r.status_code == 200, r.text
    v1 = [v for v in c.get(f"/api/v1/procedures/{pid}/versions").json()
          if v["status"] == "publicado"][0]
    # save -> creates draft v2; publish it
    r = c.put(f"/api/v1/procedures/{pid}", json={
        "title": "POP v2", "summary": "", "applies_to_all": True, "store_codes": [],
        "content_html": "<p>v2</p>", "expected_revision": 1})
    assert r.status_code == 200 and r.json()["draft_version"], r.text
    rev = r.json()["draft_version"]["revision"]
    assert c.post(f"/api/v1/procedures/{pid}/publish",
                  json={"expected_revision": rev}).status_code == 200
    versions = c.get(f"/api/v1/procedures/{pid}/versions").json()
    assert len([v for v in versions if v["status"] == "publicado"]) == 2
    # v1 still readable
    old = c.get(f"/api/v1/procedures/{pid}/versions/{v1['id']}")
    assert old.status_code == 200 and "v1" in old.json()["content_html"]
    # training linked to current published (v2 after both published? first v1)
    t = c.post("/api/v1/routines/trainings/JOINVILLE", json={
        "participant_id": str(joi.id), "procedure_id": pid, "title": "",
        "instructor": "X", "happened_on": "2026-11-01T10:00:00",
        "step": "participou", "note": ""})
    assert t.status_code == 201, t.text
    assert t.json()["procedure_version_id"]


def test_training_edit_preserves_historical_version(env):
    c, _, _, admin, joi, *_ = env
    p = _proc(c); pid = p["id"]
    assert c.post(f"/api/v1/procedures/{pid}/publish",
                  json={"expected_revision": 1}).status_code == 200
    t = c.post("/api/v1/routines/trainings/JOINVILLE", json={
        "participant_id": str(joi.id), "procedure_id": pid, "title": "",
        "instructor": "X", "happened_on": "2026-11-01T10:00:00",
        "step": "participou", "note": "antes"})
    tid = t.json()["id"]; ver = t.json()["procedure_version_id"]
    # publish v2 -> current version changes
    c.put(f"/api/v1/procedures/{pid}", json={
        "title": "POP teste", "summary": "", "applies_to_all": True, "store_codes": [],
        "content_html": "<p>v2</p>", "expected_revision": 1})
    rev = c.get(f"/api/v1/procedures/{pid}").json()["draft_version"]["revision"]
    assert c.post(f"/api/v1/procedures/{pid}/publish",
                  json={"expected_revision": rev}).status_code == 200
    # edit only the note, keeping procedure_id -> version bond preserved
    r = c.put(f"/api/v1/routines/trainings/JOINVILLE/{tid}", json={
        "participant_id": str(joi.id), "procedure_id": pid, "title": "",
        "instructor": "X", "happened_on": "2026-11-01T10:00:00",
        "step": "participou", "note": "depois", "expected_revision": t.json()["revision"]})
    assert r.status_code == 200, r.text
    assert r.json()["procedure_version_id"] == ver
    assert r.json()["note"] == "depois"


def test_seller_cannot_read_others_trainings_or_documents(env):
    c, actor, _, admin, joi, colega, tub = env
    p = _proc(c); pid = p["id"]
    assert c.post(f"/api/v1/procedures/{pid}/publish",
                  json={"expected_revision": 1}).status_code == 200
    t_colega = c.post("/api/v1/routines/trainings/JOINVILLE", json={
        "participant_id": str(colega.id), "procedure_id": pid, "title": "",
        "instructor": "X", "happened_on": "2026-11-01T10:00:00",
        "step": "participou", "note": ""}).json()
    t_joi = c.post("/api/v1/routines/trainings/JOINVILLE", json={
        "participant_id": str(joi.id), "procedure_id": pid, "title": "",
        "instructor": "X", "happened_on": "2026-11-02T10:00:00",
        "step": "participou", "note": ""}).json()
    pdf = b"%PDF-1.4 fake-body"
    up = c.put(f"/api/v1/routines/trainings/JOINVILLE/{t_colega['id']}/document?expected_revision=0",
               files={"file": ("doc.pdf", pdf, "application/pdf")})
    assert up.status_code in (200, 201), up.text
    actor["user"] = joi
    # store list shows ONLY the seller's own record
    rows = c.get("/api/v1/routines/trainings/JOINVILLE").json()
    assert [r["id"] for r in rows] == [t_joi["id"]]
    # cannot download the colleague's PDF
    assert c.get(f"/api/v1/routines/trainings/JOINVILLE/{t_colega['id']}/document").status_code == 403
    # cannot write/delete either
    assert c.put(f"/api/v1/routines/trainings/JOINVILLE/{t_colega['id']}", json={
        "participant_id": str(colega.id), "procedure_id": pid, "title": "",
        "instructor": "X", "happened_on": "2026-11-01T10:00:00", "step": "participou",
        "note": "", "expected_revision": t_colega["revision"]}).status_code == 403
    # cannot create a procedure
    assert c.post("/api/v1/procedures", json={
        "title": "Tentativa", "summary": "", "applies_to_all": True,
        "store_codes": [], "content_html": "x"}).status_code == 403
    # my-trainings returns only own
    mine = c.get("/api/v1/routines/my-trainings").json()
    assert [r["id"] for r in mine] == [t_joi["id"]]
    actor["user"] = admin
    # admin sees all trainings of the store
    ids = {r["id"] for r in c.get("/api/v1/routines/trainings/JOINVILLE").json()}
    assert ids == {t_joi["id"], t_colega["id"]}
    # admin downloads colleague's PDF fine
    assert c.get(f"/api/v1/routines/trainings/JOINVILLE/{t_colega['id']}/document").status_code == 200


def test_logical_delete_hides_record_and_document(env):
    c, _, _, admin, joi, *_ = env
    p = _proc(c); pid = p["id"]
    c.post(f"/api/v1/procedures/{pid}/publish", json={"expected_revision": 1})
    t = c.post("/api/v1/routines/trainings/JOINVILLE", json={
        "participant_id": str(joi.id), "procedure_id": pid, "title": "",
        "instructor": "X", "happened_on": "2026-11-01T10:00:00",
        "step": "participou", "note": ""}).json()
    c.put(f"/api/v1/routines/trainings/JOINVILLE/{t['id']}/document?expected_revision=0",
          files={"file": ("doc.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert c.request("DELETE", f"/api/v1/routines/trainings/JOINVILLE/{t['id']}",
                     json={"expected_revision": t["revision"]}).status_code == 200
    assert not c.get("/api/v1/routines/trainings/JOINVILLE").json()
    assert c.get(f"/api/v1/routines/trainings/JOINVILLE/{t['id']}/document").status_code == 404


def test_sanitization_drops_external_images(env):
    c, _, _, admin, *_ = env
    r = c.post("/api/v1/procedures", json={
        "title": "Com imagem externa", "summary": "", "applies_to_all": True,
        "store_codes": [],
        "content_html": '<p>ok</p><img src="https://evil.example/x.png"/>'
                        '<script>alert(1)</script><img src="/api/v1/procedures/files/abc"/>'})
    html = r.json()["content_html"]
    assert "evil.example" not in html and "<script" not in html
    assert "/api/v1/procedures/files/abc" in html


def test_obsolete_hides_from_seller_keeps_history(env):
    c, actor, _, admin, joi, colega, tub = env
    p = _proc(c, "POP obsoleto"); pid = p["id"]
    c.post(f"/api/v1/procedures/{pid}/publish", json={"expected_revision": 1})
    t = c.post("/api/v1/routines/trainings/JOINVILLE", json={
        "participant_id": str(joi.id), "procedure_id": pid, "title": "",
        "instructor": "X", "happened_on": "2026-11-01T10:00:00",
        "step": "participou", "note": ""}).json()
    actor["user"] = joi
    assert pid in {x["id"] for x in c.get("/api/v1/procedures").json()}
    actor["user"] = admin
    obs = c.post(f"/api/v1/procedures/{pid}/obsolete")
    assert obs.status_code == 200, obs.text
    assert obs.json()["status"] == "obsoleto" and obs.json()["obsolete_at"]
    # sellers: hidden, blocked on get/version/file
    actor["user"] = joi
    assert pid not in {x["id"] for x in c.get("/api/v1/procedures").json()}
    assert c.get(f"/api/v1/procedures/{pid}").status_code == 404
    vers = c.get("/api/v1/routines/my-trainings").json()
    old = next(r for r in vers if r["id"] == t["id"])
    assert old["procedure"] and old["version"]  # training record kept
    assert c.get(f"/api/v1/procedures/{pid}/versions/{old['procedure_version_id']}").status_code == 404
    actor["user"] = admin
    # admin keeps all versions + audit trail
    assert len(c.get(f"/api/v1/procedures/{pid}/versions").json()) >= 1
    # no new training with obsolete procedure
    r = c.post("/api/v1/routines/trainings/JOINVILLE", json={
        "participant_id": str(joi.id), "procedure_id": pid, "title": "",
        "instructor": "X", "happened_on": "2026-11-05T10:00:00",
        "step": "participou", "note": ""})
    assert r.status_code == 422, r.text
    # never-published cannot be marked obsolete
    draft = _proc(c, "So rascunho obs")
    assert c.post(f"/api/v1/procedures/{draft['id']}/obsolete").status_code == 422


def test_delete_only_never_published(env):
    c, actor, _, admin, joi, *_ = env
    draft = _proc(c, "Rascunho descartado")
    pub = _proc(c, "Publicado firme")
    c.post(f"/api/v1/procedures/{pub['id']}/publish", json={"expected_revision": 1})
    # published cannot be deleted
    assert c.delete(f"/api/v1/procedures/{pub['id']}").status_code == 409
    # seller cannot delete
    actor["user"] = joi
    assert c.delete(f"/api/v1/procedures/{draft['id']}").status_code == 403
    actor["user"] = admin
    # draft deleted logically: disappears from list and get
    assert c.delete(f"/api/v1/procedures/{draft['id']}").status_code == 200
    assert draft["id"] not in {x["id"] for x in c.get("/api/v1/procedures").json()}
    assert c.get(f"/api/v1/procedures/{draft['id']}").status_code == 404


def test_seller_sees_only_published_applicable(env):
    c, actor, _, admin, joi, colega, tub = env
    pub = _proc(c, "Global publicado")
    c.post(f"/api/v1/procedures/{pub['id']}/publish", json={"expected_revision": 1})
    draft = _proc(c, "So rascunho")
    tub_only = c.post("/api/v1/procedures", json={
        "title": "Tubarao apenas", "summary": "", "applies_to_all": False,
        "store_codes": ["TUBARAO"], "content_html": "<p>t</p>"}).json()
    c.post(f"/api/v1/procedures/{tub_only['id']}/publish", json={"expected_revision": 1})
    actor["user"] = joi
    ids = {p["id"] for p in c.get("/api/v1/procedures").json()}
    assert pub["id"] in ids and draft["id"] not in ids and tub_only["id"] not in ids
    actor["user"] = tub
    ids = {p["id"] for p in c.get("/api/v1/procedures").json()}
    assert tub_only["id"] in ids

