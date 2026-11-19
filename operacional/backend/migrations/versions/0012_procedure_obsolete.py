"""Obsolescencia de procedimentos publicados.

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("procedures", sa.Column("obsolete_at", sa.DateTime(timezone=True)))
    op.add_column("procedures", sa.Column("obsolete_by", sa.Uuid(),
        sa.ForeignKey("users.id", ondelete="RESTRICT")))


def downgrade() -> None:
    op.drop_column("procedures", "obsolete_by")
    op.drop_column("procedures", "obsolete_at")
