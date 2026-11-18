"""Regras de classificacao da DRE gerencial preliminar

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-17

Tabela somente-leitura nesta etapa (edicao reservada a 'dre.classify').
O seed replica o mapeamento inicial aprovado em 17/11/2026
(dre_classification.DEFAULT_RULES): barreira de compra p/ revenda e
precedencia excecao-por-fornecedor > codigo de conta > A CLASSIFICAR sao
avaliadas em codigo; a tabela guarda o mapeamento versionado.
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

COMERCIAL = "despesa_comercial"
OPERACIONAL = "despesa_operacional"
DAS = "das_identificado"
REVENDA = "compra_revenda"
FINANC = "financiamento"
IMOB = "imobilizado"
PEND = "a_classificar"

# (account_code, supplier_pattern, bucket, allocation, note)
SEED = [
    ("67", "guia simples nacional das", DAS, "shared",
     "Conta 67: DAS por vencimento, consolidado — referencia tributaria provisoria"),
    ("67", "fundo de garantia", OPERACIONAL, "erp_store",
     "Conta 67: FGTS como despesa de pessoal preliminar"),
    ("80", None, REVENDA, "erp_store",
     "Compra para revenda — fora das despesas da DRE (nao duplica CMV)"),
    ("15", None, FINANC, "erp_store",
     "Financiamento — fora do calculo ate segregar juros e principal"),
    ("26", None, FINANC, "erp_store",
     "Financiamento — fora do calculo ate segregar juros e principal"),
    ("97", None, FINANC, "erp_store",
     "Amortizacao — fora do calculo ate segregar juros e principal"),
    ("21", None, IMOB, "erp_store",
     "Aquisicao de imobilizado — quadro de investimentos, sem depreciacao"),
    ("22", None, IMOB, "erp_store",
     "Aquisicao de imobilizado — quadro de investimentos, sem depreciacao"),
    ("50", None, COMERCIAL, "erp_store", "Fretes sobre vendas — despesa comercial preliminar"),
    ("44", None, COMERCIAL, "erp_store", "Marketing — despesa comercial preliminar"),
    ("129", None, COMERCIAL, "erp_store", "Brindes — despesa comercial preliminar"),
    ("60", None, OPERACIONAL, "erp_store",
     "Pessoal — preliminar; folha/provisoes nao reconciliadas"),
    ("70", None, OPERACIONAL, "erp_store",
     "Pessoal — preliminar; folha/provisoes nao reconciliadas"),
    ("65", None, OPERACIONAL, "erp_store", "Pessoal/beneficios — preliminar"),
    ("27", None, OPERACIONAL, "erp_store", "Aluguel — operacional preliminar pela loja do ERP"),
    ("25", None, OPERACIONAL, "erp_store", "Agua — operacional preliminar pela loja do ERP"),
    ("29", None, OPERACIONAL, "erp_store", "Energia — operacional preliminar pela loja do ERP"),
    ("30", None, OPERACIONAL, "erp_store", "Internet — operacional preliminar pela loja do ERP"),
    ("31", None, OPERACIONAL, "erp_store", "IPTU — operacional preliminar pela loja do ERP"),
    ("43", None, OPERACIONAL, "erp_store", "Telefones — operacional preliminar pela loja do ERP"),
    ("75", None, OPERACIONAL, "erp_store",
     "Contabilidade — operacional preliminar; revisar uso compartilhado"),
    ("76", None, OPERACIONAL, "erp_store",
     "Manutencao — operacional preliminar; revisar uso compartilhado"),
    ("77", None, OPERACIONAL, "erp_store",
     "Manutencao — operacional preliminar; revisar uso compartilhado"),
    ("78", None, OPERACIONAL, "erp_store",
     "Seguranca — operacional preliminar; revisar uso compartilhado"),
    ("126", None, OPERACIONAL, "erp_store",
     "Advocacia — operacional preliminar; revisar uso compartilhado"),
    ("73", None, OPERACIONAL, "erp_store",
     "Terceiros — operacional preliminar; revisar uso compartilhado"),
    ("130", None, OPERACIONAL, "erp_store",
     "Viagens — operacional preliminar; revisar uso compartilhado"),
    ("36", None, OPERACIONAL, "erp_store", "Copa — operacional preliminar"),
    ("37", None, OPERACIONAL, "erp_store", "Expediente — operacional preliminar"),
    ("38", None, OPERACIONAL, "erp_store", "Limpeza — operacional preliminar"),
    ("33", None, OPERACIONAL, "erp_store", "Refeicoes — operacional preliminar"),
    ("63", None, OPERACIONAL, "erp_store", "Confraternizacoes — operacional preliminar"),
    ("40", None, OPERACIONAL, "erp_store", "Seguros — operacional preliminar"),
    ("41", None, OPERACIONAL, "erp_store", "Seguros — operacional preliminar"),
    ("72", None, OPERACIONAL, "erp_store", "Seguros — operacional preliminar"),
    ("67", None, PEND, "pending_review",
     "Conta 67 mista (GPS/INSS/IRRF/repasses) — pendente de revisao"),
    ("94", None, PEND, "pending_review", "Tributos/taxas — pendente de revisao"),
    ("86", None, PEND, "pending_review", "Tributos/taxas — pendente de revisao"),
    ("0", None, PEND, "pending_review", "Sem conta confiavel — pendente de revisao"),
]


def upgrade() -> None:
    op.create_table(
        "dre_classification_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_code", sa.String(20), nullable=True),
        sa.Column("supplier_pattern", sa.String(200), nullable=True),
        sa.Column("bucket", sa.String(30), nullable=False),
        sa.Column("allocation", sa.String(20), nullable=False,
                  server_default="erp_store"),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "bucket IN ('despesa_comercial','despesa_operacional',"
            "'das_identificado','compra_revenda','financiamento',"
            "'imobilizado','a_classificar')",
            name="ck_dre_rule_bucket"),
        sa.CheckConstraint(
            "allocation IN ('erp_store','shared','pending_review')",
            name="ck_dre_rule_allocation"),
        sa.CheckConstraint(
            "account_code IS NOT NULL OR supplier_pattern IS NOT NULL",
            name="ck_dre_rule_matcher"),
    )
    rules = sa.table(
        "dre_classification_rules",
        sa.column("id", sa.Uuid), sa.column("account_code", sa.String),
        sa.column("supplier_pattern", sa.String), sa.column("bucket", sa.String),
        sa.column("allocation", sa.String), sa.column("note", sa.String),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(rules, [
        {"id": uuid4(), "account_code": code,
         "supplier_pattern": pattern, "bucket": bucket,
         "allocation": allocation, "note": note, "active": True}
        for code, pattern, bucket, allocation, note in SEED
    ])


def downgrade() -> None:
    op.drop_table("dre_classification_rules")
