#!/usr/bin/env bash
# Migration explicita e controlada — nunca roda no boot do backend.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.vps.yml --env-file .env"
echo ">> backup pre-migration"
$COMPOSE exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "backups/pre-migrate-$(date +%Y%m%d-%H%M%S).dump"
echo ">> alembic upgrade head"
$COMPOSE --profile migrate run --rm migrate
