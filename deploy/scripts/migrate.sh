#!/usr/bin/env bash
# Migration explicita: backup -> para o app -> upgrade head -> sobe o app.
# O backend fica PARADO durante a migration: a versao antiga nao opera
# contra um schema que pode estar a frente dela.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT="${PROJECT:-portal-uma}"
COMPOSE="docker compose -p ${PROJECT} -f docker-compose.vps.yml --env-file "${ENV_FILE:-.env}""
set -a; . "./${ENV_FILE:-.env}"; set +a

echo ">> backup pre-migration"
PRE="backups/pre-migrate-$(date +%Y%m%d-%H%M%S).dump"
$COMPOSE exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$PRE"
[ -s "$PRE" ] || { echo "!! backup vazio — abortando"; rm -f "$PRE"; exit 1; }

echo ">> parando backend (schema pode ficar a frente da versao em execucao)"
$COMPOSE stop backend
echo ">> alembic upgrade head"
if ! $COMPOSE --profile migrate run --rm migrate; then
  echo "!! MIGRATION FALHOU — backend mantido parado." >&2
  echo "!! Para recuperar: bash scripts/restore.sh $PRE" >&2
  exit 1
fi
$COMPOSE up -d --no-deps backend
echo ">> migration concluida; backend de volta"
