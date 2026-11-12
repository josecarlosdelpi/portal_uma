"""Financeiro: importacao idempotente, snapshot, permissões e consultas.

Fixtures usam apenas dados ficticios; nunca subir dados reais do ERP.
"""
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
    Base, ErpImportBatch, FinancialObligation, GroupMembership,
    GroupPermission, Store, StoreGroup, User, UserPermissionOverride,
)

HEADER = ("cnpj_fornecedor;nome_fornecedor;valor;dt_vencimento;dt_pagamento;"
          "categoria;loja;loja_descricao;situacao\n")

SNAPSHOT_1 = HEADER + (
    "11111111000100;FORNECEDOR ALFA LTDA;1000,50;05/10/2026;05/10/2026;Compra p/ Revenda;1;Joinville;Pago\n"
    "22222222000100;FORNECEDOR BETA SA;250;10/11/2026;;Despesa;2;Tubarao;Aberto\n"
    ";GUIA IMPOSTO FICTICIO;300;20/11/2026;20/11/2026;Despesa;1;Joinville;Pago\n"
    "11111111000100;FORNECEDOR ALFA LTDA;1000,50;05/10/2026;05/10/2026;Compra p/ Revenda;1;Joinville;Pago\n"
    "33333333000100;FORNECEDOR GAMMA;99,90;15/12/2026;;Compra p/ Revenda;3;Itajai;Aberto\n"
)

# Mesma base, com o lancamento BETA quitado e um novo titulo aberto.
SNAPSHOT_2 = HEADER + (
    "11111111000100;FORNECEDOR ALFA LTDA;1000,50;05/10/2026;05/10/2026;Compra p/ Revenda;1;Joinville;Pago\n"
    "22222222000100;FORNECEDOR BETA SA;250;10/11/2026;12/11/2026;Despesa;2;Tubarao;Pago\n"
    ";GUIA IMPOSTO FICTICIO;300;20/11/2026;20/11/2026;Despesa;1;Joinville;Pago\n"
    "11111111000100;FORNECEDOR ALFA LTDA;1000,50;05/10/2026;05/10/2026;Compra p/ Revenda;1;Joinville;Pago\n"
    "33333333000100;FORNECEDOR GAMMA;99,90;15/12/2026;;Compra p/ Revenda;3;Itajai;Aberto\n"
    "66666666000100;FORNECEDOR ZETA;42;05/01/2027;;Despesa;2;Tubarao;Aberto\n"
)

INVALID = HEADER + "111;FORNECEDOR;abc;01/10/2026;;Despesa;1;Joinville;Aberto\n"


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
        superadmin = User(
            id=uuid4(), auth_subject="fin-root", display_name="Root",
            profile="administrator", is_superadmin=True, active=True)
        admin = User(
            id=uuid4(), auth_subject="fin-admin", display_name="Admin",
            profile="administrator", is_superadmin=False, active=True)
        seller = User(
            id=uuid4(), auth_subject="fin-seller", display_name="Vendedor",
            profile="seller", is_superadmin=False, active=True)
        db.add_all([superadmin, admin, seller])
        db.flush()
        group = StoreGroup(id=uuid4(), store_code="JOINVILLE", name="Joinville", active=True)
        db.add(group)
        db.flush()
        db.add(GroupMembership(user_id=seller.id, group_id=group.id))
        db.add(GroupPermission(group_id=group.id, code="daily_tasks.view", granted=True))
        db.commit()
        group_id = group.id
    actor = {"user": superadmin}
    app.dependency_overrides[current_user] = lambda: actor["user"]

    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = session
    try:
        with TestClient(app) as client:
            yield client, actor, engine, superadmin, admin, seller, group_id
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def upload(client, content=SNAPSHOT_1, name="Despesas.csv"):
    return client.post("/api/v1/finance/import",
                       files={"file": (name, content.encode(), "text/csv")})


