#!/usr/bin/env bash
# Restore controlado e seguro:
#  1. valida o dump (pg_restore -l) — recusa arquivo invalido/vazio
#  2. backup do banco ATUAL antes de qualquer drop (ponto de retorno)
#  3. para o app, encerra conexoes, DROP+CREATE em passos separados
#  4. restore e verificacao — falha nunca e reportada como sucesso
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT="${PROJECT:-portal-uma}"
COMPOSE="docker compose -p ${PROJECT} -f docker-compose.vps.yml --env-file "${ENV_FILE:-.env}""
set -a; . "./${ENV_FILE:-.env}"; set +a
DUMP="${1:?informe o arquivo .dump}"

fail(){ echo "!! $1" >&2; exit 1; }
[ -f "$DUMP" ] || fail "arquivo nao encontrado: $DUMP"
[ -s "$DUMP" ] || fail "arquivo vazio: $DUMP"

echo ">> validando formato do dump"
if ! docker run --rm -i postgres:16-alpine pg_restore -l < "$DUMP" > /dev/null 2>&1; then
  fail "$DUMP nao e um pg_dump custom valido"
fi

echo ">> ATENCAO: restaurar '$DUMP' sobrescreve o banco '${POSTGRES_DB}'."
read -r -p "digite o nome do banco para confirmar: " CONF
[ "$CONF" = "$POSTGRES_DB" ] || fail "confirmacao incorreta — abortado"

echo ">> backup de seguranca do banco atual"
PRE="backups/pre-restore-$(date +%Y%m%d-%H%M%S).dump"
$COMPOSE exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$PRE"
[ -s "$PRE" ] || fail "backup pre-restore vazio — abortando sem tocar no banco"
echo ">> ponto de retorno em $PRE"

echo ">> parando aplicacao (dados nao serao gravados durante o restore)"
$COMPOSE stop backend frontend caddy pgbackups

echo ">> encerrando conexoes e recriando o banco"
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${POSTGRES_DB}' AND pid<>pg_backend_pid();" \
  || fail "falha ao encerrar conexoes"
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};" || fail "falha no DROP DATABASE"
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres \
  -c "CREATE DATABASE ${POSTGRES_DB};" || fail "falha no CREATE DATABASE"

echo ">> restaurando $DUMP"
if ! $COMPOSE exec -T db sh -c 'cat > /tmp/in.dump && pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error /tmp/in.dump' < "$DUMP"; then
  echo "!! RESTORE FALHOU — o banco pode estar parcialmente restaurado." >&2
  echo "!! Recupere o ponto de retorno: bash scripts/restore.sh $PRE" >&2
  $COMPOSE up -d || true
  exit 1
fi
echo ">> restore concluido — subindo a stack"
$COMPOSE up -d
bash scripts/health.sh
