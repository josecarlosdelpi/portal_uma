"""DRE Gerencial — Previa: apuracao, classificacao, qualidade e permissao.

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
from app.dre_classification import classify
from app.main import app
from app.models import (
    Base, GroupPermission, Store, User, UserPermissionOverride,
)
from tests.access_helpers import seed_admin_access, seed_group

HEADER_VENDAS = (
    "data;loja;loja_descricao;id_vendedor;nome_vendedor;cnpj_cliente;"
    "razao_cliente;id_produto;produto_descricao;produto_unidade;"
    "quantidade;valor_unitario;valor_total;custo_unitario\n"
)
HEADER_DEVOLUCOES = (
    "data;loja;loja_descricao;cnpj_cliente;razao_cliente;id_produto;"
    "produto_descricao;produto_unidade;quantidade;valor_unitario;valor_total\n"
)
HEADER_DESPESAS = (
    "loja;loja_descricao;nr_documento;nr_parcela;cnpj_fornecedor;"
    "nome_fornecedor;dt_emissao;dt_vencimento;dt_pagamento;valor_original;"
    "acrescimos;descontos;valor_liquido;categoria;nr_conta;descricao_conta;"
    "situacao\n"
)

VENDAS = HEADER_VENDAS + "\n".join([
    # outubro: receita JOI 180 / custo informado 60; TUB 30 / 21
    "15/10/2026;1;Joinville;7;MARIA;000;CONSUMIDOR;P1;MANGA;KG;2;50;100;30",
    "16/10/2026;1;Joinville;7;MARIA;000;CONSUMIDOR;P2;MANGA;KG;1;80;80;",
    "17/10/2026;2;Tubarao;4;JOAO;000;CONSUMIDOR;P3;MANGA;PC;3;10;30;7",
    # janeiro p/ acumulado
    "05/01/2026;1;Joinville;7;MARIA;000;CONSUMIDOR;P4;MANGA;KG;1;50;50;10",
]) + "\n"

DEVOLUCOES = HEADER_DEVOLUCOES + (
    "18/10/2026;2;Tubarao;000;CONSUMIDOR;P3;MANGA;PC;1;55;55\n"
)

DEVOLUCOES_QUEBRADO = (
    "coluna_a;coluna_b\n1;2\n"
)

DESPESAS = HEADER_DESPESAS + "\n".join([
    # comercial 100 JOI | operacional 200 JOI + 1000 TUB | DAS 500 compartilhado
    "1;Joinville;D1;1;111;FORN FRETE;01/10/2026;10/10/2026;;100;0;0;100;Despesa;50;Fretes;Aberto",
    "1;Joinville;D4;1;;FUNDO DE GARANTIA DO TEMPO DE SERVICO;01/10/2026;07/10/2026;07/10/2026;200;0;0;200;Despesa;67;FGTS;Pago",
    "2;Tubarao;D2;1;222;FORN ALUGUEL;01/10/2026;05/10/2026;05/10/2026;1000;0;0;1000;Despesa;27;Alugueis;Pago",
    "1;Joinville;D3;1;;GUIA SIMPLES NACIONAL DAS;01/10/2026;20/10/2026;20/10/2026;500;0;0;500;Despesa;67;GPS FGTS;Pago",
    # excluidos / a classificar
    "1;Joinville;D5;1;;GUIA DA PREVIDENCIA SOCIAL - GPS;01/10/2026;07/10/2026;07/10/2026;150;0;0;150;Despesa;67;GPS;Pago",
    "1;Joinville;D6;1;333;BANCO FICTICIO;01/10/2026;15/10/2026;;900;0;0;900;Despesa;26;Financiamento;Aberto",
    "3;Itajai;D7;1;444;LOJA MOVEIS;01/10/2026;15/10/2026;;300;0;0;300;Despesa;21;Imobilizado;Aberto",
    "1;Joinville;D8;1;555;FORN PECAS;01/10/2026;15/10/2026;;5000;0;0;5000;Compra p/ Revenda;80;Compras;Aberto",
    "2;Tubarao;D9;1;666;FORN X;01/10/2026;16/10/2026;;700;0;0;700;Compra p/ Revenda;60;Salario;Aberto",
    "1;Joinville;D10;1;777;FORN Y;01/10/2026;18/10/2026;;80;0;0;80;Despesa;94;Taxas;Aberto",
    "1;Joinville;D11;1;888;FORN Z;01/10/2026;19/10/2026;;60;0;0;60;Despesa;999;Conta Nova;Aberto",
    # novembro (fora do recorte de outubro)
    "1;Joinville;D12;1;999;FORN W;01/11/2026;05/11/2026;;40;0;0;40;Despesa;27;Alugueis;Aberto",
]) + "\n"


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
            id=uuid4(), auth_subject="dre-root", display_name="Root",
            profile="administrator", is_superadmin=True, active=True)
        admin = User(
            id=uuid4(), auth_subject="dre-admin", display_name="Admin",
            profile="administrator", is_superadmin=False, active=True)
        seller = User(
            id=uuid4(), auth_subject="dre-seller", display_name="Vendedor",
            profile="seller", is_superadmin=False, active=True)
        db.add_all([superadmin, admin, seller])
        db.flush()
        seed_admin_access(db, admin)
        group = seed_group(
            db, "Vendedores Joinville", ["JOINVILLE"], ["daily_tasks.view"],
            [seller])
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


def upload_vendas(client, content=VENDAS):
    return client.post("/api/v1/sales/imports/vendas",
                       files={"file": ("Vendas.csv", content.encode(), "text/csv")})


def upload_devolucoes(client, content=DEVOLUCOES):
    return client.post("/api/v1/sales/imports/devolucoes",
                       files={"file": ("Devolucoes.csv", content.encode(), "text/csv")})


def upload_despesas(client, content=DESPESAS):
    return client.post("/api/v1/finance/import",
                       files={"file": ("Despesas.csv", content.encode(), "text/csv")})


def seed_all(client):
    assert upload_vendas(client).status_code == 200
    assert upload_despesas(client).status_code == 200


def by_key(preview, key):
    return next(row for row in preview["rows"] if row["key"] == key)


# ---------- classificacao (unidade pura) ----------

def test_classificacao_barreira_compra_revenda():
    result = classify(category="compra_revenda", account_code="60",
                      supplier_name="FORN X")
    assert result.bucket == "compra_revenda"
    assert result.reason == "barreira_categoria"


def test_classificacao_excecoes_conta_67():
    das = classify(category="despesa", account_code="67",
                   supplier_name="GUIA SIMPLES NACIONAL DAS")
    assert das.bucket == "das_identificado"
    assert das.allocation == "shared"
    fgts = classify(category="despesa", account_code="67",
                    supplier_name="FUNDO DE GARANTIA DO TEMPO DE SERVICO")
    assert fgts.bucket == "despesa_operacional"
    gps = classify(category="despesa", account_code="67",
                   supplier_name="GUIA DA PREVIDENCIA SOCIAL - GPS")
    assert gps.bucket == "a_classificar"
    outro = classify(category="despesa", account_code="67",
                     supplier_name="SINDICATO QUALQUER")
    assert outro.bucket == "a_classificar"


def test_classificacao_codigo_e_desconhecido():
    assert classify(category="despesa", account_code="50",
                    supplier_name="X").bucket == "despesa_comercial"
    assert classify(category="despesa", account_code="27",
                    supplier_name="X").bucket == "despesa_operacional"
    assert classify(category="despesa", account_code="26",
                    supplier_name="X").bucket == "financiamento"
    assert classify(category="despesa", account_code="21",
                    supplier_name="X").bucket == "imobilizado"
    novo = classify(category="despesa", account_code="777", supplier_name="X")
    assert novo.bucket == "a_classificar" and novo.reason == "sem_regra"
    sem_conta = classify(category="despesa", account_code=None,
                         supplier_name="X")
    assert sem_conta.bucket == "a_classificar"


# ---------- previa consolidada ----------

def test_previa_outubro_consolidado(env):
    c, *_ = env
    seed_all(c)
    res = c.get("/api/v1/dre/preview?month=2026-10&mode=month")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["disclaimer"].startswith("DRE GERENCIAL PRELIMINAR")
    assert data["basis"].startswith("valores financeiros por vencimento")
    assert data["columns"] == ["ITAJAI", "JOINVILLE", "TUBARAO",
                               "COMPARTILHADO", "UMA"]

    receita = by_key(data, "receita")["values"]
    assert receita["JOINVILLE"] == "180.00"
    assert receita["TUBARAO"] == "30.00"
    assert receita["ITAJAI"] is None          # mes sem vendas != zero
    assert receita["UMA"] == "210.00"

    cmv = by_key(data, "cmv")["values"]
    assert cmv["JOINVILLE"] == "60.00"
    assert cmv["TUBARAO"] == "21.00"
    assert cmv["UMA"] == "81.00"

    margem = by_key(data, "margem")["values"]
    assert margem["JOINVILLE"] == "120.00"
    assert margem["TUBARAO"] == "9.00"
    assert margem["UMA"] == "129.00"

    comercial = by_key(data, "despesa_comercial")["values"]
    assert comercial["JOINVILLE"] == "100.00"
    assert comercial["UMA"] == "100.00"

    operacional = by_key(data, "despesa_operacional")["values"]
    assert operacional["JOINVILLE"] == "200.00"   # FGTS (conta 67 -> pessoal)
    assert operacional["TUBARAO"] == "1000.00"
    assert operacional["UMA"] == "1200.00"

    das = by_key(data, "das")["values"]
    assert das["COMPARTILHADO"] == "500.00"       # nunca integral em Joinville
    assert das["JOINVILLE"] == "0.00"
    assert das["UMA"] == "500.00"

    saldo = by_key(data, "saldo")["values"]
    assert saldo["JOINVILLE"] == "-180.00"        # 120 - (100+200)
    assert saldo["TUBARAO"] == "-991.00"          # 9 - 1000
    assert saldo["UMA"] == "-1671.00"             # 129 - (100+1200+500)
    assert saldo["COMPARTILHADO"] is None         # sem base de receita

    excluded = {e["bucket"]: e for e in data["excluded"]}
    assert excluded["compra_revenda"]["amount"] == "5700.00"  # 5000 + 700
    assert excluded["compra_revenda"]["count"] == 2
    assert excluded["financiamento"]["amount"] == "900.00"
    assert excluded["imobilizado"]["amount"] == "300.00"
    assert excluded["a_classificar"]["amount"] == "290.00"    # 150+80+60
    assert excluded["a_classificar"]["count"] == 3

    codes = {w["code"] for w in data["warnings"]}
    assert "custo_ausente" in codes              # 1 linha sem custo
    assert "a_classificar" in codes
    assert "mes_sem_vendas" in codes             # Itajai sem vendas


def test_previa_devolucoes_separadas_sem_abater(env):
    c, *_ = env
    seed_all(c)
    assert upload_devolucoes(c).status_code == 200
    data = c.get("/api/v1/dre/preview?month=2026-10").json()
    devol = by_key(data, "devolucoes")
    assert devol["kind"] == "memo"               # nao entra no saldo
    assert devol["values"]["TUBARAO"] == "55.00"
    # resultado nao muda com devolucoes validas
    assert by_key(data, "saldo")["values"]["UMA"] == "-1671.00"


def test_previa_devolucoes_indisponiveis(env):
    c, *_ = env
    seed_all(c)
    assert upload_devolucoes(c).status_code == 200
    assert upload_devolucoes(c, DEVOLUCOES_QUEBRADO).status_code == 422
    data = c.get("/api/v1/dre/preview?month=2026-10").json()
    devol = by_key(data, "devolucoes")
    assert devol["state"] == "unavailable"
    assert all(v is None for v in devol["values"].values())
    codes = {w["code"] for w in data["warnings"]}
    assert "devolucoes_indisponiveis" in codes
    # demais linhas continuam calculadas — DRE nao cai por devolucoes
    assert by_key(data, "receita")["values"]["UMA"] == "210.00"


def test_previa_mes_sem_vendas_e_sem_saldo_sem_despesas(env):
    c, *_ = env
    seed_all(c)
    data = c.get("/api/v1/dre/preview?month=2026-12").json()
    receita = by_key(data, "receita")["values"]
    assert receita["JOINVILLE"] is None          # sem dados, nunca zero
    despesas = by_key(data, "despesa_operacional")["values"]
    assert despesas["JOINVILLE"] is None         # fora da cobertura do arquivo
    saldo = by_key(data, "saldo")["values"]
    assert saldo["JOINVILLE"] is None
    codes = {w["code"] for w in data["warnings"]}
    assert "despesas_fora_cobertura" in codes


def test_previa_fonte_despesas_falha_deixa_saldo_oculto(env):
    c, *_ = env
    seed_all(c)
    bad = HEADER_DESPESAS + "1;X;D1;1;1;FORN;xx;10/10/2026;;a;0;0;a;Despesa;50;x;Aberto\n"
    assert upload_despesas(c, bad).status_code == 422
    data = c.get("/api/v1/dre/preview?month=2026-10").json()
    assert data["sources"]["despesas"]["availability"] == "unavailable"
    assert by_key(data, "despesa_operacional")["values"]["JOINVILLE"] is None
    assert by_key(data, "saldo")["values"]["UMA"] is None
    # receita segue exibida: fonte de vendas nao foi afetada
    assert by_key(data, "receita")["values"]["JOINVILLE"] == "180.00"


def test_previa_acumulado_ano(env):
    c, *_ = env
    seed_all(c)
    data = c.get("/api/v1/dre/preview?month=2026-10&mode=ytd").json()
    assert data["period"]["first"] == "2026-01-01"
    receita = by_key(data, "receita")["values"]
    assert receita["JOINVILLE"] == "230.00"      # 180 out + 50 jan
    operacional = by_key(data, "despesa_operacional")["values"]
    # novembro esta fora do acumulado ate outubro
    assert operacional["JOINVILLE"] == "200.00"


def test_cmv_arredondamento_por_linha(env):
    """Politica unica: cada linha a centavos (ROUND_HALF_UP), depois soma.
    1,005 x 10,55 = 10,60275 -> 10,60 por linha; duas linhas = 21,20
    (somar o bruto primeiro daria 21,21)."""
    c, *_ = env
    vendas = HEADER_VENDAS + "\n".join([
        "15/10/2026;1;Joinville;7;MARIA;000;CONSUMIDOR;P1;MANGA;KG;1,005;10,55;10,60;10,55",
        "16/10/2026;1;Joinville;7;MARIA;000;CONSUMIDOR;P1;MANGA;KG;1,005;10,55;10,60;10,55",
    ]) + "\n"
    assert upload_vendas(c, vendas).status_code == 200
    data = c.get("/api/v1/dre/preview?month=2026-10").json()
    assert "ROUND_HALF_UP" in data["rounding_policy"]
    cmv = by_key(data, "cmv")["values"]
    assert cmv["JOINVILLE"] == "21.20"           # por linha, nao 21.21


def test_previa_loja_unica_sem_compartilhado(env):
    c, *_ = env
    seed_all(c)
    data = c.get("/api/v1/dre/preview?month=2026-10&store=JOINVILLE").json()
    assert data["columns"] == ["JOINVILLE"]
    das = by_key(data, "das")["values"]
    assert das["JOINVILLE"] == "0.00"            # DAS nao entra na loja
    assert data["shared_memo"]["amount"] == "500.00"
    saldo = by_key(data, "saldo")["values"]
    assert saldo["JOINVILLE"] == "-180.00"


# ---------- detalhamento e classificacao ----------

def test_detalhamento_por_grupo(env):
    c, *_ = env
    seed_all(c)
    res = c.get("/api/v1/dre/lines?bucket=a_classificar&month=2026-10")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total"] == 3
    assert data["sum_amount"] == "290.00"
    suppliers = {item["supplier_name"] for item in data["items"]}
    assert "GUIA DA PREVIDENCIA SOCIAL - GPS" in suppliers
    item = next(i for i in data["items"] if i["account_code"] == "999")
    assert item["rule"] == "sem_regra"
    assert item["allocation_provisional"] is True

    das = c.get("/api/v1/dre/lines?bucket=das_identificado&month=2026-10").json()
    assert das["total"] == 1
    assert das["items"][0]["allocation"] == "COMPARTILHADO"
    assert "DAS" in das["items"][0]["rule_note"]


def test_visao_classificacao_somente_leitura(env):
    c, *_ = env
    seed_all(c)
    res = c.get("/api/v1/dre/classification")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["editable"] is False
    assert data["rules_origin"] == "default"     # sem regras na tabela (sqlite)
    accounts = {a["account_code"]: a for a in data["accounts"]}
    assert accounts["67"]["mixed"] is True       # conta mista nunca integral
    assert accounts["67"]["buckets"]["a_classificar"]["amount"] == "150.00"
    assert accounts["80"]["dominant_bucket"] == "compra_revenda"
    assert accounts["999"]["dominant_bucket"] == "a_classificar"


# ---------- autorizacao ----------

def test_dre_negado_para_perfis_sem_concessao(env):
    c, actor, _, _, admin, seller, _ = env
    actor["user"] = admin
    assert c.get("/api/v1/dre/preview").status_code == 403
    assert c.get("/api/v1/dre/lines?bucket=a_classificar").status_code == 403
    assert c.get("/api/v1/dre/classification").status_code == 403
    actor["user"] = seller
    assert c.get("/api/v1/dre/preview").status_code == 403


def test_dre_concessao_explicita_limitada_a_loja(env):
    c, actor, engine, _, _, seller, group_id = env
    seed_all(c)
    with Session(engine) as db:
        db.add(GroupPermission(group_id=group_id, code="dre.view", granted=True))
        db.commit()
    actor["user"] = seller
    res = c.get("/api/v1/dre/preview?month=2026-10")
    assert res.status_code == 200
    data = res.json()
    assert data["columns"] == ["JOINVILLE"]      # sem consolidado das 3 lojas
    assert data["consolidated"] is False
    # loja fora do escopo e consolidado UMA continuam negados
    assert c.get("/api/v1/dre/preview?store=TUBARAO").status_code == 403
    assert "COMPARTILHADO" not in data["columns"]


def test_dre_concessao_por_excecao_individual(env):
    c, actor, engine, _, admin, _, _ = env
    with Session(engine) as db:
        db.add(UserPermissionOverride(
            user_id=admin.id, code="dre.view", granted=True))
        db.commit()
    actor["user"] = admin
    assert c.get("/api/v1/dre/preview").status_code == 200


def test_me_expoe_feature_dre(env):
    c, actor, _, _, admin, _, _ = env
    assert c.get("/api/v1/me").json()["features"]["dre"] is True
    actor["user"] = admin
    assert c.get("/api/v1/me").json()["features"]["dre"] is False


def test_sem_dados_resposta_coerente(env):
    c, *_ = env
    data = c.get("/api/v1/dre/preview?month=2026-10").json()
    receita = by_key(data, "receita")["values"]
    assert all(v is None for v in receita.values())
    assert data["sources"]["vendas"]["availability"] == "missing"
    assert data["sources"]["despesas"]["availability"] == "missing"
