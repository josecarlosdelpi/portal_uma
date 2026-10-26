"""Google review tracking, supply ledgers and independent client-contact logs.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_review_months",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("checked_on", sa.DateTime(), nullable=False),
        sa.Column("delivered_on", sa.DateTime()),
        sa.Column("note", sa.String(200), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("store_code", "year", "month", name="uq_google_reviews_store_month"),
        sa.CheckConstraint("year BETWEEN 2020 AND 2100 AND month BETWEEN 1 AND 12", name="ck_google_month"),
        sa.CheckConstraint("count BETWEEN 0 AND 9999", name="ck_google_count"),
        sa.CheckConstraint("revision >= 1", name="ck_google_revision"),
    )
    op.create_table(
        "supply_materials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("name_key", sa.String(100), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("name_key", name="uq_supply_material_name_key"),
    )
    op.create_table(
        "supply_stocks",
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), primary_key=True),
        sa.Column("material_id", sa.Uuid(), sa.ForeignKey("supply_materials.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minimum", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.CheckConstraint("balance >= 0", name="ck_supply_balance"),
        sa.CheckConstraint("minimum >= 0", name="ck_supply_minimum"),
        sa.CheckConstraint("revision >= 1", name="ck_supply_revision"),
    )
    op.create_table(
        "supply_movements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("material_id", sa.Uuid(), sa.ForeignKey("supply_materials.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("resulting_balance", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(180), nullable=False, server_default=""),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity BETWEEN 1 AND 9999", name="ck_supply_move_qty"),
        sa.CheckConstraint("kind IN ('entrada','retirada')", name="ck_supply_move_kind"),
    )
    op.create_index("ix_supply_movements_store_created", "supply_movements", ["store_code", "created_at"])
    op.create_table(
        "contact_clients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_key", sa.String(120), nullable=False),
        sa.Column("erp_code", sa.String(50)),
        sa.Column("phone", sa.String(40)),
        sa.Column("origin", sa.String(25), nullable=False),
        sa.Column("last_purchase_on", sa.DateTime()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("store_code", "name_key", name="uq_client_name_store"),
    )
    op.create_table(
        "contact_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("contact_clients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("seller_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contacted_on", sa.DateTime(), nullable=False),
        sa.Column("outcome", sa.String(25), nullable=False),
        sa.Column("next_on", sa.DateTime()),
        sa.Column("note", sa.String(240), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("outcome IN ('apresentacao','sem_resposta','whatsapp','outro')", name="ck_call_outcome"),
        sa.CheckConstraint("revision >= 1", name="ck_call_revision"),
    )
    op.create_index("ix_calls_store_date", "contact_attempts", ["store_code", "contacted_on"])


def downgrade() -> None:
    op.drop_index("ix_calls_store_date", table_name="contact_attempts")
    op.drop_table("contact_attempts")
    op.drop_table("contact_clients")
    op.drop_index("ix_supply_movements_store_created", table_name="supply_movements")
    op.drop_table("supply_movements")
    op.drop_table("supply_stocks")
    op.drop_table("supply_materials")
    op.drop_table("google_review_months")
