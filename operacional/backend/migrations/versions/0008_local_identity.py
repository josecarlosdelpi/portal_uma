"""Login com usuario e senha provisoria individual, sessoes revogaveis e exclusao logica.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "local_credentials",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("username_key", sa.String(70), nullable=False),
        sa.Column("password_hash", sa.String(350), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("temporary_expires_at", sa.DateTime(timezone=True)),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("username_key", name="uq_local_credentials_username"),
        sa.CheckConstraint("failed_attempts >= 0", name="ck_local_failed_attempts"),
    )
    op.create_table(
        "local_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("limited", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("token_hash", name="uq_local_session_hash"),
    )
    op.create_index("ix_local_sessions_user_id", "local_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_local_sessions_user_id", table_name="local_sessions")
    op.drop_table("local_sessions")
    op.drop_table("local_credentials")
    op.drop_column("users", "deleted_at")
