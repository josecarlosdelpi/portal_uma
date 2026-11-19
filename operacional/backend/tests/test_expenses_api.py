"""Gestao de Despesas: categorias, regras por fornecedor, classificacao
manual persistente (fingerprint), analise por categoria e seguranca.

Fixtures usam apenas dados ficticios; nunca subir dados reais do ERP.
"""
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
    AuditEvent, Base, ExpenseCategory, ExpenseLineClassification,
    Store, SupplierCategoryRule, User, UserPermissionOverride,
)
from tests.access_helpers import seed_admin_access, seed_group

HEADER_DESPESAS = (
    "loja;loja_descricao;nr_documento;nr_parcela;cnpj_fornecedor;"
    "nome_fornecedor;dt_emissao;dt_vencimento;dt_pagamento;valor_original;"
    "acrescimos;descontos;valor_liquido;categoria;nr_conta;descricao_conta;"
    "situacao\n"
)

DESPESAS_V1 = HEADER_DESPESAS + "\n".join([
    # elegiveis (operacionais/comercial/DAS/pendente)
    "1;Joinville;E1;1;12345678000199;SUPER MERCADO GIASSI;01/10/2026;05/10/2026;05/10/2026;300;0;0;300;Despesa;38;Limpeza;Pago",
    "2;Tubarao;E2;1;12345678000199;SUPER MERCADO GIASSI;01/10/2026;06/10/2026;06/10/2026;80;0;0;80;Despesa;38;Limpeza;Pago",
    "1;Joinville;E3;1;;PAPELARIA CENTRAL;01/10/2026;07/10/2026;07/10/2026;45;0;0;45;Despesa;37;Expediente;Pago",
    "1;Joinville;D3;1;;GUIA SIMPLES NACIONAL DAS;01/10/2026;20/10/2026;20/10/2026;500;0;0;500;Despesa;67;GPS FGTS;Pago",
    "2;Tubarao;D2;1;222;FORN ALUGUEL;01/10/2026;05/10/2026;05/10/2026;1000;0;0;1000;Despesa;27;Alugueis;Pago",
    # linhas literalmente identicas -> mesmo fingerprint (classificacao cobre ambas)
    "1;Joinville;D16;1;;FORN LIMPEZA;01/10/2026;09/10/2026;09/10/2026;40;0;0;40;Despesa;38;Limpeza;Pago",
    "1;Joinville;D16;1;;FORN LIMPEZA;01/10/2026;09/10/2026;09/10/2026;40;0;0;40;Despesa;38;Limpeza;Pago",
    # separados da analise operacional (nao elegiveis)
    "1;Joinville;D13;1;333;FORN PECAS;01/10/2026;10/10/2026;10/10/2026;5000;0;0;5000;Compra p/ Revenda;80;Compras;Pago",
    "1;Joinville;E4;1;98765432000111;BANCO X;01/10/2026;08/10/2026;08/10/2026;700;0;0;700;Despesa;15;Financiamento;Pago",
    # aberto nunca entra na analise nem pode ser classificado
    "1;Joinville;F1;1;;FORN FRETE;01/10/2026;10/10/2026;;100;0;0;100;Despesa;50;Fretes;Aberto",
]) + "\n"

