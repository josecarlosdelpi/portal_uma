"""Um grupo principal por usuario, garantido pelo banco.

Revision ID: 0021
Revises: 0020

- Deduplica group_memberships antes da restricao: para cada usuario com
  mais de um vinculo, mantem o grupo que a resolucao atual escolheria
  (menor nome, desempate por id), preservando o comportamento efetivo.
- Cria UNIQUE em group_memberships.user_id: usuario comum tem exatamente
  um grupo principal, mesmo em escritas fora do ORM/servico.

Reversao: remove apenas a restricao de unicidade. Linhas dedupadas NAO sao
restauradas (o downgrade nao recria vinculos removidos) — faca backup
(pg_dump) antes de reverter, ou reaplique os vinculos manualmente.

Estrategia segura de backup/restauracao para migracoes de acesso:
  pg_dump -U <usuario> -d <banco> -F c -f backup_pre_0021.dump
  # testar rollback sempre numa copia restaurada, nunca na base ativa:
  createdb <banco>_rollback && pg_restore -d <banco>_rollback backup_pre_0021.dump
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM group_memberships gm
        USING (
            SELECT gm2.user_id, gm2.group_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY gm2.user_id
                       ORDER BY g.name, gm2.group_id
                   ) AS rn
            FROM group_memberships gm2
            JOIN access_groups g ON g.id = gm2.group_id
        ) ranked
        WHERE gm.user_id = ranked.user_id
          AND gm.group_id = ranked.group_id
          AND ranked.rn > 1
        """
    )
    op.create_unique_constraint(
        "uq_group_memberships_user", "group_memberships", ["user_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_group_memberships_user", "group_memberships")
