#!/usr/bin/env bash
# Atualizacao segura: pull(opcional) -> backup -> build -> stop app -> migrate -> restart -> health.
# Se a migration falhar, o backend permanece parado e o backup preservado.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT="${PROJECT:-portal-uma}"
COMPOSE="docker compose -p ${PROJECT} -f docker-compose.vps.yml --env-file "${ENV_FILE:-.env}""
set -a; . "./${ENV_FILE:-.env}"; set +a

if [ "${SKIP_GIT_PULL:-false}" != "true" ]; then
  echo ">> atualizando codigo"
  git fetch --all --prune
  git checkout "${1:-main}"
  git pull --ff-only
fi

echo ">> backup pre-update"
PRE="backups/pre-update-$(date +%Y%m%d-%H%M%S).dump"
$COMPOSE exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$PRE"
[ -s "$PRE" ] || { echo "!! backup vazio — abortando"; rm -f "$PRE"; exit 1; }
echo ">> backup em $PRE"

echo ">> build"
$COMPOSE build
echo ">> parando backend antes de migrar"
$COMPOSE stop backend
echo ">> migrations explicitas"
if ! $COMPOSE --profile migrate run --rm migrate; then
  echo "!! MIGRATION FALHOU — deploy abortado, backend parado." >&2
  echo "!! Backup preservado em $PRE — recupere com: bash scripts/restore.sh $PRE" >&2
  exit 1
fi
echo ">> restart dos servicos"
$COMPOSE up -d
bash scripts/health.sh
