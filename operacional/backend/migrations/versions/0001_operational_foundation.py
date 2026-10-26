"""Initial UMA stores, identities, permissions and audit tables.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.bulk_insert(
        sa.table("stores", sa.column("code", sa.String), sa.column("name", sa.String)),
        [{"code": "JOINVILLE", "name": "Joinville"},
         {"code": "ITAJAI", "name": "Itajai"},
         {"code": "TUBARAO", "name": "Tubarao"}],
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("auth_subject", sa.String(250), unique=True, nullable=False),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("profile", sa.String(30), nullable=False),
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("profile IN ('administrator', 'seller')", name="ck_users_profile"),
    )
    op.create_table(
        "store_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "group_memberships",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("store_groups.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "group_permissions",
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("store_groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("code", sa.String(100), primary_key=True),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "user_permission_overrides",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("code", sa.String(100), primary_key=True),
        sa.Column("granted", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_subject", sa.String(250), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(150)),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("user_permission_overrides")
    op.drop_table("group_permissions")
    op.drop_table("group_memberships")
    op.drop_table("store_groups")
    op.drop_table("users")
    op.drop_table("stores")