def test_importacao_visao_geral_e_reimportacao_idempotente(env):
    c, _, engine, *_ = env
    first = upload(c)
    assert first.status_code == 200, first.text
    assert first.json()["duplicated"] is False
    assert first.json()["batch"]["row_count"] == 5

    again = upload(c)
    assert again.status_code == 200
    assert again.json()["duplicated"] is True

    with Session(engine) as db:
        rows = db.scalars(select(FinancialObligation)).all()
        assert len(rows) == 5  # cardinalidade preservada, sem duplicar

    overview = c.get("/api/v1/finance/overview?month=2026-10")
    assert overview.status_code == 200
    kpis = overview.json()["kpis"]
    assert kpis["open_amount"] == "349.90"       # 250 + 99,90
    assert kpis["paid_month_amount"] == "2001.00"  # 1000,50 x2 (outubro)
    by_cat = overview.json()["by_category"]
    assert by_cat["compra_revenda"]["open_amount"] == "99.90"
    assert by_cat["despesa"]["open_amount"] == "250.00"
    by_store = {s["store_code"]: s for s in overview.json()["by_store"]}
    assert by_store["TUBARAO"]["open_amount"] == "250.00"

    overview_nov = c.get("/api/v1/finance/overview?month=2026-11")
    assert overview_nov.json()["kpis"]["paid_month_amount"] == "300.00"


def test_snapshot_substituido_sem_perder_historico(env):
    c, _, engine, *_ = env
    assert upload(c).status_code == 200
    assert upload(c, SNAPSHOT_2).status_code == 200

    with Session(engine) as db:
        batches = db.scalars(select(ErpImportBatch)).all()
        assert len(batches) == 2
        applied = [b for b in batches if b.status == "APPLIED"]
        assert {b.rows_applied for b in applied} == {5, 6}
        # lotes antigos preservados: 5 + 6 obrigacoes historicas
        assert len(db.scalars(select(FinancialObligation)).all()) == 11

    # consultas veem apenas o snapshot vigente: BETA agora consta como pago
    paid = c.get("/api/v1/finance/payments?paid_from=2026-11-01&paid_to=2026-11-30")
    assert paid.status_code == 200
    assert paid.json()["sum_amount"] == "550.00"  # 300 (20/11) + 250 (12/11)
    open_q = c.get("/api/v1/finance/obligations?status=aberto")
    assert open_q.json()["total"] == 2           # GAMMA + ZETA


def test_importacao_invalida_registra_falha_sem_alterar_dados(env):
    c, _, engine, *_ = env
    assert upload(c).status_code == 200
    bad = upload(c, INVALID, "quebrado.csv")
    assert bad.status_code == 422

    with Session(engine) as db:
        batches = db.scalars(select(ErpImportBatch)).all()
        assert len(batches) == 2
        failed = [b for b in batches if b.status == "FAILED"]
        assert len(failed) == 1
        assert len(db.scalars(select(FinancialObligation)).all()) == 5

    listed = c.get("/api/v1/finance/batches")
    assert listed.status_code == 200
    kinds = {item["status"] for item in listed.json()["items"]}
    assert kinds == {"imported", "failed"}
    current = [i for i in listed.json()["items"] if i["is_current"]]
    assert len(current) == 1


def test_contas_a_pagar_filtros_ordenacao_e_paginacao(env):
    c, *_ = env
    assert upload(c).status_code == 200

    abertas = c.get("/api/v1/finance/obligations?status=aberto&sort=-amount")
    assert abertas.status_code == 200
    items = abertas.json()["items"]
    assert [i["supplier_name"] for i in items] == [
        "FORNECEDOR BETA SA", "FORNECEDOR GAMMA"]
    assert abertas.json()["sum_amount"] == "349.90"

    por_loja = c.get("/api/v1/finance/obligations?store=TUBARAO")
    assert por_loja.json()["total"] == 1

    por_cat = c.get("/api/v1/finance/obligations?category=compra_revenda")
    assert por_cat.json()["total"] == 3

    janela = c.get("/api/v1/finance/obligations?due_from=2026-11-01&due_to=2026-11-30")
    assert janela.json()["total"] == 2  # BETA (10/11) + GUIA (20/11)

    busca = c.get("/api/v1/finance/obligations?supplier=gamma")
    assert busca.json()["total"] == 1

    paginado = c.get("/api/v1/finance/obligations?page_size=2&page=2")
    assert paginado.json()["total"] == 5 and len(paginado.json()["items"]) == 2


