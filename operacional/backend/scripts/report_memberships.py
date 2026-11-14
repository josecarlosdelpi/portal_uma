"""Relatorio de conferencia: usuarios com mais de um grupo principal.

Execute ANTES de aplicar a migracao 0021 em uma base com dados reais:

    cd operacional/backend
    python -m scripts.report_memberships

Para cada usuario duplicado mostra qual vinculo a deduplicacao manteria
(menor nome de grupo, desempate por id) e quais seriam removidos.
Faca backup (pg_dump) antes de reaplicar a migracao com
PORTAL_MEMBERSHIP_DEDUP_OK=1.
"""
from importlib import util as importlib_util
from pathlib import Path

from app.db import get_engine


def main() -> None:
    # A consulta vive na propria migracao para nunca divergir da regra
    # aplicada na deduplicacao.

    migration = Path(__file__).resolve().parent.parent / \
        "migrations" / "versions" / "0021_membership_unique.py"
    spec = importlib_util.spec_from_file_location("mig0021", migration)
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = get_engine()
    with engine.connect() as conn:
        duplicates = module.multi_memberships(conn)

    if not duplicates:
        print("Nenhum usuario com multiplos grupos — a migracao 0021 "
              "aplica direto, sem deduplicacao.")
        return
    print(f"{len(duplicates)} usuario(s) com mais de um vinculo:\n")
    for item in duplicates:
        print(f"  {item['display_name']} — {item['total']} vinculos")
        print(f"    manteria : {item['kept']['name']} ({item['kept']['group_id']})")
        for group in item["removed"]:
            print(f"    removeria: {group['name']} ({group['group_id']})")
        print()
    print("Revise o relatorio, faca backup (pg_dump) e reaplique a migracao")
    print("com PORTAL_MEMBERSHIP_DEDUP_OK=1 para deduplicar conscientemente.")


if __name__ == "__main__":
    main()
