"""Carteira comercial de televendas: cadastro ampliado, avisos, retornos,
indicadores, configuracao de inatividade e importacao de planilhas."""
import io
from uuid import uuid4

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import get_db
from app.main import app
from app.models import AuditEvent, Base, Store, User
from tests.access_helpers import seed_admin_access, seed_group


@pytest.fixture
def env():
    engine=create_engine("sqlite+pysqlite://",connect_args={"check_same_thread":False},
                         poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        for code in ("JOINVILLE","ITAJAI","TUBARAO"):
            db.add(Store(code=code,name=code))
        admin=User(id=uuid4(),auth_subject="tm-admin",display_name="Gestora Televendas",
                   profile="administrator",is_superadmin=False,active=True)
        seller=User(id=uuid4(),auth_subject="tm-seller",display_name="Vendedor Itajai",
                    profile="seller",is_superadmin=False,active=True)
        outsider=User(id=uuid4(),auth_subject="tm-outsider",display_name="Sem Acesso",
                      profile="seller",is_superadmin=False,active=True)
        db.add_all([admin,seller,outsider]);db.flush()
        seed_admin_access(db, admin)
        seed_group(db, "Vendedores Itajai", ["ITAJAI"],
                   ["telemarketing.view", "telemarketing.edit"], [seller])
        seed_group(db, "Sem acesso", ["TUBARAO"], [], [outsider])
        db.commit()
    identity={"actor":admin}
    def override_user():return identity["actor"]
    def override_db():
        with Session(engine) as db:yield db
    app.dependency_overrides[current_user]=override_user
    app.dependency_overrides[get_db]=override_db
    try:
        with TestClient(app) as client:
            yield client,identity,engine,admin,seller,outsider
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def create(client, **fields):
    payload={"origin":"google",**fields}
    return client.post("/api/v1/operations/contacts/ITAJAI/clients",json=payload)


def full_client():
    return {
        "name":"Mecânica Exemplo","origin":"google","phone":"47 3264-9244",
        "cellphone":"47 98464-6623","city":"Navegantes","contact_person":"Elides",
        "birthday_day":13,"birthday_month":1,"status":"ativo","tag":"Linha Leve",
        "last_contact_on":"2026-10-01","last_purchase_on":"2026-09-10",
        "erp_code":"2500","notes":"Cliente antigo, prefere WhatsApp. "*3,
    }


def test_full_registration_and_independent_city(env):
    client,*_=env
    saved=create(client,confirm=True,**full_client())
    assert saved.status_code==201,saved.text
    row=saved.json()["client"]
    assert row["city"]=="Navegantes"  # cidade independente da loja UMA
    assert row["cellphone"]=="47 98464-6623"
    assert row["birthday"]=="13/01"
    assert row["status"]=="ativo"
    assert row["tag"]=="Linha Leve"
    assert len(row["notes"])>60
    detail=client.get(f"/api/v1/operations/contacts/ITAJAI/clients/{row['id']}")
    assert detail.status_code==200,detail.text
    assert detail.json()["days_since_purchase"] is not None


def test_duplicate_phone_and_missing_tag_warn_but_do_not_block(env):
    client,*_=env
    first=create(client,name="Autopeças A",phone="47 9999-0001",
                 city="Itajaí",contact_person="Ana",tag="Autopeças",status="ativo")
    assert first.status_code==201,first.text
    dup=create(client,name="Autopeças B",phone="(47) 99990-001",
               tag="Autopeças",status="ativo",city="Itajaí",
               contact_person="Beto")
    assert dup.status_code==201
    assert dup.json()["result"]=="review"
    assert any(w["code"]=="telefone_duplicado" for w in dup.json()["warnings"])
    confirmed=create(client,name="Autopeças B",phone="(47) 99990-001",
                     tag="Autopeças",status="ativo",city="Itajaí",
                     contact_person="Beto",confirm=True)
    assert confirmed.json()["result"]=="saved"
    no_tag=create(client,name="Sem Tag Ltda",city="Itajaí",
                  contact_person="Carlos",phone="47 3000-0000")
    assert no_tag.json()["result"]=="review"
    assert any(w["code"]=="sem_tag" for w in no_tag.json()["warnings"])
    incomplete=create(client,name="Incompleto SA")
    assert any(w["code"]=="dados_incompletos" for w in incomplete.json()["warnings"])
    complete=create(client,name="Sem Tag Ltda",city="Itajaí",
                    contact_person="Carlos",phone="47 3000-0000",confirm=True)
    assert complete.json()["result"]=="saved"


def test_odd_dates_warn_and_never_rewrite_user_data(env):
    client,*_=env
    future=create(client,name="Data Futura",city="Itajaí",
                  contact_person="Duda",tag="Frotista",
                  last_purchase_on="2099-01-01")
    assert future.json()["result"]=="review"
    assert any(w["code"]=="data_inconsistente" for w in future.json()["warnings"])
    saved=create(client,name="Data Futura",city="Itajaí",
                 contact_person="Duda",tag="Frotista",
                 last_purchase_on="2099-01-01",confirm=True)
    # a data informada e preservada, nao corrigida silenciosamente
    assert saved.json()["client"]["last_purchase_on"]=="2099-01-01"


def test_client_update_with_revision_and_warnings(env):
    client,*_=env
    saved=create(client,confirm=True,**full_client()).json()["client"]
    wrong=client.put(f"/api/v1/operations/contacts/ITAJAI/clients/{saved['id']}",
                     json={"expected_revision":9,"city":"Itajaí"})
    assert wrong.status_code==409
    changed=client.put(f"/api/v1/operations/contacts/ITAJAI/clients/{saved['id']}",
                       json={"expected_revision":saved["revision"],"city":"Itajaí",
                             "status":"inativo","tag":""})
    assert changed.status_code==200,changed.text
    assert changed.json()["result"]=="review"
    assert any(w["code"]=="sem_tag" for w in changed.json()["warnings"])
    confirmed=client.put(f"/api/v1/operations/contacts/ITAJAI/clients/{saved['id']}",
                         json={"expected_revision":saved["revision"],"city":"Itajaí",
                               "status":"inativo","tag":"","confirm":True})
    assert confirmed.json()["result"]=="saved"
    assert confirmed.json()["client"]["city"]=="Itajaí"
    assert confirmed.json()["client"]["revision"]==saved["revision"]+1


def test_filters_and_pagination(env):
    client,*_=env
    for i in range(120):
        create(client,confirm=True,name=f"Cliente {i:03d}",
               city="Itajaí" if i%2==0 else "Navegantes",
               tag="Linha Leve" if i%3 else "Frotista",
               status="ativo" if i%5 else "prospect",
               contact_person="Pessoa",phone=f"47 90000-{i:04d}")
    page1=client.get("/api/v1/operations/contacts/ITAJAI/clients?page=1&page_size=50")
    assert page1.status_code==200
    assert page1.json()["total"]==120 and len(page1.json()["items"])==50
    page3=client.get("/api/v1/operations/contacts/ITAJAI/clients?page=3&page_size=50")
    assert len(page3.json()["items"])==20
    nav=client.get("/api/v1/operations/contacts/ITAJAI/clients?city=Navegantes&page_size=200")
    assert nav.json()["total"]==60
    tag=client.get("/api/v1/operations/contacts/ITAJAI/clients?tag=Frotista&page_size=200")
    assert tag.json()["total"]==40
    pros=client.get("/api/v1/operations/contacts/ITAJAI/clients?status=prospect&page_size=200")
    assert pros.json()["total"]==24
    phone=client.get("/api/v1/operations/contacts/ITAJAI/clients?phone=90000 0007")
    assert phone.json()["total"]==1
    search=client.get("/api/v1/operations/contacts/ITAJAI/clients?q=cliente 011")
    assert search.json()["total"]==1


def test_calls_with_whatsapp_channel_and_client_history(env):
    client,identity,engine,_,seller,_=env
    cid=create(client,confirm=True,**full_client()).json()["client"]["id"]
    call=client.post("/api/v1/operations/contacts/ITAJAI/calls",json={
        "client_id":cid,"seller_id":str(seller.id),"date":"2026-10-10",
        "channel":"whatsapp","outcome":"whatsapp","next_on":"2026-10-15",
        "note":"Pediu catálogo"})
    assert call.status_code==201,call.text
    assert call.json()["channel"]=="whatsapp"
    detail=client.get(f"/api/v1/operations/contacts/ITAJAI/clients/{cid}").json()
    assert len(detail["history"])==1
    assert detail["history"][0]["channel"]=="whatsapp"
    assert len(detail["pending_followups"])==1


def test_followups_complete_and_reschedule(env):
    client,identity,engine,_,seller,_=env
    cid=create(client,confirm=True,**full_client()).json()["client"]["id"]
    call=client.post("/api/v1/operations/contacts/ITAJAI/calls",json={
        "client_id":cid,"seller_id":str(seller.id),"date":"2026-01-05",
        "channel":"ligacao","outcome":"outro","next_on":"2026-01-10"}).json()
    pending=client.get("/api/v1/operations/contacts/ITAJAI/followups?state=abertos").json()
    assert pending["total"]==1
    assert pending["items"][0]["overdue"] is True  # janeiro ja passou
    done=client.post(
        f"/api/v1/operations/contacts/ITAJAI/followups/{call['id']}/done",
        json={"expected_revision":call["revision"]})
    assert done.status_code==200,done.text
    assert done.json()["followup_done_at"] is not None
    assert client.get("/api/v1/operations/contacts/ITAJAI/followups?state=abertos").json()["total"]==0
    again=client.post(
        f"/api/v1/operations/contacts/ITAJAI/followups/{call['id']}/done",
        json={"expected_revision":done.json()["revision"]})
    assert again.status_code==409
    resched=client.post(
        f"/api/v1/operations/contacts/ITAJAI/followups/{call['id']}/reschedule",
        json={"next_on":"2027-02-01","expected_revision":done.json()["revision"]})
    assert resched.status_code==200,resched.text
    assert resched.json()["followup_done_at"] is None
    assert resched.json()["next_on"]=="2027-02-01"


def test_inactivity_setting_and_metrics(env):
    client,*_=env
    settings=client.get("/api/v1/operations/contacts/ITAJAI/settings")
    assert settings.status_code==200
    assert settings.json()["inactivity_days"]==45
    updated=client.put("/api/v1/operations/contacts/ITAJAI/settings",
                       json={"inactivity_days":60})
    assert updated.status_code==200
    assert updated.json()["inactivity_days"]==60
    create(client,confirm=True,name="Compra Recente",city="Itajaí",
           tag="Linha Leve",status="ativo",contact_person="Rui",
           last_purchase_on="2099-01-01")  # futuro: nunca inativo
    old=create(client,confirm=True,name="Compra Antiga",city="Itajaí",
               tag="Linha Leve",status="ativo",contact_person="Téo",
               last_purchase_on="2020-01-01")
    metrics=client.get("/api/v1/operations/contacts/ITAJAI/metrics/2026/10").json()
    assert metrics["clients_total"]==2
    assert metrics["inactive_by_purchases"]==1
    assert metrics["by_status"]["ativo"]==2
    assert metrics["inactivity_days"]==60


def workbook(sheets:dict[str,list[list]])->bytes:
    book=openpyxl.Workbook()
    first=True
    for name,rows in sheets.items():
        ws=book.active if first else book.create_sheet()
        if first:
            ws.title=name;first=False
        else:
            ws.title=name
        for row in rows:ws.append(row)
    buffer=io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()

HEADER=["EMPRESA","CONTATO","CELULAR","PESSOA","DATA ANIVER","STATUS","TAG",
        "DATA CONTATO","OBS."]


def test_import_preview_and_commit(env):
    client,*_=env
    data=workbook({
        "ITAJAÍ":[["ITAJAÍ"],HEADER,
                  ["Oficina do Zé","47 3333-1111",None,"ZÉ","20/03","Ativo",
                   "Linha Leve","10/10/2026","OBS LONGA "*40]],
        "NAVEGANTES":[["NAVEGANTES"],HEADER,
                      ["Auto Naval",None,"47 98888-7777","NINA",None,"Prospect",
                       "Autopeças","2026-09-15",None]],
        "COP":[[None],HEADER,[None],[None]],
    })
    preview=client.post("/api/v1/operations/contacts/ITAJAI/import/preview",
                        files={"file":("carteira.xlsx",data,
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert preview.status_code==201,preview.text
    body=preview.json()
    assert body["rows_total"]==2
    assert {c["city"]:c["total"] for c in body["cities"]}=={"ITAJAÍ":1,"NAVEGANTES":1}
    rows={r["name"]:r for r in body["rows"]}
    assert rows["Oficina do Zé"]["birthday_day"]==20
    assert rows["Oficina do Zé"]["birthday_month"]==3
    assert rows["Auto Naval"]["status"]=="prospect"
    assert rows["Auto Naval"]["birthday_day"] is None
    commit=client.post(
        f"/api/v1/operations/contacts/ITAJAI/import/{body['session_id']}/commit",
        json={"decisions":{},"confirm":True})
    assert commit.status_code==200,commit.text
    assert commit.json()["report"]["imported"]==2
    assert commit.json()["report"]["warnings"]>=0
    detail=client.get("/api/v1/operations/contacts/ITAJAI/clients?q=oficina do zé").json()
    assert detail["total"]==1
    saved=detail["items"][0]
    assert saved["birthday"]=="20/03"
    assert saved["status"]=="ativo"
    assert saved["notes"].startswith("OBS LONGA")
    assert saved["last_contact_on"]=="2026-10-10"
    # data de contato NAO vira ultima compra
    assert saved["last_purchase_on"] is None
    # segunda importacao do mesmo arquivo sugere atualizacao, nao duplica
    again=client.post("/api/v1/operations/contacts/ITAJAI/import/preview",
                      files={"file":("carteira.xlsx",data)})
    row=again.json()["rows"][0]
    assert row["suggested"]=="update"
    assert any("nome" in m["kinds"] for m in row["matches"])
    commit2=client.post(
        f"/api/v1/operations/contacts/ITAJAI/import/{again.json()['session_id']}/commit",
        json={"decisions":{},"confirm":True})
    assert commit2.json()["report"]["updated"]==2
    assert client.get("/api/v1/operations/contacts/ITAJAI/clients").json()["total"]==2


def test_import_respects_decisions_and_permission(env):
    client,identity,*_=env
    existing=create(client,confirm=True,name="Oficina do Zé",city="Itajaí",
                    tag="Linha Leve",status="ativo",contact_person="Zé",
                    phone="47 3333-1111").json()["client"]
    data=workbook({"ITAJAÍ":[["ITAJAÍ"],HEADER,
        ["Oficina do Zé","47 3333-1111",None,"ZÉ","20/03","Ativo","Linha Leve",
         "10/10/2026","obs"],
        ["Nova Casa",None,"47 97777-6666","MARI",None,"Ativo","Frotista",
         None,None]]})
    preview=client.post("/api/v1/operations/contacts/ITAJAI/import/preview",
                        files={"file":("carteira.xlsx",data)}).json()
    decisions={
        str(preview["rows"][0]["index"]):{"action":"skip"},
        str(preview["rows"][1]["index"]):{"action":"import","city":"Balneário Camboriú"},
    }
    commit=client.post(
        f"/api/v1/operations/contacts/ITAJAI/import/{preview['session_id']}/commit",
        json={"decisions":decisions,"confirm":True}).json()
    assert commit["report"]["skipped"]==1
    assert commit["report"]["imported"]==1
    moved=client.get("/api/v1/operations/contacts/ITAJAI/clients?q=nova casa").json()
    assert moved["items"][0]["city"]=="Balneário Camboriú"
    kept=client.get(f"/api/v1/operations/contacts/ITAJAI/clients/{existing['id']}").json()
    assert kept["notes"] is None  # decisao 'skip' preserva o cadastro


def test_seller_registers_contacts_only_with_permission(env):
    client,identity,engine,admin,seller,outsider=env
    cid=create(client,confirm=True,**full_client()).json()["client"]["id"]
    identity["actor"]=seller
    call=client.post("/api/v1/operations/contacts/ITAJAI/calls",json={
        "client_id":cid,"seller_id":str(seller.id),"date":"2026-10-10",
        "channel":"ligacao","outcome":"outro"})
    assert call.status_code==201,call.text
    created=client.post("/api/v1/operations/contacts/ITAJAI/clients",json={
        "name":"Cliente do Vendedor","origin":"outro","city":"Itajaí",
        "contact_person":"Ana","phone":"47 3222-0000","tag":"Linha Leve",
        "status":"ativo"})
    assert created.status_code==201
    assert client.put("/api/v1/operations/contacts/ITAJAI/settings",
                      json={"inactivity_days":30}).status_code==403
    assert client.post("/api/v1/operations/contacts/ITAJAI/import/preview",
                       files={"file":("a.xlsx",b"xx")}).status_code==403
    identity["actor"]=outsider
    assert client.get("/api/v1/operations/contacts/ITAJAI/clients").status_code==403
    assert client.post("/api/v1/operations/contacts/ITAJAI/clients",json={
        "name":"X","origin":"outro"}).status_code==403


def test_audit_records_warnings_and_imports(env):
    client,_,engine,*_=env
    create(client,name="Audit Me",phone="47 91111-2222",city="Itajaí",
           contact_person="Ivo",tag="Linha Leve",status="ativo")
    create(client,name="Audit Me 2",phone="47911112222",city="Itajaí",
           contact_person="Ivo",tag="Linha Leve",status="ativo",confirm=True)
    client.put("/api/v1/operations/contacts/ITAJAI/settings",
               json={"inactivity_days":50})
    with Session(engine) as db:
        actions=[e.action for e in db.scalars(select(AuditEvent)).all()]
    assert "telemarketing.client.created" in actions
    assert "telemarketing.settings.updated" in actions
    with Session(engine) as db:
        created=[e for e in db.scalars(select(AuditEvent)).all()
                 if e.action=="telemarketing.client.created"]
    assert any("telefone_duplicado" in (e.details or {}).get("confirmed_warnings",[])
               for e in created)
