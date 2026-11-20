#!/usr/bin/env bash
# Migracao de dados homologados (portal_uma_dev -> banco da VPS):
# restore do dump + migration pendente (ex.: 0029) + verificacao de contagens.
# NAO use dumps dos ambientes ficticios 8081/8082.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT="${PROJECT:-portal-uma}"
COMPOSE="docker compose -p ${PROJECT} -f docker-compose.vps.yml --env-file "${ENV_FILE:-.env}""
DUMP="${1:?informe o dump do portal_uma_dev}"
set -a; . "./${ENV_FILE:-.env}"; set +a

echo ">> restore do dump homologado"
echo "$POSTGRES_DB" | bash scripts/restore.sh "$DUMP"
echo ">> migrations pendentes (ex.: 0029_superadmin_totp)"
$COMPOSE --profile migrate run --rm migrate
echo ">> verificacao pos-migracao"
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT version_num FROM alembic_version;" \
  -c "SELECT count(*) AS usuarios FROM users WHERE deleted_at IS NULL;" \
  -c "SELECT count(*) AS credenciais FROM local_credentials;" \
  -c "SELECT count(*) AS clientes_televendas FROM contact_clients;" \
  -c "SELECT count(*) AS categorias_despesa FROM expense_categories;"
echo ">> concluido — confira as contagens contra o ambiente de origem"