def test_pagamentos_agregacoes(env):
    c, *_ = env
    assert upload(c).status_code == 200
    res = c.get("/api/v1/finance/payments")
    assert res.status_code == 200
    assert res.json()["total"] == 3
    stores = {s["store_code"]: s for s in res.json()["by_store"]}
    assert stores["JOINVILLE"]["amount"] == "2301.00"
    cats = res.json()["by_category"]
    assert cats["compra_revenda"]["amount"] == "2001.00"
    assert cats["despesa"]["amount"] == "300.00"


def test_compras_para_revenda(env):
    c, *_ = env
    assert upload(c).status_code == 200
    res = c.get("/api/v1/finance/purchases")
    assert res.status_code == 200
    totals = res.json()["totals"]
    assert totals["amount"] == "2100.90"        # 2001,00 + 99,90
    assert totals["paid_amount"] == "2001.00"
    assert totals["open_amount"] == "99.90"
    assert res.json()["top_suppliers"][0]["supplier_name"] == "FORNECEDOR ALFA LTDA"


def test_financeiro_exclusivo_superadmin_sem_concessao(env):
    c, actor, engine, _, admin, seller, _ = env
    actor["user"] = admin
    assert c.get("/api/v1/finance/overview").status_code == 403
    assert upload(c).status_code == 403
    actor["user"] = seller
    assert c.get("/api/v1/finance/overview").status_code == 403
    assert c.get("/api/v1/finance/obligations").status_code == 403
    assert upload(c).status_code == 403


def test_concessao_explicita_de_leitura_por_loja(env):
    c, actor, engine, _, _, seller, group_id = env
    assert upload(c).status_code == 200

    # concessao via grupo da loja (estrutura pronta para liberação futura)
    with Session(engine) as db:
        db.add(GroupPermission(group_id=group_id, code="finance.view", granted=True))
        db.commit()

    actor["user"] = seller
    res = c.get("/api/v1/finance/obligations?store=JOINVILLE")
    assert res.status_code == 200
    assert res.json()["total"] == 3
    # fora da loja autorizada continua negado
    assert c.get("/api/v1/finance/obligations?store=TUBARAO").status_code == 403
    # consolidado limita-se a loja do vendedor
    assert c.get("/api/v1/finance/obligations").json()["total"] == 3
    # importacao continua exclusiva do SuperAdmin
    assert upload(c).status_code == 403


def test_concessao_explicita_para_administrador(env):
    c, actor, engine, _, admin, _, _ = env
    assert upload(c).status_code == 200

    with Session(engine) as db:
        db.add(UserPermissionOverride(
            user_id=admin.id, code="finance.view", granted=True))
        db.commit()

    actor["user"] = admin
    assert c.get("/api/v1/finance/overview").status_code == 200
    assert upload(c).status_code == 403  # importacao nao e concedivel


def test_me_expoe_feature_finance(env):
    c, actor, _, _, admin, _, _ = env
    me = c.get("/api/v1/me").json()
    assert me["features"]["finance"] is True
    actor["user"] = admin
    me = c.get("/api/v1/me").json()
    assert me["features"]["finance"] is False


def test_sem_dados_respostas_vazias_coerentes(env):
    c, *_ = env
    assert c.get("/api/v1/finance/overview").json()["has_data"] is False
    assert c.get("/api/v1/finance/obligations").json()["total"] == 0
    assert c.get("/api/v1/finance/payments").json()["total"] == 0
    assert c.get("/api/v1/finance/purchases").json()["has_data"] is False
    assert c.get("/api/v1/finance/batches").json()["items"] == []