# V2: mesmas linhas reordenadas + um lancamento novo + F1 agora pago
DESPESAS_V2 = HEADER_DESPESAS + "\n".join([
    "1;Joinville;F1;1;;FORN FRETE;01/10/2026;10/10/2026;22/10/2026;100;0;0;100;Despesa;50;Fretes;Pago",
    "2;Tubarao;D2;1;222;FORN ALUGUEL;01/10/2026;05/10/2026;05/10/2026;1000;0;0;1000;Despesa;27;Alugueis;Pago",
    "1;Joinville;E5;1;;NOVA PAPELARIA;01/10/2026;15/10/2026;15/10/2026;60;0;0;60;Despesa;37;Expediente;Pago",
    "1;Joinville;D16;1;;FORN LIMPEZA;01/10/2026;09/10/2026;09/10/2026;40;0;0;40;Despesa;38;Limpeza;Pago",
    "1;Joinville;D16;1;;FORN LIMPEZA;01/10/2026;09/10/2026;09/10/2026;40;0;0;40;Despesa;38;Limpeza;Pago",
    "1;Joinville;E1;1;12345678000199;SUPER MERCADO GIASSI;01/10/2026;05/10/2026;05/10/2026;300;0;0;300;Despesa;38;Limpeza;Pago",
    "2;Tubarao;E2;1;12345678000199;SUPER MERCADO GIASSI;01/10/2026;06/10/2026;06/10/2026;80;0;0;80;Despesa;38;Limpeza;Pago",
    "1;Joinville;E3;1;;PAPELARIA CENTRAL;01/10/2026;07/10/2026;07/10/2026;45;0;0;45;Despesa;37;Expediente;Pago",
    "1;Joinville;D3;1;;GUIA SIMPLES NACIONAL DAS;01/10/2026;20/10/2026;20/10/2026;500;0;0;500;Despesa;67;GPS FGTS;Pago",
    "1;Joinville;D13;1;333;FORN PECAS;01/10/2026;10/10/2026;10/10/2026;5000;0;0;5000;Compra p/ Revenda;80;Compras;Pago",
    "1;Joinville;E4;1;98765432000111;BANCO X;01/10/2026;08/10/2026;08/10/2026;700;0;0;700;Despesa;15;Financiamento;Pago",
]) + "\n"

# V3: E1 com valor alterado -> fingerprint quebrado (classificacao vira orfa)
DESPESAS_V3 = HEADER_DESPESAS + "\n".join([
    "1;Joinville;E1;1;12345678000199;SUPER MERCADO GIASSI;01/10/2026;05/10/2026;05/10/2026;350;0;0;350;Despesa;38;Limpeza;Pago",
    "2;Tubarao;E2;1;12345678000199;SUPER MERCADO GIASSI;01/10/2026;06/10/2026;06/10/2026;80;0;0;80;Despesa;38;Limpeza;Pago",
]) + "\n"

OUT = "date_from=2026-10-01&date_to=2026-10-31"


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
            id=uuid4(), auth_subject="ex-root", display_name="Root",
            profile="administrator", is_superadmin=True, active=True)
        admin = User(
            id=uuid4(), auth_subject="ex-admin", display_name="Admin",
            profile="administrator", is_superadmin=False, active=True)
        admin_joi = User(
            id=uuid4(), auth_subject="ex-admin-joi", display_name="Admin JOI",
            profile="administrator", is_superadmin=False, active=True)
        seller = User(
            id=uuid4(), auth_subject="ex-seller", display_name="Vendedor",
            profile="seller", is_superadmin=False, active=True)
        db.add_all([superadmin, admin, admin_joi, seller])
        db.flush()
        seed_admin_access(db, admin)
        # admin_joi: despesas apenas em Joinville (leitura + gestao)
        seed_group(db, "Gestores JOI", ["JOINVILLE"],
                   ["expenses.view", "expenses.manage"], [admin_joi])
        seed_group(db, "Vendedores Joinville", ["JOINVILLE"],
                   ["daily_tasks.view"], [seller])
        db.commit()
    actor = {"user": superadmin}
    app.dependency_overrides[current_user] = lambda: actor["user"]

    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = session
    try:
        with TestClient(app) as client:
            yield client, actor, engine, superadmin, admin, admin_joi, seller
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def upload_despesas(client, content=DESPESAS_V1):
    return client.post("/api/v1/finance/import",
                       files={"file": ("Despesas.csv", content.encode(), "text/csv")})


def seed_all(client):
    assert upload_despesas(client).status_code == 200


