"""Gestao de Despesas: categorias, regras por fornecedor e classificacoes

Revision ID: 0027
Revises: 0025
Create Date: 2026-11-19

Estrutura persistente e independente dos snapshots do ERP:
- expense_categories: dimensao gerencial compartilhada entre as lojas;
- supplier_category_rules: regra automatica por fornecedor (doc ou nome
  normalizado), com abrangencia por loja ou UMA;
- expense_line_classifications: classificacao manual por 'fingerprint'
  dos campos identitarios do lancamento — nunca pelo id interno, que
  muda a cada importacao.

ATENCAO: esta revisao e irma da 0026 (televendas), ambas descendentes de
0025 — ao integrar as duas linhas de desenvolvimento, criar a migration
de merge Alembic correspondente.
"""
from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expense_categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("name_norm", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name_norm", name="uq_expense_category_norm"),
    )

    op.create_table(
        "supplier_category_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("supplier_key", sa.String(220), nullable=False),
        sa.Column("supplier_label", sa.String(220), nullable=False),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT")),
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_supplier_rule_key", "supplier_category_rules", ["supplier_key"])

    op.create_table(
        "expense_line_classifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_key", sa.String(220), nullable=False),
        sa.Column("supplier_label", sa.String(220), nullable=False),
        sa.Column("document_number", sa.String(30)),
        sa.Column("installment_number", sa.String(10)),
        sa.Column("issued_at", sa.Date()),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("matched_rows", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active','orphan')",
                           name="ck_expense_line_class_status"),
    )


def downgrade() -> None:
    op.drop_table("expense_line_classifications")
    op.drop_index("ix_supplier_rule_key", table_name="supplier_category_rules")
    op.drop_table("supplier_category_rules")
    op.drop_table("expense_categories")
