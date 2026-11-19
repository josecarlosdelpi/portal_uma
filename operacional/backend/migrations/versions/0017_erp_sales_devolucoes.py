"""Integracao ERP comercial: lotes de importacao, linhas de vendas e devolucoes,
estado compartilhado da aquisicao remota (Google Drive).

Frente A — Vendas e Devolucoes. Reserva: 0017 (frente B usa 0018+).

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_import_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("source", sa.String(15), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("file_name", sa.String(150), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("drive_file_id", sa.String(120), nullable=True),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("rows_applied", sa.Integer(), nullable=False),
        sa.Column("rows_rejected", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("coverage", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.JSON(), nullable=True),
        sa.Column("imported_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('VENDAS','DEVOLUCOES')", name="ck_erp_batch_kind"),
        sa.CheckConstraint("source IN ('MANUAL_UPLOAD','DRIVE_SYNC')", name="ck_erp_batch_source"),
        sa.CheckConstraint("status IN ('RECEIVED','APPLIED','DUPLICATE','FAILED')", name="ck_erp_batch_status"),
        sa.ForeignKeyConstraint(["imported_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_erp_import_batches_kind", "erp_import_batches", ["kind"])

    op.create_table(
        "erp_sale_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("store_code", sa.String(20), nullable=False),
        sa.Column("seller_code", sa.String(30), nullable=False),
        sa.Column("customer_cnpj", sa.String(20), nullable=False),
        sa.Column("customer_name", sa.String(150), nullable=False),
        sa.Column("product_code", sa.String(60), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["erp_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_code"], ["stores.code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_erp_sale_rows_batch_id", "erp_sale_rows", ["batch_id"])
    op.create_index("ix_erp_sale_rows_date", "erp_sale_rows", ["sale_date"])
    op.create_index("ix_erp_sale_rows_store_date", "erp_sale_rows", ["store_code", "sale_date"])

    op.create_table(
        "erp_return_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("store_code", sa.String(20), nullable=False),
        sa.Column("seller_code", sa.String(30), nullable=False),
        sa.Column("customer_cnpj", sa.String(20), nullable=False),
        sa.Column("customer_name", sa.String(150), nullable=False),
        sa.Column("product_code", sa.String(60), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["erp_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_code"], ["stores.code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_erp_return_rows_batch_id", "erp_return_rows", ["batch_id"])
    op.create_index("ix_erp_return_rows_date", "erp_return_rows", ["sale_date"])
    op.create_index("ix_erp_return_rows_store_date", "erp_return_rows", ["store_code", "sale_date"])

    op.create_table(
        "erp_source_files",
        sa.Column("file_key", sa.String(40), nullable=False),
        sa.Column("drive_file_id", sa.String(120), nullable=True),
        sa.Column("drive_file_name", sa.String(150), nullable=True),
        sa.Column("drive_md5", sa.String(64), nullable=True),
        sa.Column("remote_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(12), nullable=False),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "last_status IN ('PENDING','OK','SKIPPED','FAILED','DISABLED')",
            name="ck_erp_source_status",
        ),
        sa.PrimaryKeyConstraint("file_key"),
    )


def downgrade() -> None:
    op.drop_table("erp_source_files")
    op.drop_index("ix_erp_return_rows_store_date", table_name="erp_return_rows")
    op.drop_index("ix_erp_return_rows_date", table_name="erp_return_rows")
    op.drop_index("ix_erp_return_rows_batch_id", table_name="erp_return_rows")
    op.drop_table("erp_return_rows")
    op.drop_index("ix_erp_sale_rows_store_date", table_name="erp_sale_rows")
    op.drop_index("ix_erp_sale_rows_date", table_name="erp_sale_rows")
    op.drop_index("ix_erp_sale_rows_batch_id", table_name="erp_sale_rows")
    op.drop_table("erp_sale_rows")
    op.drop_index("ix_erp_import_batches_kind", table_name="erp_import_batches")
    op.drop_table("erp_import_batches")