def mk_cat(client, name):
    res = client.post("/api/v1/expenses/categories", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def get_lines(client, **kw):
    qs = "&".join(f"{k}={v}" for k, v in kw.items())
    res = client.get(f"/api/v1/expenses/lines?{OUT}&{qs}")
    assert res.status_code == 200, res.text
    return res.json()


def line_by_doc(items, doc):
    return [i for i in items if i["document_number"] == doc]


# ---------- categorias ----------

def test_criar_renomear_desativar_categoria(env):
    c, *_ = env
    seed_all(c)
    cat_id = mk_cat(c, "Materiais de limpeza")
    cats = c.get("/api/v1/expenses/categories").json()["items"]
    assert any(i["id"] == cat_id and i["active"] for i in cats)
    # renomear
    res = c.patch(f"/api/v1/expenses/categories/{cat_id}",
                  json={"name": "Limpeza e higiene"})
    assert res.status_code == 200 and res.json()["name"] == "Limpeza e higiene"
    # desativar preserva o registro
    res = c.patch(f"/api/v1/expenses/categories/{cat_id}",
                  json={"active": False})
    assert res.json()["active"] is False
    cats = c.get("/api/v1/expenses/categories").json()["items"]
    assert any(i["id"] == cat_id for i in cats)


def test_categoria_duplicada_impedida(env):
    c, *_ = env
    seed_all(c)
    mk_cat(c, "Salários")
    for variant in ("salários", " SALÁRIOS ", "Salarios  "):
        res = c.post("/api/v1/expenses/categories", json={"name": variant})
        # 'Salarios' sem acento e nome diferente — aceito; com acento/caso/e
        # espacos, e duplicata e deve falhar
        if variant.strip().casefold() == "salarios":
            assert res.status_code == 201
        else:
            assert res.status_code == 409


def test_desativar_categoria_preserva_classificacao(env):
    c, *_ = env
    seed_all(c)
    cat_id = mk_cat(c, "Limpeza")
    items = get_lines(c, page_size=200)["items"]
    fp = line_by_doc(items, "E1")[0]["fingerprint"]
    res = c.put(f"/api/v1/expenses/lines/{fp}/category",
                json={"category_id": cat_id})
    assert res.status_code == 200
    c.patch(f"/api/v1/expenses/categories/{cat_id}", json={"active": False})
    # a classificacao manual persiste e ainda e exibida
    line = line_by_doc(get_lines(c, page_size=200)["items"], "E1")[0]
    assert line["category_name"] == "Limpeza"
    assert line["origin"] == "manual"


# ---------- regras por fornecedor ----------

def test_regra_fornecedor_por_documento_retroativa(env):
    """Regra criada depois do upload aplica-se retroativamente aos
    lancamentos elegiveis do fornecedor (identificado pelo CNPJ)."""
    c, *_ = env
    seed_all(c)
    cat_id = mk_cat(c, "Materiais de limpeza")
    res = c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199",
        "supplier_label": "SUPER MERCADO GIASSI (12345678000199)",
        "store_code": None, "category_id": cat_id})
    assert res.status_code == 201, res.text
    items = get_lines(c, page_size=200)["items"]
    for doc in ("E1", "E2"):
        line = line_by_doc(items, doc)[0]
        assert line["category_id"] == cat_id
        assert line["origin"] == "rule_general"


def test_regra_especifica_loja_prevalece_sobre_geral(env):
    c, *_ = env
    seed_all(c)
    limpeza = mk_cat(c, "Materiais de limpeza")
    copa = mk_cat(c, "Copa e alimentação")
    c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199",
        "supplier_label": "GIASSI", "store_code": None,
        "category_id": limpeza})
    c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199",
        "supplier_label": "GIASSI", "store_code": "TUBARAO",
        "category_id": copa})
    items = get_lines(c, page_size=200)["items"]
    assert line_by_doc(items, "E2")[0]["category_id"] == copa
    assert line_by_doc(items, "E2")[0]["origin"] == "rule_store"
    assert line_by_doc(items, "E1")[0]["category_id"] == limpeza


def test_regra_fornecedor_sem_documento_por_nome(env):
    """Sem CNPJ confiavel, a regra usa o nome normalizado — nunca
    correspondencia aproximada entre fornecedores."""
    c, *_ = env
    seed_all(c)
    cat_id = mk_cat(c, "Materiais de escritório")
    res = c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "name:PAPELARIA CENTRAL",
        "supplier_label": "PAPELARIA CENTRAL",
        "store_code": None, "category_id": cat_id})
    assert res.status_code == 201
    items = get_lines(c, page_size=200)["items"]
    assert line_by_doc(items, "E3")[0]["category_id"] == cat_id
    # fornecedor de nome diferente permanece sem categoria
    assert line_by_doc(items, "D2")[0]["category_id"] is None


def test_regra_desativada_deixa_de_aplicar(env):
    c, *_ = env
    seed_all(c)
    cat_id = mk_cat(c, "Limpeza")
    rule_id = c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199", "supplier_label": "GIASSI",
        "store_code": None, "category_id": cat_id}).json()["id"]
    c.patch(f"/api/v1/expenses/supplier-rules/{rule_id}",
            json={"active": False})
    items = get_lines(c, page_size=200)["items"]
    assert line_by_doc(items, "E1")[0]["category_id"] is None


