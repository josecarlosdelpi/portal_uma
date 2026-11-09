"""Procedimentos editaveis com versoes publicadas e imagens privadas.

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procedures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("title", sa.String(140), nullable=False),
        sa.Column("summary", sa.String(300), nullable=False, server_default=""),
        sa.Column("applies_to_all", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("code", name="uq_procedures_code"),
    )
    op.create_table(
        "procedure_stores",
        sa.Column("procedure_id", sa.Uuid(), sa.ForeignKey("procedures.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), primary_key=True),
    )
    op.create_table(
        "procedure_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("procedure_id", sa.Uuid(), sa.ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_label", sa.String(20), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="rascunho"),
        sa.Column("content_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("published_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("procedure_id", "version_label", name="uq_procedure_version_label"),
        sa.CheckConstraint("status IN ('rascunho','publicado')", name="ck_procedure_version_status"),
        sa.CheckConstraint("revision >= 1", name="ck_procedure_version_revision"),
    )
    op.create_table(
        "procedure_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("procedure_id", sa.Uuid(), sa.ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("original_name", sa.String(120), nullable=False),
        sa.Column("media_type", sa.String(30), nullable=False),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("byte_length BETWEEN 1 AND 3145728", name="ck_procedure_file_size"),
    )
    op.add_column("training_records", sa.Column("procedure_id", sa.Uuid(),
        sa.ForeignKey("procedures.id", ondelete="RESTRICT")))
    op.add_column("training_records", sa.Column("procedure_version_id", sa.Uuid(),
        sa.ForeignKey("procedure_versions.id", ondelete="RESTRICT")))
    op.add_column("training_records", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("training_records", sa.Column("updated_by", sa.Uuid(),
        sa.ForeignKey("users.id", ondelete="RESTRICT")))
    op.add_column("training_records", sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.add_column("training_records", sa.Column("deleted_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    for col in ("deleted_at", "updated_at", "updated_by", "revision",
                "procedure_version_id", "procedure_id"):
        op.drop_column("training_records", col)
    op.drop_table("procedure_files")
    op.drop_table("procedure_versions")
    op.drop_table("procedure_stores")
    op.drop_table("procedures")
