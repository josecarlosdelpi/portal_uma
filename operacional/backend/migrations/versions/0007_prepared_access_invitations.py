"""SuperAdmin prepared invitations, no passwords, no email transmission.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("email_key", sa.String(254), nullable=False),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("profile", sa.String(30), nullable=False),
        sa.Column("store_code", sa.String(20),
                  sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="prepared"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("prepared_by", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("email_key", name="uq_access_invitations_email_key"),
        sa.CheckConstraint("profile IN ('administrator','seller')",
                           name="ck_invite_profile"),
        sa.CheckConstraint(
            "status IN ('prepared','sent','activated','cancelled','expired')",
            name="ck_invite_status",
        ),
        sa.CheckConstraint(
            "(profile='administrator' AND store_code IS NULL) OR "
            "(profile='seller' AND store_code IS NOT NULL)",
            name="ck_invite_store_by_profile",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_invite_revision"),
    )
    op.create_index("ix_access_invitations_status", "access_invitations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_access_invitations_status", table_name="access_invitations")
    op.drop_table("access_invitations")
