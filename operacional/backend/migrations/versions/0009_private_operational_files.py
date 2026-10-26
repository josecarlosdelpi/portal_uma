"""Private small images and PDFs for WhatsApp calendar and training.

Revision ID: 0009
Revises: 0008

No public file paths. Files are kept in private PostgreSQL columns.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_files",
        sa.Column("post_date", sa.DateTime(),
                  sa.ForeignKey("whatsapp_posts.post_date", ondelete="RESTRICT"),
                  primary_key=True),
        sa.Column("kind", sa.String(10), primary_key=True),
        sa.Column("original_name", sa.String(120), nullable=False),
        sa.Column("media_type", sa.String(30), nullable=False),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uploaded_by", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('art','evidence')", name="ck_whatsapp_file_kind"),
        sa.CheckConstraint("byte_length BETWEEN 1 AND 3145728", name="ck_whatsapp_file_size"),
        sa.CheckConstraint("revision >= 1", name="ck_whatsapp_file_revision"),
    )
    op.create_table(
        "training_documents",
        sa.Column("training_id", sa.Uuid(),
                  sa.ForeignKey("training_records.id", ondelete="RESTRICT"),
                  primary_key=True),
        sa.Column("original_name", sa.String(120), nullable=False),
        sa.Column("media_type", sa.String(30), nullable=False,
                  server_default="application/pdf"),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uploaded_by", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("byte_length BETWEEN 1 AND 5242880", name="ck_training_pdf_size"),
        sa.CheckConstraint("revision >= 1", name="ck_training_pdf_revision"),
    )


def downgrade() -> None:
    op.drop_table("training_documents")
    op.drop_table("whatsapp_files")
