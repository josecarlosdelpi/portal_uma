"""Store monthly targets, business-day calendars and minimum daily targets.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_sales_targets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("days_off", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("store_code", "year", "month", name="uq_monthly_target_store_period"),
        sa.CheckConstraint("year BETWEEN 2020 AND 2100", name="ck_monthly_target_year"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_monthly_target_month"),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name="ck_monthly_target_amount"),
        sa.CheckConstraint("revision >= 1", name="ck_monthly_target_revision"),
    )
    op.create_table(
        "store_target_settings",
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), primary_key=True),
        sa.Column("minimum_daily", sa.Numeric(14, 2), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("minimum_daily >= 0", name="ck_store_target_minimum_nonnegative"),
        sa.CheckConstraint("revision >= 1", name="ck_store_settings_revision"),
    )


def downgrade() -> None:
    op.drop_table("store_target_settings")
    op.drop_table("monthly_sales_targets")
