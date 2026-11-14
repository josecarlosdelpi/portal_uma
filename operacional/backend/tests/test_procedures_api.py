"""Regression tests: procedure versions, private files and training privacy."""
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import get_db
from app.main import app
from app.models import (
    Base, Procedure, ProcedureVersion, Store, TrainingRecord, User,
)
from tests.access_helpers import seed_admin_access, seed_group


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
        seed_admin_access(db, admin)
        for code, members in (("JOINVILLE", [joi, colega]), ("TUBARAO", [tub])):
            seed_group(db, "Vendedores " + code, [code], ["training.view"], members)
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
    c, actor, engine, admin, joi, *_ = env
    p = _proc(c); pid = p["id"]
    c.post(f"/api/v1/procedures/{pid}/publish", json={"expected_revision": 1})
    t = c.post("/api/v1/routines/trainings/JOINVILLE", json={
        "participant_id": str(joi.id), "procedure_id": pid, "title": "",
        "instructor": "X", "happened_on": "2026-11-01T10:00:00",
        "step": "participou", "note": ""}).json()
    c.put(f"/api/v1/routines/trainings/JOINVILLE/{t['id']}/document?expected_revision=0",
          files={"file": ("doc.pdf", b"%PDF-1.4 x", "application/pdf")})
    # exclusao de treinamento exige SuperAdmin desde a restricao por perfil
    with Session(engine) as db:
        root = User(id=uuid4(), auth_subject="root-del", display_name="Super",
                    profile="administrator", is_superadmin=True, active=True)
        db.add(root); db.commit(); db.refresh(root)
        actor["user"] = root
    assert c.request("DELETE", f"/api/v1/routines/trainings/JOINVILLE/{t['id']}",
                     json={"expected_revision": t["revision"]}).status_code == 200
    actor["user"] = admin
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


def test_delete_permissions_and_preservation(env):
    """Rascunho nunca publicado: qualquer editor exclui. Publicado/obsoleto: so SuperAdmin.
    A exclusao e logica: versoes e treinamentos historicos permanecem no banco."""
    c, actor, engine, admin, joi, *_ = env
    draft = _proc(c, "Rascunho descartado")
    pub = _proc(c, "Publicado firme")
    c.post(f"/api/v1/procedures/{pub['id']}/publish", json={"expected_revision": 1})
    # published com nova versao em rascunho
    mixed = _proc(c, "Publicado com rascunho")
    c.post(f"/api/v1/procedures/{mixed['id']}/publish", json={"expected_revision": 1})
    c.put(f"/api/v1/procedures/{mixed['id']}", json={
        "title": "Publicado com rascunho", "summary": "", "applies_to_all": True,
        "store_codes": [], "content_html": "<p>v2</p>", "expected_revision": 1})
    # obsoleto
    obs = _proc(c, "Obsoleto alvo")
    c.post(f"/api/v1/procedures/{obs['id']}/publish", json={"expected_revision": 1})
    assert c.post(f"/api/v1/procedures/{obs['id']}/obsolete").status_code == 200
    # treinamento historico vinculado ao publicado
    t = c.post("/api/v1/routines/trainings/JOINVILLE", json={
        "participant_id": str(joi.id), "procedure_id": pub["id"], "title": "",
        "instructor": "X", "happened_on": "2026-11-01T10:00:00",
        "step": "participou", "note": ""}).json()
    # admin nao exclui publicado, publicado+rascunho nem obsoleto
    assert c.delete(f"/api/v1/procedures/{pub['id']}").status_code == 403
    assert c.delete(f"/api/v1/procedures/{mixed['id']}").status_code == 403
    assert c.delete(f"/api/v1/procedures/{obs['id']}").status_code == 403
    # vendedor nao exclui nem rascunho
    actor["user"] = joi
    assert c.delete(f"/api/v1/procedures/{draft['id']}").status_code == 403
    actor["user"] = admin
    # admin exclui rascunho nunca publicado: some das listagens e do acesso direto
    assert c.delete(f"/api/v1/procedures/{draft['id']}").status_code == 200
    assert draft["id"] not in {x["id"] for x in c.get("/api/v1/procedures").json()}
    assert c.get(f"/api/v1/procedures/{draft['id']}").status_code == 404
    # superadmin exclui publicado, publicado+rascunho e obsoleto
    with Session(engine) as db:
        root = User(id=uuid4(), auth_subject="root-proc", display_name="Super",
                    profile="administrator", is_superadmin=True, active=True)
        db.add(root); db.commit(); db.refresh(root)
        actor["user"] = root
    for target in (pub, mixed, obs):
        assert c.delete(f"/api/v1/procedures/{target['id']}").status_code == 200
        assert c.get(f"/api/v1/procedures/{target['id']}").status_code == 404
    assert not c.get("/api/v1/procedures").json()
    # vendedor e admin nao acessam por link direto
    actor["user"] = joi
    assert c.get(f"/api/v1/procedures/{pub['id']}").status_code == 404
    actor["user"] = admin
    assert c.get(f"/api/v1/procedures/{pub['id']}").status_code == 404
    # versoes e treinamentos historicos preservados no banco (exclusao logica)
    with Session(engine) as db:
        assert db.scalar(select(func.count(ProcedureVersion.id)).where(
            ProcedureVersion.procedure_id == UUID(pub["id"]))) >= 1
        rec = db.get(TrainingRecord, UUID(t["id"]))
        assert rec is not None and rec.procedure_version_id is not None
        assert db.get(Procedure, UUID(pub["id"])).deleted_at is not None


