#!/usr/bin/env bash
# Atualizacao segura: pull -> backup -> build -> migrate -> restart -> health.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.vps.yml --env-file .env"

echo ">> atualizando codigo"
git fetch --all --prune && git status --short
git checkout "${1:-main}" && git pull --ff-only

echo ">> backup pre-migration"
$COMPOSE exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "backups/pre-update-$(date +%Y%m%d-%H%M%S).dump"

echo ">> build"
$COMPOSE build
echo ">> migrations explicitas"
if ! $COMPOSE --profile migrate run --rm migrate; then
  echo "!! MIGRATION FALHOU — deploy abortado, backup em deploy/backups/" >&2
  exit 1
fi
echo ">> restart dos servicos (mantendo o banco)"
$COMPOSE up -d --no-deps backend frontend caddy pgbackups
bash scripts/health.sh
