#!/usr/bin/env bash
# FASE 4 — Despliega Guacamole + guacd + mysql (Opción A) e instala schema JDBC.
# Idempotente: no recrea .env si existe, no re-importa schema si ya está.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# CRLF → LF si el repo se editó desde Windows.
if command -v dos2unix >/dev/null 2>&1; then
  for f in docker-compose.yml guacamole.properties guacd.conf .env.example; do
    [ -f "$f" ] && dos2unix "$f" 2>/dev/null || true
  done
fi

# 1. .env con secretos aleatorios si no existe.
if [ ! -f .env ]; then
  root="$(openssl rand -hex 24)"
  pass="$(openssl rand -hex 24)"
  umask 077
  cat > .env <<EOF
GUAC_MYSQL_ROOT=${root}
GUAC_MYSQL_PASS=${pass}
EOF
  echo "[install.sh] .env generado (chmod 600). Guarda copia fuera del repo."
fi

# 2. Levantar stack.
docker compose up -d

# 3. Esperar a mysql (hasta 60s).
echo "[install.sh] esperando mysql..."
for _ in $(seq 1 60); do
  if docker compose exec -T mysql mysqladmin ping -h 127.0.0.1 --silent 2>/dev/null; then
    break
  fi
  sleep 1
done

# 4. Importar schema JDBC de Guacamole (idempotente: CREATE TABLE IF NOT EXISTS).
SCHEMA_URL="https://dlcdn.apache.org/guacamole/1.5.5/binary/guacamole-auth-jdbc-1.5.5.tar.gz"
WORK="$(mktemp -d)"
if [ ! -f "$HERE/.schema-imported" ]; then
  curl -fsSL "$SCHEMA_URL" -o "$WORK/jdbc.tar.gz"
  tar -xzf "$WORK/jdbc.tar.gz" -C "$WORK"
  SCHEMA="$WORK/guacamole-auth-jdbc-1.5.5/mysql/schema/001-create-schema.sql"
  set -a; . "$HERE/.env"; set +a
  docker compose exec -T mysql \
    sh -c "exec mysql -h127.0.0.1 -uroot -p\"${GUAC_MYSQL_ROOT}\" guacamole" < "$SCHEMA"
  touch "$HERE/.schema-imported"
fi

# 5. Validación: guacd sin puertos publicados.
docker ps --format '{{.Names}} {{.Ports}}' | awk '/guacd/ {print "[install.sh] guacd ports:", $0}'

echo "[install.sh] OK — Guacamole en http://127.0.0.1:8080/guacamole/ (solo loopback)."