"""Etapa do treinamento aceita múltiplos valores (apresentado + prática).

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

OLD = "step IN ('participou','pratica')"
NEW = "step IN ('participou','pratica','participou,pratica')"


def upgrade() -> None:
    op.drop_constraint("ck_training_step", "training_records", type_="check")
    op.alter_column("training_records", "step",
                    existing_type=sa.String(15), type_=sa.String(31),
                    existing_nullable=False)
    op.create_check_constraint("ck_training_step", "training_records", NEW)


def downgrade() -> None:
    op.drop_constraint("ck_training_step", "training_records", type_="check")
    op.alter_column("training_records", "step",
                    existing_type=sa.String(31), type_=sa.String(15),
                    existing_nullable=False)
    op.create_check_constraint("ck_training_step", "training_records", OLD)
