#!/usr/bin/env bash
# Restore controlado: para o app, restaura o dump indicado, sobe de novo.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.vps.yml --env-file .env"
DUMP="${1:?informe o arquivo .dump}"
echo ">> ATENCAO: restaurar '$DUMP' sobrescreve o banco atual."
read -r -p "digite o nome do banco para confirmar: " CONF
. ./.env
[ "$CONF" = "$POSTGRES_DB" ] || { echo "abortado"; exit 1; }

$COMPOSE stop backend frontend caddy pgbackups
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS ${POSTGRES_DB}; CREATE DATABASE ${POSTGRES_DB};"
cat "$DUMP" | $COMPOSE exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner
$COMPOSE up -d
bash scripts/health.sh
