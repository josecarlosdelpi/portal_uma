"""Preferencias visuais do proprio usuario (ex.: cores das lojas nos graficos).

Campo JSON generico em user_preferences para preferencias de interface que
devem seguir o usuario entre dispositivos. Frente A — Vendas e Devolucoes.

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("ui_prefs", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "ui_prefs")
