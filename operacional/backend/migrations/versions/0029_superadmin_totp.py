"""MFA opcional do SuperAdmin: segredo TOTP na credencial local.

Adiciona totp_secret (segredo RFC 6238, base32) e totp_enabled a
local_credentials. So o SuperAdmin pode ativar; a recuperacao de
acesso (recover_superadmin) limpa ambos os campos.

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "local_credentials",
        sa.Column("totp_secret", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "local_credentials",
        sa.Column("totp_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("local_credentials", "totp_enabled")
    op.drop_column("local_credentials", "totp_secret")