def test_training_delete_superadmin_only(env):
    """Somente o SuperAdmin exclui treinamentos; admin e vendedor recebem 403."""
    c, actor, engine, admin, joi, *_ = env
    p = _proc(c, "POP delete treinamento"); pid = p["id"]
    c.post(f"/api/v1/procedures/{pid}/publish", json={"expected_revision": 1})
    t = c.post("/api/v1/routines/trainings/JOINVILLE", json={
        "participant_id": str(joi.id), "procedure_id": pid, "title": "",
        "instructor": "X", "happened_on": "2026-11-01T10:00:00",
        "step": "participou", "note": ""}).json()
    rev = c.get("/api/v1/routines/trainings/JOINVILLE").json()[0]["revision"]
    url = f"/api/v1/routines/trainings/JOINVILLE/{t['id']}"
    body = {"expected_revision": rev}
    # vendedor -> 403
    actor["user"] = joi
    assert c.request("DELETE", url, json=body).status_code == 403
    # admin -> 403
    actor["user"] = admin
    assert c.request("DELETE", url, json=body).status_code == 403
    assert c.get("/api/v1/routines/trainings/JOINVILLE").json() != []  # nao excluiu
    # superadmin -> 200
    with Session(engine) as db:
        root = User(id=uuid4(), auth_subject="root", display_name="Super",
                    profile="administrator", is_superadmin=True, active=True)
        db.add(root); db.commit(); db.refresh(root)
        actor["user"] = root
    r = c.request("DELETE", url, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True
    # some das consultas normais
    assert t["id"] not in {x["id"] for x in c.get("/api/v1/routines/trainings/JOINVILLE").json()}
    actor["user"] = admin


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



def test_scoped_training_edit_cannot_manage_other_stores(env):
    """training.edit restrito a JOINVILLE nao autoriza documento global ou
    de outra loja — em criacao, edicao, publicacao, obsolescencia, exclusao
    e anexos. Este e o cenario-chave da revisao de seguranca."""
    c, actor, engine, admin, joi, *_ = env
    with Session(engine) as db:
        editor = User(id=uuid4(), auth_subject="proc-ed-joi",
                      display_name="Editor Joi", profile="staff",
                      is_superadmin=False, active=True)
        db.add(editor); db.flush()
        seed_group(db, "Editores Joinville", ["JOINVILLE"],
                   ["training.view", "training.edit"], [editor])
        db.commit(); db.refresh(editor)
    global_doc = _proc(c, "POP global")
    c.post(f"/api/v1/procedures/{global_doc['id']}/publish",
           json={"expected_revision": 1})
    tub_doc = c.post("/api/v1/procedures", json={
        "title": "POP Tubarao", "summary": "", "applies_to_all": False,
        "store_codes": ["TUBARAO"], "content_html": "<p>t</p>"}).json()
    actor["user"] = editor

    # criacao: nem global, nem loja fora do escopo
    assert c.post("/api/v1/procedures", json={
        "title": "Global indevido", "summary": "", "applies_to_all": True,
        "store_codes": [], "content_html": "x"}).status_code == 403
    assert c.post("/api/v1/procedures", json={
        "title": "Tubarao indevido", "summary": "", "applies_to_all": False,
        "store_codes": ["TUBARAO"], "content_html": "x"}).status_code == 403
    assert c.post("/api/v1/procedures", json={
        "title": "Duas lojas indevido", "summary": "", "applies_to_all": False,
        "store_codes": ["JOINVILLE", "TUBARAO"], "content_html": "x"}
    ).status_code == 403

    # criacao dentro do escopo funciona
    mine = c.post("/api/v1/procedures", json={
        "title": "POP Joinville", "summary": "", "applies_to_all": False,
        "store_codes": ["JOINVILLE"], "content_html": "<p>j</p>"})
    assert mine.status_code == 201, mine.text
    mine_id = mine.json()["id"]
    assert c.post(f"/api/v1/procedures/{mine_id}/publish",
                  json={"expected_revision": 1}).status_code == 200

    # operacoes sobre documento global -> 403 em todas
    gid = global_doc["id"]
    assert c.put(f"/api/v1/procedures/{gid}", json={
        "title": "Edicao indevida", "summary": "", "applies_to_all": True,
        "store_codes": [], "content_html": "<p>x</p>",
        "expected_revision": 1}).status_code == 403
    assert c.post(f"/api/v1/procedures/{gid}/obsolete").status_code == 403
    assert c.delete(f"/api/v1/procedures/{gid}").status_code == 403
    assert c.put(f"/api/v1/procedures/{gid}/files",
                 files={"file": ("i.png", b"\x89PNG\r\n\x1a\n" + b"0" * 60, "image/png")}
                 ).status_code == 403
    # idem sobre documento de outra loja
    assert c.put(f"/api/v1/procedures/{tub_doc['id']}", json={
        "title": "Edicao indevida", "summary": "", "applies_to_all": False,
        "store_codes": ["TUBARAO"], "content_html": "<p>x</p>",
        "expected_revision": 1}).status_code == 403

    # nao pode ampliar o escopo do proprio documento para fora da loja
    assert c.put(f"/api/v1/procedures/{mine_id}", json={
        "title": "POP Joinville", "summary": "", "applies_to_all": True,
        "store_codes": [], "content_html": "<p>j</p>",
        "expected_revision": 1}).status_code == 403
    # nem reduzir para criar versao global indiretamente: Tubarao segue fora
    assert c.put(f"/api/v1/procedures/{mine_id}", json={
        "title": "POP Joinville", "summary": "", "applies_to_all": False,
        "store_codes": ["TUBARAO"], "content_html": "<p>j</p>",
        "expected_revision": 1}).status_code == 403

    # publicado: mesmo editor com escopo correto nao exclui (SuperAdmin-only)
    assert c.delete(f"/api/v1/procedures/{mine_id}").status_code == 403
    actor["user"] = admin


def test_obsolete_blocks_writes(env):
    """Procedimento obsoleto: sem edicao, publicacao ou novos anexos."""
    c, _, _, admin, joi, *_ = env
    p = _proc(c, "POP obsoleto bloqueado"); pid = p["id"]
    c.post(f"/api/v1/procedures/{pid}/publish", json={"expected_revision": 1})
    c.post(f"/api/v1/procedures/{pid}/obsolete")
    assert c.put(f"/api/v1/procedures/{pid}", json={
        "title": "Nova tentativa", "summary": "", "applies_to_all": True,
        "store_codes": [], "content_html": "<p>x</p>",
        "expected_revision": 1}).status_code == 409
    assert c.post(f"/api/v1/procedures/{pid}/publish",
                  json={"expected_revision": 1}).status_code == 409
    assert c.put(f"/api/v1/procedures/{pid}/files",
                 files={"file": ("i.png", b"\x89PNG\r\n\x1a\n" + b"0" * 60, "image/png")}
                 ).status_code == 409
