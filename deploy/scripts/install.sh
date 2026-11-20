#!/usr/bin/env bash
# Instalacao inicial: valida .env, sobe o banco, migra, entao sobe o app.
# Ordem garante que o backend/ERP nunca toque num banco sem schema.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT="${PROJECT:-portal-uma}"
COMPOSE="docker compose -p ${PROJECT} -f docker-compose.vps.yml --env-file "${ENV_FILE:-.env}""

if [ ! -f "${ENV_FILE:-.env}" ]; then
  cp .env.example "${ENV_FILE:-.env}"
  SENHA=$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${SENHA}/" "${ENV_FILE:-.env}"
  echo ">> .env criado com senha de banco gerada."
fi
chmod 600 "${ENV_FILE:-.env}" 2>/dev/null || true
set -a; . "./${ENV_FILE:-.env}"; set +a

# --- validacao estrita da configuracao ---------------------------------
fail(){ echo "!! $1" >&2; exit 1; }
[ -n "${DOMAIN:-}" ] || fail "DOMAIN ausente em deploy/.env"
[ -n "${POSTGRES_DB:-}" ] && [ -n "${POSTGRES_USER:-}" ] \
  || fail "POSTGRES_DB/POSTGRES_USER ausentes em deploy/.env"
[ -n "${POSTGRES_PASSWORD:-}" ] || fail "POSTGRES_PASSWORD vazio"
case "$POSTGRES_PASSWORD" in
  TROQUE*|*exemplo*|*example*) fail "POSTGRES_PASSWORD ainda e o valor de exemplo — troque ou apague .env para regenerar";;
esac
[ "${#POSTGRES_PASSWORD}" -ge 16 ] \
  || fail "POSTGRES_PASSWORD fraca (min. 16 caracteres)"
if [ "${ERP_SYNC_ENABLED:-true}" = "true" ]; then
  [ -n "${GOOGLE_DRIVE_FOLDER_ID:-}" ] \
    && [ "$GOOGLE_DRIVE_FOLDER_ID" != "ID_DA_PASTA_NO_DRIVE" ] \
    || fail "ERP_SYNC_ENABLED=true exige GOOGLE_DRIVE_FOLDER_ID real"
  SA="${DRIVE_SA_FILE:-./secrets/uma-drive-sa.json}"
  [ -f "$SA" ] || fail "Arquivo da conta de servico nao encontrado: $SA"
fi

mkdir -p secrets backups && chmod 700 secrets 2>/dev/null || true

echo ">> build das imagens"
$COMPOSE build
echo ">> subindo APENAS o banco"
$COMPOSE up -d db
echo ">> aguardando banco"
$COMPOSE exec -T db sh -c 'until pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; do sleep 1; done'
echo ">> migrations explicitas (schema antes de qualquer app)"
$COMPOSE --profile migrate run --rm migrate
echo ">> subindo backend, frontend, proxy e backups"
$COMPOSE up -d
echo ">> aguardando backend saudavel"
for i in $(seq 1 40); do
  if $COMPOSE exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')" >/dev/null 2>&1; then
    echo ">> OK. Acesse https://${DOMAIN}"; exit 0
  fi
  sleep 2
done
fail "backend nao respondeu ao healthcheck — verifique: $COMPOSE logs backend"
