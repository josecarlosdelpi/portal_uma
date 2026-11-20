#!/usr/bin/env bash
# Instalacao inicial na VPS: gera .env, sobe a stack e migra o banco.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.vps.yml --env-file .env"

if [ ! -f .env ]; then
  if [ ! -f .env.example ]; then echo "rode de deploy/"; exit 1; fi
  cp .env.example .env
  SENHA=$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${SENHA}/" .env
  echo ">> .env criado com senha de banco gerada. Revise DOMAIN e GOOGLE_DRIVE_FOLDER_ID em deploy/.env"
fi
mkdir -p secrets backups && chmod 700 secrets
chmod 600 .env

echo ">> build das imagens"
$COMPOSE build
echo ">> subindo banco + proxy + app"
$COMPOSE up -d db caddy frontend backend pgbackups
echo ">> aguardando banco"
$COMPOSE exec -T db sh -c 'until pg_isready -U "$POSTGRES_USER"; do sleep 1; done'
echo ">> migrations (explicitas)"
$COMPOSE --profile migrate run --rm migrate
echo ">> OK. Acesse https://$(grep '^DOMAIN=' .env | cut -d= -f2)"
