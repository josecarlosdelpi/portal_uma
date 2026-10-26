"""Versioned drafts and immutable monthly closing snapshots.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_closing_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("year", "month", name="uq_closing_draft_period"),
        sa.CheckConstraint("year BETWEEN 2020 AND 2100", name="ck_closing_draft_year"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_closing_draft_month"),
        sa.CheckConstraint("revision >= 1", name="ck_closing_draft_revision"),
    )
    op.create_table(
        "monthly_closing_archives",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("archived_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("year", "month", "version", name="uq_closing_archive_period_version"),
        sa.CheckConstraint("year BETWEEN 2020 AND 2100", name="ck_closing_archive_year"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_closing_archive_month"),
        sa.CheckConstraint("version >= 1", name="ck_closing_archive_version"),
    )


def downgrade() -> None:
    op.drop_table("monthly_closing_archives")
    op.drop_table("monthly_closing_drafts")
