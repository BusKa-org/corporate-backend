#!/usr/bin/env bash
# Inicializa o banco de produção de forma idempotente:
# - Cria extensão uuid-ossp se não existir
# - Aplica migrações Alembic (no-op se já estiver em dia)
# - Roda seed (pula se já houver dados)
# NÃO apaga nem altera dados existentes.
set -e

CONTAINER_DB="${CONTAINER_DB:-buska_db_prod}"

if [ -z "$DB_USER" ] || [ -z "$DB_PASSWORD" ] || [ -z "$DB_NAME" ]; then
  echo "Erro: defina DB_USER, DB_PASSWORD e DB_NAME (ou use .env.prod com source)."
  exit 1
fi

echo "[init-db] Aguardando Postgres..."
until PGPASSWORD="$DB_PASSWORD" pg_isready -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" 2>/dev/null; do
  echo "  aguardando..."
  sleep 2
done

echo "[init-db] Garantindo extensão uuid-ossp..."
docker exec "$CONTAINER_DB" psql -U "$DB_USER" -d "$DB_NAME" -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";' 2>/dev/null || true

echo "[init-db] Aplicando migrações (Alembic)..."
python -m alembic upgrade head

echo "[init-db] Rodando seed (será ignorado se já houver dados)..."
python seed.py

echo "[init-db] Concluído."
