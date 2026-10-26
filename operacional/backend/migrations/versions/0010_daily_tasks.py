"""Tarefas diarias por loja, com responsavel, status, revisao e auditoria.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("due_on", sa.DateTime(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("details", sa.String(400), nullable=False, server_default=""),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(15), nullable=False, server_default="pendente"),
        sa.Column("assignee_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pendente','em_andamento','concluida')", name="ck_daily_task_status"),
        sa.CheckConstraint("priority IN ('baixa','normal','alta')", name="ck_daily_task_priority"),
        sa.CheckConstraint("revision >= 1", name="ck_daily_task_revision"),
    )
    op.create_index("ix_daily_tasks_store_date", "daily_tasks", ["store_code", "due_on"])


def downgrade() -> None:
    op.drop_index("ix_daily_tasks_store_date", table_name="daily_tasks")
    op.drop_table("daily_tasks")