# ---------- classificacao manual ----------

def test_classificacao_manual_prevalece_e_remove(env):
    c, *_ = env
    seed_all(c)
    limpeza = mk_cat(c, "Limpeza")
    copa = mk_cat(c, "Copa")
    c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199", "supplier_label": "GIASSI",
        "store_code": None, "category_id": limpeza})
    fp = line_by_doc(get_lines(c, page_size=200)["items"], "E1")[0]["fingerprint"]
    # manual sobrescreve a regra
    res = c.put(f"/api/v1/expenses/lines/{fp}/category",
                json={"category_id": copa})
    assert res.status_code == 200
    line = line_by_doc(get_lines(c, page_size=200)["items"], "E1")[0]
    assert line["category_id"] == copa and line["origin"] == "manual"
    # remover manual -> volta para a regra geral
    res = c.put(f"/api/v1/expenses/lines/{fp}/category",
                json={"category_id": None})
    assert res.status_code == 200
    line = line_by_doc(get_lines(c, page_size=200)["items"], "E1")[0]
    assert line["category_id"] == limpeza and line["origin"] == "rule_general"


def test_linhas_identicas_compartilham_classificacao(env):
    """Duas linhas identicas em todos os campos identitarios sao
    indistinguiveis — a classificacao manual cobre as duas."""
    c, *_ = env
    seed_all(c)
    cat_id = mk_cat(c, "Limpeza")
    dups = line_by_doc(get_lines(c, page_size=200)["items"], "D16")
    assert len(dups) == 2
    assert dups[0]["fingerprint"] == dups[1]["fingerprint"]
    res = c.put(f"/api/v1/expenses/lines/{dups[0]['fingerprint']}/category",
                json={"category_id": cat_id})
    assert res.status_code == 200 and res.json()["rows"] == 2
    dups = line_by_doc(get_lines(c, page_size=200)["items"], "D16")
    assert all(d["category_id"] == cat_id for d in dups)


def test_classificar_linha_nao_elegivel_rejeitado(env):
    """Compras p/ revenda e financiamentos nao recebem categoria gerencial."""
    c, *_ = env
    seed_all(c)
    cat_id = mk_cat(c, "Limpeza")
    items = get_lines(c, page_size=200)["items"]
    for doc in ("D13", "E4"):
        line = line_by_doc(items, doc)[0]
        assert line["eligible"] is False
        res = c.put(f"/api/v1/expenses/lines/{line['fingerprint']}/category",
                    json={"category_id": cat_id})
        assert res.status_code == 422


def test_linha_aberta_nao_aparece(env):
    c, *_ = env
    seed_all(c)
    items = get_lines(c, page_size=200)["items"]
    assert line_by_doc(items, "F1") == []


# ---------- persistencia entre importacoes ----------

def test_classificacao_sobrevive_nova_importacao(env):
    """Reimportar o arquivo (linhas reordenadas + novo lancamento + F1
    agora pago) nao perde classificacoes manuais nem regras."""
    c, *_ = env
    seed_all(c)
    limpeza = mk_cat(c, "Limpeza")
    copa = mk_cat(c, "Copa")
    c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199", "supplier_label": "GIASSI",
        "store_code": None, "category_id": limpeza})
    items = get_lines(c, page_size=200)["items"]
    fp = line_by_doc(items, "E3")[0]["fingerprint"]
    c.put(f"/api/v1/expenses/lines/{fp}/category",
          json={"category_id": copa})
    # nova importacao do arquivo corrigido
    assert upload_despesas(c, DESPESAS_V2).status_code == 200
    items = get_lines(c, page_size=200)["items"]
    # manual persistiu por fingerprint
    e3 = line_by_doc(items, "E3")[0]
    assert e3["category_id"] == copa and e3["origin"] == "manual"
    # regra continua aplicando
    assert line_by_doc(items, "E1")[0]["category_id"] == limpeza
    # lancamento novo sem categoria; F1 pago agora elegivel e sem categoria
    assert line_by_doc(items, "E5")[0]["category_id"] is None
    f1 = line_by_doc(items, "F1")[0]
    assert f1["eligible"] is True and f1["category_id"] is None


