"""Anexos de treinamento: limite de tamanho sobe para 10 MB.

Revision ID: 0016
Revises: 0015
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_training_pdf_size", "training_documents", type_="check")
    op.create_check_constraint(
        "ck_training_pdf_size", "training_documents",
        "byte_length BETWEEN 1 AND 10485760",
    )


def downgrade() -> None:
    op.drop_constraint("ck_training_pdf_size", "training_documents", type_="check")
    op.create_check_constraint(
        "ck_training_pdf_size", "training_documents",
        "byte_length BETWEEN 1 AND 5242880",
    )
