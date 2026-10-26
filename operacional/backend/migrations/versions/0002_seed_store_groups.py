"""Seed the three UMA store groups; no personal information is seeded.

Revision ID: 0002
Revises: 0001
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    groups = sa.table(
        "store_groups",
        sa.column("id", sa.Uuid()),
        sa.column("store_code", sa.String()),
        sa.column("name", sa.String()),
    )
    op.bulk_insert(groups, [
        {"id": uuid4(), "store_code": "JOINVILLE", "name": "Joinville"},
        {"id": uuid4(), "store_code": "ITAJAI", "name": "Itajaí"},
        {"id": uuid4(), "store_code": "TUBARAO", "name": "Tubarão"},
    ])


def downgrade() -> None:
    op.execute("DELETE FROM store_groups WHERE store_code IN ('JOINVILLE', 'ITAJAI', 'TUBARAO')")
