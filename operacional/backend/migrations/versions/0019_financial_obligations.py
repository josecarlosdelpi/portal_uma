"""Obrigacoes financeiras do ERP (despezas e pagamentos) sobre o contrato
compartilhado erp_import_batches da frente comercial.

Revision ID: 0019
Revises: 0018

Unificacao das frentes: a tabela erp_import_batches ja existe desde 0017
(contrato unico); esta revisao apenas amplia o CHECK de kind para aceitar
'DESPESAS' e cria a tabela de dominio financeiro. Uma linha por linha do
arquivo do ERP: sem IDs transacionais, a cardinalidade e preservada e
registros identicos sao legitimos. Consultas leem o snapshot corrente
(ultimo lote APPLIED de kind='DESPESAS'); linhas de lotes antigos ficam
preservadas via batch_id para auditoria.
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_erp_batch_kind", "erp_import_batches", type_="check")
    op.create_check_constraint(
        "ck_erp_batch_kind", "erp_import_batches",
        "kind IN ('VENDAS','DEVOLUCOES','DESPESAS')",
    )
    op.create_table(
        "financial_obligations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("batch_id", sa.Uuid(),
                  sa.ForeignKey("erp_import_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("supplier_doc", sa.String(20), nullable=True),
        sa.Column("supplier_name", sa.String(200), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("paid_at", sa.Date(), nullable=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("store_code", sa.String(20),
                  sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount >= 0", name="ck_obligation_amount"),
        sa.CheckConstraint("category IN ('despesa','compra_revenda')", name="ck_obligation_category"),
        sa.CheckConstraint("status IN ('aberto','pago')", name="ck_obligation_status"),
        sa.CheckConstraint("(status = 'pago') = (paid_at IS NOT NULL)",
                           name="ck_obligation_status_paid"),
    )
    op.create_index("ix_financial_obligations_batch", "financial_obligations", ["batch_id"])
    op.create_index("ix_financial_obligations_due", "financial_obligations",
                    ["store_code", "due_date"])
    op.create_index("ix_financial_obligations_paid", "financial_obligations",
                    ["store_code", "paid_at"])


def downgrade() -> None:
    op.drop_index("ix_financial_obligations_paid", table_name="financial_obligations")
    op.drop_index("ix_financial_obligations_due", table_name="financial_obligations")
    op.drop_index("ix_financial_obligations_batch", table_name="financial_obligations")
    op.drop_table("financial_obligations")
    op.drop_constraint("ck_erp_batch_kind", "erp_import_batches", type_="check")
    op.create_check_constraint(
        "ck_erp_batch_kind", "erp_import_batches",
        "kind IN ('VENDAS','DEVOLUCOES')",
    )