def test_fingerprint_quebrado_vira_orfao_sem_transferir(env):
    """Valor alterado pelo ERP quebra a identidade: a classificacao fica
    orfa e sinalizada — nunca migrada por aproximacao."""
    c, *_ = env
    seed_all(c)
    cat_id = mk_cat(c, "Limpeza")
    fp = line_by_doc(get_lines(c, page_size=200)["items"], "E1")[0]["fingerprint"]
    c.put(f"/api/v1/expenses/lines/{fp}/category", json={"category_id": cat_id})
    # nova importacao muda o valor de E1
    assert upload_despesas(c, DESPESAS_V3).status_code == 200
    items = get_lines(c, page_size=200)["items"]
    e1 = line_by_doc(items, "E1")[0]
    # a linha alterada NAO herda a classificacao antiga
    assert e1["fingerprint"] != fp
    assert e1["category_id"] is None
    data = get_lines(c, page_size=200)
    assert data["orphan_classifications"] == 1
    analysis = c.get(f"/api/v1/expenses/analysis?{OUT}").json()
    assert analysis["orphan_classifications"] == 1
    assert any(w["code"] == "classificacoes_orfas"
               for w in analysis["warnings"])
    with Session(env[2]) as db:
        rec = db.query(ExpenseLineClassification).one()
        assert rec.status == "orphan"


# ---------- analise ----------

def test_analise_totais_e_percentuais(env):
    c, *_ = env
    seed_all(c)
    limpeza = mk_cat(c, "Limpeza")
    c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199", "supplier_label": "GIASSI",
        "store_code": None, "category_id": limpeza})
    data = c.get(f"/api/v1/expenses/analysis?{OUT}").json()
    t = data["totals"]
    # elegiveis: E1 300 + E2 80 + E3 45 + D3 500 + D2 1000 + D16 2x40 = 2005
    assert t["paid_total"] == "2005.00"
    # classificados pela regra: E1+E2 = 380
    assert t["classified"] == "380.00"
    assert t["unclassified"] == "1625.00"
    assert t["classified_pct"] == "19.0"
    assert t["unclassified_rows"] == 5
    cats = {i["name"]: i for i in data["by_category"]}
    assert cats["Limpeza"]["total"] == "380.00"
    assert cats["Sem categoria"]["total"] == "1625.00"
    # separados fora dos percentuais
    excl = {e["bucket"]: e for e in data["excluded_natures"]}
    assert excl["compra_revenda"]["total"] == "5000.00"
    assert excl["financiamento"]["total"] == "700.00"


def test_analise_comparativo_lojas_compartilhado(env):
    c, *_ = env
    seed_all(c)
    data = c.get(f"/api/v1/expenses/analysis?{OUT}&store=TODAS").json()
    cols = {s["store"]: s for s in data["by_store"]}
    # DAS compartilhado vai para coluna propria no consolidado
    assert cols["COMPARTILHADO"]["total"] == "500.00"
    assert cols["TUBARAO"]["total"] == "1080.00"
    # JOINVILLE sem DAS: 300+45+80 = 425
    assert cols["JOINVILLE"]["total"] == "425.00"


def test_analise_loja_individual_memo_compartilhado(env):
    c, *_ = env
    seed_all(c)
    data = c.get(f"/api/v1/expenses/analysis?{OUT}&store=JOINVILLE").json()
    assert data["totals"]["paid_total"] == "425.00"
    memo = data["shared_memo"]
    assert memo is not None and memo["amount"] == "500.00"
    # sem coluna compartilhada na visao individual
    assert all(s["store"] != "COMPARTILHADO" for s in data["by_store"])


def test_analise_filtros_situacao_categoria_fornecedor(env):
    c, *_ = env
    seed_all(c)
    limpeza = mk_cat(c, "Limpeza")
    c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199", "supplier_label": "GIASSI",
        "store_code": None, "category_id": limpeza})
    # apenas classificadas
    data = c.get(f"/api/v1/expenses/analysis?{OUT}&situation=classified").json()
    assert data["totals"]["paid_total"] == "380.00"
    # apenas sem categoria
    data = c.get(f"/api/v1/expenses/analysis?{OUT}&situation=unclassified").json()
    assert data["totals"]["paid_total"] == "1625.00"
    # por categoria especifica
    data = c.get(f"/api/v1/expenses/analysis?{OUT}&category_id={limpeza}").json()
    assert data["totals"]["paid_total"] == "380.00"
    # por fornecedor
    data = c.get(f"/api/v1/expenses/analysis?{OUT}&supplier=aluguel").json()
    assert data["totals"]["paid_total"] == "1000.00"


