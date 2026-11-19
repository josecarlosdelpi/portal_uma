"""Fluxo de Caixa Estimado: entradas por vendas, saidas por pagamento
efetivo, cobertura, autorizacao.

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
    # outubro: JOI 180 | TUB 30 ; janeiro: JOI 50
    "15/10/2026;1;Joinville;7;MARIA;000;CONSUMIDOR;P1;MANGA;KG;2;50;100;30",
    "16/10/2026;1;Joinville;7;MARIA;000;CONSUMIDOR;P2;MANGA;KG;1;80;80;30",
    "17/10/2026;2;Tubarao;4;JOAO;000;CONSUMIDOR;P3;MANGA;PC;3;10;30;7",
    "05/01/2026;1;Joinville;7;MARIA;000;CONSUMIDOR;P4;MANGA;KG;1;50;50;10",
]) + "\n"

DEVOLUCOES = HEADER_DEVOLUCOES + (
    "18/10/2026;2;Tubarao;000;CONSUMIDOR;P3;MANGA;PC;1;55;55\n"
)

DESPESAS = HEADER_DESPESAS + "\n".join([
    # pagos em outubro: operacional JOI 200 / TUB 1000; DAS compartilhado 500;
    # a_classificar JOI 150; compra p/ revenda paga JOI 5000
    "1;Joinville;D4;1;;FUNDO DE GARANTIA DO TEMPO DE SERVICO;01/10/2026;07/10/2026;07/10/2026;200;0;0;200;Despesa;67;FGTS;Pago",
    "2;Tubarao;D2;1;222;FORN ALUGUEL;01/10/2026;05/10/2026;05/10/2026;1000;0;0;1000;Despesa;27;Alugueis;Pago",
    "1;Joinville;D3;1;;GUIA SIMPLES NACIONAL DAS;01/10/2026;20/10/2026;20/10/2026;500;0;0;500;Despesa;67;GPS FGTS;Pago",
    "1;Joinville;D5;1;;GUIA DA PREVIDENCIA SOCIAL - GPS;01/10/2026;07/10/2026;07/10/2026;150;0;0;150;Despesa;67;GPS;Pago",
    "1;Joinville;D13;1;333;FORN PECAS;01/10/2026;10/10/2026;10/10/2026;5000;0;0;5000;Compra p/ Revenda;80;Compras;Pago",
    # duplicados legitimos: mesmos campos, nunca deduplicar (2x 40)
    "1;Joinville;D14;1;;FORN LIMPEZA;01/10/2026;09/10/2026;09/10/2026;40;0;0;40;Despesa;38;Limpeza;Pago",
    "1;Joinville;D15;1;;FORN LIMPEZA;01/10/2026;09/10/2026;09/10/2026;40;0;0;40;Despesa;38;Limpeza;Pago",
    # pago em novembro apesar de vencer em outubro -> sai do recorte de outubro
    "1;Joinville;D16;1;222;FORN ALUGUEL;01/10/2026;15/10/2026;02/11/2026;900;0;0;900;Despesa;27;Alugueis;Pago",
    # abertos nunca sao saida, mesmo vencidos no periodo
    "1;Joinville;D1;1;111;FORN FRETE;01/10/2026;10/10/2026;;100;0;0;100;Despesa;50;Fretes;Aberto",
    "2;Tubarao;D9;1;666;FORN X;01/10/2026;16/10/2026;;700;0;0;700;Compra p/ Revenda;60;Salario;Aberto",
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
            id=uuid4(), auth_subject="cf-root", display_name="Root",
            profile="administrator", is_superadmin=True, active=True)
        admin = User(
            id=uuid4(), auth_subject="cf-admin", display_name="Admin",
            profile="administrator", is_superadmin=False, active=True)
        seller = User(
            id=uuid4(), auth_subject="cf-seller", display_name="Vendedor",
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


OUT = "date_from=2026-10-01&date_to=2026-10-31"


# ---------- apuracao principal ----------

def test_preview_outubro_consolidado(env):
    c, *_ = env
    seed_all(c)
    res = c.get(f"/api/v1/cashflow/preview?{OUT}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["disclaimer"].startswith("FLUXO DE CAIXA ESTIMADO")
    assert data["opening_balance"] == "0.00"
    assert data["entries_source"]["kind"] == "vendas_registradas"
    assert data["entries_source"]["replaceable"] is True
    assert data["columns"] == ["ITAJAI", "JOINVILLE", "TUBARAO",
                               "COMPARTILHADO", "UMA"]

    entries = data["summary"]["entries"]
    assert entries["JOINVILLE"] == "180.00"
    assert entries["TUBARAO"] == "30.00"
    assert entries["ITAJAI"] is None             # sem vendas != zero
    assert entries["UMA"] == "210.00"

    exits = data["summary"]["exits"]
    # JOI: 200 FGTS + 150 GPS + 5000 compra + 2x40 limpeza (sem dedup) = 5430
    assert exits["JOINVILLE"] == "5430.00"
    assert exits["TUBARAO"] == "1000.00"
    assert exits["COMPARTILHADO"] == "500.00"    # DAS compartilhado
    assert exits["UMA"] == "6930.00"
    # aberto vencido no periodo nao e saida; pago em nov tambem nao
    assert "900" not in exits["JOINVILLE"]

    balance = data["summary"]["balance"]
    assert balance["JOINVILLE"] == "-5250.00"    # 180 - 5430
    assert balance["TUBARAO"] == "-970.00"
    assert balance["ITAJAI"] is None             # sem entrada apuravel
    assert balance["COMPARTILHADO"] == "-500.00"
    assert balance["UMA"] == "-6720.00"          # 210 - 6930


def test_composicao_pagamentos_todas_naturezas(env):
    c, *_ = env
    seed_all(c)
    data = c.get(f"/api/v1/cashflow/preview?{OUT}").json()
    payments = {p["bucket"]: p for p in data["payments"]}
    # compra p/ revenda paga entra como saida (nada de CMV aqui)
    assert payments["compra_revenda"]["amount"] == "5000.00"
    assert payments["compra_revenda"]["columns"]["JOINVILLE"] == "5000.00"
    assert payments["despesa_operacional"]["amount"] == "1280.00"  # 200+1000+2x40
    assert payments["das_identificado"]["columns"]["COMPARTILHADO"] == "500.00"
    assert payments["a_classificar"]["amount"] == "150.00"
    assert payments["financiamento"]["amount"] == "0.00"


def test_evolucao_mensal_do_periodo(env):
    c, *_ = env
    seed_all(c)
    res = c.get("/api/v1/cashflow/preview?"
                "date_from=2026-10-01&date_to=2026-11-30")
    data = res.json()
    assert data["period"]["months"] == ["2026-10", "2026-11"]
    oct_row, nov_row = data["monthly"]
    assert oct_row["month"] == "2026-10"
    assert oct_row["entries"] == "210.00"
    assert oct_row["exits"] == "6930.00"
    assert oct_row["balance"] == "-6720.00"
    # novembro: sem vendas -> entrada None; saida 900 (aluguel pago em nov);
    # saldo nao e apresentado sem entradas apuraveis
    assert nov_row["entries"] is None
    assert nov_row["exits"] == "900.00"
    assert nov_row["balance"] is None
    assert oct_row["balance_state"] == "partial"
    assert nov_row["balance_state"] == "unavailable"


def test_periodo_sem_vendas_nao_vira_zero(env):
    c, *_ = env
    seed_all(c)
    data = c.get("/api/v1/cashflow/preview?"
                 "date_from=2026-12-01&date_to=2026-12-31").json()
    assert data["summary"]["entries"]["JOINVILLE"] is None
    assert data["summary"]["balance"]["JOINVILLE"] is None
    codes = {w["code"] for w in data["warnings"]}
    assert "periodo_sem_vendas" in codes


def test_devolucoes_informativas_sem_abater(env):
    c, *_ = env
    seed_all(c)
    assert upload_devolucoes(c).status_code == 200
    data = c.get(f"/api/v1/cashflow/preview?{OUT}").json()
    assert data["returns"]["state"] == "current"
    assert data["returns"]["columns"]["TUBARAO"] == "55.00"
    assert data["returns"]["count"] == 1
    # entradas e saldo inalterados pela devolucao
    assert data["summary"]["entries"]["UMA"] == "210.00"
    assert data["summary"]["balance"]["UMA"] == "-6720.00"


def test_saldo_parcial_quando_vendas_nao_cobrem_mes(env):
    """Vendas so ate 17/10 -> o periodo de outubro e parcial; a diferenca
    continua visivel, mas nunca marcada como saldo de mes completo."""
    c, *_ = env
    seed_all(c)
    data = c.get(f"/api/v1/cashflow/preview?{OUT}").json()
    st = data["summary"]["balance_state"]
    assert st["JOINVILLE"] == "partial"
    assert st["TUBARAO"] == "partial"
    assert st["ITAJAI"] == "unavailable"        # sem vendas
    assert st["COMPARTILHADO"] == "payments_only"  # sem receitas proprias
    assert st["UMA"] == "partial"               # consolidado nunca "completo"
    # numeros permanecem consultaveis
    assert data["summary"]["balance"]["UMA"] == "-6720.00"


def test_trimestre_com_mes_ausente_nao_e_saldo_completo(env):
    c, *_ = env
    seed_all(c)
    data = c.get("/api/v1/cashflow/preview?"
                 "date_from=2026-10-01&date_to=2026-12-31").json()
    assert data["summary"]["balance_state"]["UMA"] == "partial"
    states = {m["month"]: m["balance_state"] for m in data["monthly"]}
    assert states["2026-10"] == "partial"
    assert states["2026-11"] == "unavailable"
    assert states["2026-12"] == "unavailable"
    nov = next(m for m in data["monthly"] if m["month"] == "2026-11")
    assert nov["balance"] is None               # nunca inventa saldo do mes


def test_consolidado_com_loja_sem_dados(env):
    """Itajai sem cobertura de vendas: o consolidado mostra a soma das
    demais, mas identificada como parcial — nunca 'UMA completo'."""
    c, *_ = env
    seed_all(c)
    data = c.get(f"/api/v1/cashflow/preview?{OUT}").json()
    st = data["summary"]["balance_state"]
    assert data["summary"]["entries"]["ITAJAI"] is None
    assert st["ITAJAI"] == "unavailable"
    assert data["summary"]["balance"]["ITAJAI"] is None
    assert st["UMA"] == "partial"
    # loja unica tambem e identificada
    single = c.get(f"/api/v1/cashflow/preview?{OUT}&store=ITAJAI").json()
    assert single["summary"]["balance_state"]["ITAJAI"] == "unavailable"
    assert single["summary"]["balance"]["ITAJAI"] is None


VENDAS_FULL = HEADER_VENDAS + "\n".join([
    # as 3 lojas com vendas ate o ultimo dia do periodo -> cobertura integral
    "05/10/2026;1;Joinville;7;MARIA;000;CONSUMIDOR;P1;MANGA;KG;1;100;100;30",
    "31/10/2026;1;Joinville;7;MARIA;000;CONSUMIDOR;P1;MANGA;KG;1;50;50;30",
    "05/10/2026;2;Tubarao;4;JOAO;000;CONSUMIDOR;P2;MANGA;PC;1;30;30;7",
    "31/10/2026;2;Tubarao;4;JOAO;000;CONSUMIDOR;P2;MANGA;PC;1;20;20;7",
    "05/10/2026;3;Itajai;2;ANA;000;CONSUMIDOR;P3;MANGA;PC;1;40;40;5",
    "31/10/2026;3;Itajai;2;ANA;000;CONSUMIDOR;P3;MANGA;PC;1;10;10;5",
]) + "\n"


def test_consolidado_completo_com_pagamentos_compartilhados(env):
    """Tres lojas com cobertura integral de vendas + DAS compartilhado:
    a coluna compartilhada nao degrada o consolidado — UMA reflete a
    disponibilidade das lojas e dos arquivos, nao a falta de receita
    propria da coluna compartilhada."""
    c, *_ = env
    assert upload_vendas(c, VENDAS_FULL).status_code == 200
    assert upload_despesas(c).status_code == 200
    data = c.get(f"/api/v1/cashflow/preview?{OUT}").json()
    st = data["summary"]["balance_state"]
    assert st["JOINVILLE"] == "complete"
    assert st["TUBARAO"] == "complete"
    assert st["ITAJAI"] == "complete"
    assert st["COMPARTILHADO"] == "payments_only"
    assert st["UMA"] == "complete"
    # pagamentos compartilhados seguem integralmente no consolidado, sem rateio
    assert data["summary"]["exits"]["COMPARTILHADO"] == "500.00"
    assert data["summary"]["entries"]["UMA"] == "250.00"
    assert data["summary"]["exits"]["UMA"] == "6930.00"
    assert data["summary"]["balance"]["UMA"] == "-6680.00"


def test_cobertura_pagamentos_indicativa_nao_confirmacao(env):
    """A janela do Despesas.csv e por vencimentos: nao confirma que todos
    os paid_at do periodo estejam cobertos — qualidade sempre indicativa."""
    c, *_ = env
    seed_all(c)
    data = c.get(f"/api/v1/cashflow/preview?{OUT}").json()
    assert data["payments_coverage"] == "indicative"
    assert any("vencimentos" in m and "confirma" in m
               for m in data["methodology"])


def test_intervalo_personalizado_recorta_datas(env):
    c, *_ = env
    seed_all(c)
    # apenas primeira quinzena: vendas 15-17/10; pagamentos ate 15/10
    data = c.get("/api/v1/cashflow/preview?"
                 "date_from=2026-10-15&date_to=2026-10-15").json()
    entries = data["summary"]["entries"]
    assert entries["JOINVILLE"] == "100.00"      # so a venda de 15/10
    exits = data["summary"]["exits"]
    assert exits["JOINVILLE"] is None or exits["JOINVILLE"] in (None, "0.00")
    # pagamento de 10/10 (compra 5000) ficou fora do dia 15
    payments = {p["bucket"]: p for p in data["payments"]}
    assert payments["compra_revenda"]["amount"] == "0.00"


def test_loja_unica_sem_compartilhado(env):
    c, *_ = env
    seed_all(c)
    data = c.get(f"/api/v1/cashflow/preview?{OUT}&store=JOINVILLE").json()
    assert data["columns"] == ["JOINVILLE"]
    assert data["summary"]["exits"]["JOINVILLE"] == "5430.00"
    assert data["shared_memo"]["amount"] == "500.00"  # DAS fora do recorte
    assert data["summary"]["balance"]["JOINVILLE"] == "-5250.00"


def test_detalhamento_pagamentos_por_grupo(env):
    c, *_ = env
    seed_all(c)
    res = c.get("/api/v1/cashflow/lines?bucket=compra_revenda&" + OUT)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total"] == 1                    # so a compra PAGA (aberta nao entra)
    assert data["sum_amount"] == "5000.00"
    item = data["items"][0]
    assert item["status"] == "pago"
    assert item["paid_at"] == "2026-10-10"
    oper = c.get("/api/v1/cashflow/lines?bucket=despesa_operacional&" + OUT).json()
    assert oper["total"] == 4                    # FGTS + aluguel + 2x limpeza


# ---------- autorizacao ----------

def test_cashflow_negado_sem_concessao(env):
    c, actor, _, _, admin, seller, _ = env
    actor["user"] = admin
    assert c.get(f"/api/v1/cashflow/preview?{OUT}").status_code == 403
    assert c.get("/api/v1/cashflow/lines?bucket=a_classificar&" + OUT).status_code == 403
    actor["user"] = seller
    assert c.get(f"/api/v1/cashflow/preview?{OUT}").status_code == 403


def test_cashflow_concessao_limitada_a_loja(env):
    c, actor, engine, _, _, seller, group_id = env
    seed_all(c)
    with Session(engine) as db:
        db.add(GroupPermission(group_id=group_id, code="cashflow.view", granted=True))
        db.commit()
    actor["user"] = seller
    res = c.get(f"/api/v1/cashflow/preview?{OUT}")
    assert res.status_code == 200
    data = res.json()
    assert data["columns"] == ["JOINVILLE"]
    assert data["consolidated"] is False
    assert c.get(f"/api/v1/cashflow/preview?{OUT}&store=TUBARAO").status_code == 403


def test_cashflow_concessao_por_excecao_individual(env):
    c, actor, engine, _, admin, _, _ = env
    with Session(engine) as db:
        db.add(UserPermissionOverride(
            user_id=admin.id, code="cashflow.view", granted=True))
        db.commit()
    actor["user"] = admin
    assert c.get(f"/api/v1/cashflow/preview?{OUT}").status_code == 200


def test_me_expoe_feature_cashflow(env):
    c, actor, _, _, admin, _, _ = env
    assert c.get("/api/v1/me").json()["features"]["cashflow"] is True
    actor["user"] = admin
    assert c.get("/api/v1/me").json()["features"]["cashflow"] is False


def test_parametros_invalidos(env):
    c, *_ = env
    assert c.get("/api/v1/cashflow/preview").status_code == 422
    assert c.get("/api/v1/cashflow/preview?"
                 "date_from=2026-10-31&date_to=2026-10-01").status_code == 422
    assert c.get("/api/v1/cashflow/preview?"
                 "date_from=xx&date_to=2026-10-01").status_code == 422
