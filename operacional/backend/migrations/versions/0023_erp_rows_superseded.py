"""Substituicao recuperavel das linhas ERP (soft-delete por cobertura).

Revision ID: 0023
Revises: 0022

O replace-window passa a marcar linhas substituidas com superseded_at em
vez de deleta-las: o historico completo de cada exportacao fica
recuperavel (basta limpar a marca) e qualquer substituicao pode ser
auditada. Consultas e indicadores leem apenas superseded_at IS NULL.
Linhas existentes permanecem NULL (ativas).
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("erp_sale_rows", "erp_return_rows"):
        op.add_column(table, sa.Column("superseded_at", sa.DateTime(timezone=True)))
        op.create_index(
            f"ix_{table}_active_window", table,
            ["store_code", "sale_date"],
            postgresql_where=sa.text("superseded_at IS NULL"),
        )


def downgrade() -> None:
    for table in ("erp_return_rows", "erp_sale_rows"):
        op.drop_index(f"ix_{table}_active_window", table_name=table)
        op.drop_column(table, "superseded_at")