def test_linhas_filtro_sem_categoria(env):
    c, *_ = env
    seed_all(c)
    limpeza = mk_cat(c, "Limpeza")
    c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199", "supplier_label": "GIASSI",
        "store_code": None, "category_id": limpeza})
    data = get_lines(c, situation="unclassified", page_size=200)
    assert all(i["category_id"] is None for i in data["items"])
    assert data["total"] == 5
    data = get_lines(c, situation="classified", page_size=200)
    assert data["total"] == 2


# ---------- seguranca ----------

def test_vendedor_sem_acesso(env):
    c, actor, engine, root, admin, admin_joi, seller = env
    seed_all(c)
    actor["user"] = seller
    assert c.get(f"/api/v1/expenses/analysis?{OUT}").status_code == 403
    assert c.get("/api/v1/expenses/categories").status_code == 403
    res = c.post("/api/v1/expenses/categories", json={"name": "X"})
    assert res.status_code == 403


def test_admin_sem_manage_le_mas_nao_edita(env):
    """Admin com apenas expenses.view nao altera nada."""
    c, actor, engine, root, admin, admin_joi, seller = env
    seed_all(c)
    with Session(engine) as db:
        db.add(UserPermissionOverride(
            user_id=admin.id, code="expenses.view", granted=True))
        db.commit()
    actor["user"] = admin
    assert c.get(f"/api/v1/expenses/analysis?{OUT}").status_code == 200
    assert c.post("/api/v1/expenses/categories",
                  json={"name": "X"}).status_code == 403
    items = c.get(f"/api/v1/expenses/lines?{OUT}").json()["items"]
    fp = items[0]["fingerprint"]
    res = c.put(f"/api/v1/expenses/lines/{fp}/category",
                json={"category_id": "x"})
    assert res.status_code == 403


def test_admin_escopo_loja_nao_edita_regra_geral_nem_outra_loja(env):
    c, actor, engine, root, admin, admin_joi, seller = env
    seed_all(c)
    actor["user"] = admin_joi
    cat_id = mk_cat(c, "Limpeza")  # JOI: permitido
    # regra geral UMA exige as tres lojas -> 403
    res = c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199", "supplier_label": "G",
        "store_code": None, "category_id": cat_id})
    assert res.status_code == 403
    # regra de outra loja -> 403
    res = c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199", "supplier_label": "G",
        "store_code": "TUBARAO", "category_id": cat_id})
    assert res.status_code == 403
    # regra da propria loja -> ok
    res = c.post("/api/v1/expenses/supplier-rules", json={
        "supplier_key": "doc:12345678000199", "supplier_label": "G",
        "store_code": "JOINVILLE", "category_id": cat_id})
    assert res.status_code == 201
    # classificacao em outra loja -> 403
    items = c.get(f"/api/v1/expenses/lines?{OUT}").json()["items"]
    assert all(i["store_code"] == "JOINVILLE" for i in items)
    res = c.get(f"/api/v1/expenses/analysis?{OUT}&store=TUBARAO")
    assert res.status_code == 403


def test_consolidado_proibido_para_escopo_parcial(env):
    """Escopo parcial nunca recebe a visao consolidada das tres lojas."""
    c, actor, engine, root, admin, admin_joi, seller = env
    seed_all(c)
    actor["user"] = admin_joi
    data = c.get(f"/api/v1/expenses/analysis?{OUT}&store=TODAS").json()
    # nao consolidado: apenas a loja autorizada
    assert {s["store"] for s in data["by_store"]} == {"JOINVILLE"}
    assert data["totals"]["paid_total"] == "425.00"


# ---------- auditoria ----------

def test_auditoria_registra_operacoes(env):
    c, _, engine, *_ = env
    seed_all(c)
    cat_id = mk_cat(c, "Limpeza")
    fp = line_by_doc(get_lines(c, page_size=200)["items"], "E1")[0]["fingerprint"]
    c.put(f"/api/v1/expenses/lines/{fp}/category", json={"category_id": cat_id})
    with Session(engine) as db:
        actions = [a.action for a in db.query(AuditEvent).all()]
    assert "expenses.category.create" in actions
    assert "expenses.classify.set" in actions
