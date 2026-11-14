"""Um grupo principal por usuario, garantido pelo banco.

Revision ID: 0021
Revises: 0020

- Se houver usuarios com mais de um vinculo em group_memberships, a
  migracao NAO deduplica silenciosamente: aborta com instrucoes para
  gerar o relatorio de conferencia. Apos revisar o relatorio e fazer
  backup, reaplique com PORTAL_MEMBERSHIP_DEDUP_OK=1 para deduplicar
  (mantem o grupo de menor nome, desempate por id — o mesmo criterio
  deterministico que a resolucao anterior usaria).
- Cria UNIQUE em group_memberships.user_id: usuario comum tem exatamente
  um grupo principal, mesmo em escritas fora do ORM/servico.

Conferencia pre-migracao em base com dados reais:
  python -m scripts.report_memberships        # lista vinculos multiplos
  pg_dump -U <usuario> -d <banco> -F c -f backup_pre_0021.dump

Reversao: remove apenas a restricao de unicidade. Linhas dedupadas NAO sao
restauradas — o downgrade nao recria vinculos removidos. Valide sempre
numa copia restaurada do backup, nunca na base ativa.
"""
import os

from alembic import op
from sqlalchemy import text

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

DEDUP_ENV_VAR = "PORTAL_MEMBERSHIP_DEDUP_OK"

_DUPLICATES_SQL = """
    SELECT gm.user_id, u.display_name, g.id AS group_id, g.name AS group_name,
           ROW_NUMBER() OVER (
               PARTITION BY gm.user_id ORDER BY g.name, g.id
           ) AS rn,
           COUNT(*) OVER (PARTITION BY gm.user_id) AS total
    FROM group_memberships gm
    JOIN access_groups g ON g.id = gm.group_id
    JOIN users u ON u.id = gm.user_id
    ORDER BY u.display_name, g.name, g.id
"""

_EXCEEDING_SQL = """
    SELECT ranked.user_id, ranked.group_id
    FROM (
        SELECT gm.user_id, gm.group_id,
               ROW_NUMBER() OVER (
                   PARTITION BY gm.user_id
                   ORDER BY g.name, gm.group_id
               ) AS rn
        FROM group_memberships gm
        JOIN access_groups g ON g.id = gm.group_id
    ) ranked
    WHERE ranked.rn > 1
"""


def multi_memberships(conn) -> list[dict]:
    """Usuarios com mais de um vinculo de grupo, com o grupo que seria
    mantido (rn=1) e os que seriam removidos — mesma regra do dedup."""
    rows = conn.execute(text(_DUPLICATES_SQL)).mappings().all()
    by_user: dict = {}
    for row in rows:
        entry = by_user.setdefault(str(row["user_id"]), {
            "user_id": str(row["user_id"]),
            "display_name": row["display_name"],
            "total": row["total"],
            "kept": None, "removed": [],
        })
        if row["total"] <= 1:
            continue
        item = {"group_id": str(row["group_id"]), "name": row["group_name"]}
        if row["rn"] == 1:
            entry["kept"] = item
        else:
            entry["removed"].append(item)
    return [entry for entry in by_user.values() if entry["total"] > 1]


def dedup_memberships(conn) -> int:
    """Remove vinculos excedentes mantendo o grupo de menor nome."""
    rows = conn.execute(text(_EXCEEDING_SQL)).all()
    for user_id, group_id in rows:
        conn.execute(
            text("DELETE FROM group_memberships "
                 "WHERE user_id = :u AND group_id = :g"),
            {"u": user_id, "g": group_id},
        )
    return len(rows)


def upgrade() -> None:
    conn = op.get_bind()
    duplicates = multi_memberships(conn)
    if duplicates and os.environ.get(DEDUP_ENV_VAR) != "1":
        report = "; ".join(
            f"{item['display_name']} ({item['total']} vinculos: manteria "
            f"'{item['kept']['name']}', removeria "
            + ", ".join("'" + g["name"] + "'" for g in item["removed"]) + ")"
            for item in duplicates
        )
        raise RuntimeError(
            f"Encontrados {len(duplicates)} usuario(s) com multiplos grupos. "
            "A migracao nao deduplica silenciosamente. Gere o relatorio com "
            "'python -m scripts.report_memberships', faca backup (pg_dump) e "
            f"reaplique com {DEDUP_ENV_VAR}=1. Detalhes: {report}"
        )
    if duplicates:
        for item in duplicates:
            print(
                f"[0021] dedup {item['display_name']}: mantido "
                f"'{item['kept']['name']}', removidos "
                + ", ".join("'" + g["name"] + "'" for g in item["removed"])
            )
        removed = dedup_memberships(conn)
        print(f"[0021] {removed} vinculo(s) excedente(s) removido(s)")
    op.create_unique_constraint(
        "uq_group_memberships_user", "group_memberships", ["user_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_group_memberships_user", "group_memberships")
