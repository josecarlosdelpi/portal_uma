"""Grupos de acesso configuraveis, abrangencia por loja e escopo individual.

Revision ID: 0020
Revises: 0019

- store_groups -> access_groups: nome/descricao/ativo, sem loja unica.
- access_group_stores: abrangencia geografica do grupo (N lojas).
- user_store_scopes: restricao individual de lojas dentro da abrangencia
  do grupo; ausencia de linhas herda toda a abrangencia.
- users.profile passa a indicar FUNCAO ('administrator','seller','staff'),
  sem conceder permissoes.
- Preservacao de acessos: cada grupo de loja migra com suas concessoes e
  sua loja; usuarios 'administrator' (nao superadmin) entram no novo grupo
  'Administradores' com todas as permissoes operacionais nas tres lojas —
  exatamente o acesso que tinham de forma implicita.

Limitacoes conhecidas do downgrade (dados pos-upgrade nao mapeaveis ao
esquema antigo):
- user_store_scopes e descartada: restricoes individuais de loja criadas
  apos o upgrade se perdem.
- Grupos com abrangencia multi-loja recuperam apenas a menor store_code;
  as demais lojas da abrangencia nao sao representaveis no esquema antigo.
- O grupo 'Administradores' e suas memberships sao removidos: admins
  voltam ao acesso implicito por perfil do esquema anterior.
- Excecoes (user_permission_overrides) sao preservadas, mas o esquema
  antigo so honrava 'granted=true'; valores 'false' ficam sem efeito.

Backup/restauracao: antes de aplicar ou reverter, capture
  pg_dump -U <usuario> -d <banco> -F c -f backup_pre_0020.dump
e valide o rollback numa copia restaurada, nunca na base ativa.
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

OPERATIONAL_PERMISSIONS = [
    "overview.view",
    "sales.view", "sales.revenue.view", "sales.target.view",
    "sales.attainment.view", "sales.previous_month.view",
    "sales.previous_year.view", "sales.import",
    "targets.view", "targets.edit",
    "telemarketing.view", "telemarketing.edit",
    "reviews.view", "reviews.edit",
    "supplies.view", "supplies.edit",
    "checklist.view", "checklist.edit",
    "daily_tasks.view", "daily_tasks.edit",
    "training.view", "training.edit",
    "whatsapp_status.view", "whatsapp_status.edit",
    "instagram.view", "instagram.edit",
    "monthly_closing.view", "monthly_closing.edit", "monthly_closing.archive",
]

LEGACY_NAMES = {
    "Joinville": "Vendedores — Joinville",
    "Itajaí": "Vendedores — Itajaí",
    "Tubarão": "Vendedores — Tubarão",
}


def upgrade() -> None:
    op.rename_table("store_groups", "access_groups")
    op.add_column("access_groups", sa.Column(
        "description", sa.String(300), nullable=False, server_default=""))
    op.add_column("access_groups", sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False,
        server_default=sa.func.now()))
    op.add_column("access_groups", sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False,
        server_default=sa.func.now()))

    op.create_table(
        "access_group_stores",
        sa.Column("group_id", sa.Uuid(),
                  sa.ForeignKey("access_groups.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("store_code", sa.String(20),
                  sa.ForeignKey("stores.code", ondelete="RESTRICT"),
                  primary_key=True),
    )
    op.execute(
        "INSERT INTO access_group_stores (group_id, store_code) "
        "SELECT id, store_code FROM access_groups"
    )
    op.drop_constraint("store_groups_store_code_key", "access_groups", type_="unique")
    op.drop_column("access_groups", "store_code")

    op.create_table(
        "user_store_scopes",
        sa.Column("user_id", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("store_code", sa.String(20),
                  sa.ForeignKey("stores.code", ondelete="RESTRICT"),
                  primary_key=True),
    )

    for old, new in LEGACY_NAMES.items():
        op.execute(
            sa.text("UPDATE access_groups SET name = :new WHERE name = :old")
            .bindparams(new=new, old=old)
        )
    op.execute(
        "UPDATE access_groups SET description = "
        "'Grupo de vendedores da loja (migrado)' WHERE description = ''"
    )

    # Grupo "Administradores": reproduz o acesso implicito anterior do perfil.
    admin_group = uuid4()
    groups = sa.table(
        "access_groups",
        sa.column("id", sa.Uuid()), sa.column("name", sa.String()),
        sa.column("description", sa.String()), sa.column("active", sa.Boolean()),
    )
    op.bulk_insert(groups, [{
        "id": admin_group, "name": "Administradores",
        "description": "Administracao operacional das tres lojas (migrado)",
        "active": True,
    }])
    scopes = sa.table(
        "access_group_stores",
        sa.column("group_id", sa.Uuid()), sa.column("store_code", sa.String()),
    )
    op.bulk_insert(scopes, [
        {"group_id": admin_group, "store_code": code}
        for code in ("JOINVILLE", "ITAJAI", "TUBARAO")
    ])
    grants = sa.table(
        "group_permissions",
        sa.column("group_id", sa.Uuid()), sa.column("code", sa.String()),
        sa.column("granted", sa.Boolean()),
    )
    op.bulk_insert(grants, [
        {"group_id": admin_group, "code": code, "granted": True}
        for code in OPERATIONAL_PERMISSIONS
    ])
    op.execute(
        sa.text(
            "INSERT INTO group_memberships (user_id, group_id) "
            "SELECT id, :gid FROM users "
            "WHERE profile = 'administrator' AND is_superadmin = false "
            "AND deleted_at IS NULL"
        ).bindparams(gid=admin_group)
    )

    op.drop_constraint("ck_users_profile", "users", type_="check")
    op.create_check_constraint(
        "ck_users_profile", "users",
        "profile IN ('administrator', 'seller', 'staff')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_profile", "users", type_="check")
    op.create_check_constraint(
        "ck_users_profile", "users",
        "profile IN ('administrator', 'seller')",
    )

    op.execute("DELETE FROM group_memberships WHERE group_id IN "
               "(SELECT id FROM access_groups WHERE name = 'Administradores')")
    op.execute("DELETE FROM access_groups WHERE name = 'Administradores'")

    op.add_column("access_groups", sa.Column(
        "store_code", sa.String(20),
        sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=True))
    # Cada grupo recupera uma loja da abrangencia. Grupos multi-loja criados
    # apos o upgrade mantem a menor loja do conjunto; a unicidade por loja do
    # esquema antigo NAO e restaurada (estrutura incompativel).
    op.execute(
        "UPDATE access_groups g SET store_code = COALESCE(("
        "SELECT MIN(s.store_code) FROM access_group_stores s "
        "WHERE s.group_id = g.id), 'JOINVILLE')"
    )
    op.alter_column("access_groups", "store_code", nullable=False)
    for old, new in LEGACY_NAMES.items():
        op.execute(
            sa.text("UPDATE access_groups SET name = :old WHERE name = :new")
            .bindparams(new=new, old=old)
        )
    op.drop_column("access_groups", "description")
    op.drop_column("access_groups", "created_at")
    op.drop_column("access_groups", "updated_at")

    op.drop_table("user_store_scopes")
    op.drop_table("access_group_stores")
    op.rename_table("access_groups", "store_groups")
