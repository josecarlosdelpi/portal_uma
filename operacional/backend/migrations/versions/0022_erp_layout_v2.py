"""Novas colunas do layout v2 do ERP (11/2026).

Revision ID: 0022
Revises: 0021

O Vitor ampliou as tres exportacoes do ERP:
- Vendas.csv: 10 -> 14 colunas (id/nome do vendedor, id/descricao/unidade
  do produto, custo unitario);
- Devolucoes.csv: 10 -> 11 colunas (id/descricao/unidade do produto; sem
  vendedor);
- Despesas.csv: 9 -> 17 colunas (nr_documento, nr_parcela, dt_emissao,
  valor_original, acrescimos, descontos, valor_liquido, plano de contas).

Todas as colunas novas sao nullable: lotes anteriores ao layout v2
permanecem integros para auditoria. Em financial_obligations, 'amount'
continua sendo o valor liquido; valor_original/acrescimos/descontos
ficam preservados para conferencia e conciliacao.
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_NEW_ROW_COLUMNS = (
    ("seller_name", sa.String(150)),
    ("product_description", sa.String(200)),
    ("product_unit", sa.String(10)),
    ("unit_cost", sa.Numeric(14, 2)),
)
_NEW_OBLIGATION_COLUMNS = (
    ("document_number", sa.String(30)),
    ("installment_number", sa.String(10)),
    ("issued_at", sa.Date()),
    ("original_amount", sa.Numeric(14, 2)),
    ("additions", sa.Numeric(14, 2)),
    ("discounts", sa.Numeric(14, 2)),
    ("account_code", sa.String(20)),
    ("account_description", sa.String(150)),
)


def upgrade() -> None:
    for table in ("erp_sale_rows", "erp_return_rows"):
        for name, type_ in _NEW_ROW_COLUMNS:
            op.add_column(table, sa.Column(name, type_, nullable=True))
    for name, type_ in _NEW_OBLIGATION_COLUMNS:
        op.add_column("financial_obligations", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _type in _NEW_OBLIGATION_COLUMNS:
        op.drop_column("financial_obligations", name)
    for table in ("erp_return_rows", "erp_sale_rows"):
        for name, _type in _NEW_ROW_COLUMNS:
            op.drop_column(table, name)
