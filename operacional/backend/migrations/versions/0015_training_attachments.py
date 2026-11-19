"""Anexos de treinamento aceitam mais tipos de mídia (10 MB).

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("training_documents", "media_type",
                    existing_type=sa.String(30), type_=sa.String(120),
                    existing_nullable=False)


def downgrade() -> None:
    op.alter_column("training_documents", "media_type",
                    existing_type=sa.String(120), type_=sa.String(30),
                    existing_nullable=False)
