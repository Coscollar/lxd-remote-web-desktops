#!/usr/bin/env bash
# FASE 4 — Instala lab.conf + certbot HTTP-01 + hook de renovación.
# Idempotente: re-ejecutable sin duplicar.
# Orden seguro: emitir cert PRIMERO (standalone, nginx parado), luego
# instalar site HTTPS y reload. Evita que nginx -t falle por cert ausente.
set -euo pipefail

DOMINIO="${1:-lab.example.com}"
ADMIN_EMAIL="${2:-admin@example.com}"
CONF_SRC="$(dirname "$0")/lab.conf"
CONF_DST="/etc/nginx/sites-available/lab.conf"
ENABLED="/etc/nginx/sites-enabled/lab.conf"
RELOAD_HOOK="/etc/letsencrypt/renewal-hooks/deploy/nginx-reload.sh"
CERT_DIR="/etc/letsencrypt/live/${DOMINIO}"

# CRLF → LF si el repo se editó desde Windows.
if command -v dos2unix >/dev/null 2>&1; then dos2unix "$CONF_SRC" 2>/dev/null || true; fi

# 1. log_format lab_safe debe estar en http{}. Include mínimo si no existe.
LOG_INC="/etc/nginx/conf.d/lab-log.conf"
if [ ! -f "$LOG_INC" ]; then
  install -m0644 /dev/stdin "$LOG_INC" <<'EOF'
log_format lab_safe '$remote_addr $lab_alumno/$lab_name - $request';

# WebSocket Connection upgrade map (evita túnel RDP caiga a polling)
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
EOF
fi

# 2. Emitir cert PRIMERO (standalone, nginx parado) si no existe.
if [ ! -d "$CERT_DIR" ]; then
  echo "[install.sh] emitiendo cert para ${DOMINIO} (standalone)..."
  # Plantilla HTTP-only temporal para que nginx arranque y sirva :80
  # (certbot --standalone necesita :80 libre, así que paramos nginx)
  if systemctl is-active --quiet nginx 2>/dev/null; then
    systemctl stop nginx
  fi
  certbot certonly --standalone -d "${DOMINIO}" --non-interactive --agree-tos -m "${ADMIN_EMAIL}"
  # Reanudar nginx (aún sin site lab, pero al menos default)
  systemctl start nginx
fi

# 3. Validar que el cert existe antes de instalar el site HTTPS.
if [ ! -f "$CERT_DIR/fullchain.pem" ] || [ ! -f "$CERT_DIR/privkey.pem" ]; then
  echo "[install.sh] ERROR: cert no emitido en $CERT_DIR" >&2
  exit 1
fi

# 4. Copiar site con el dominio sustituido (NO machaca si ya existe y es idéntico).
tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
sed "s#lab\.<dominio>#${DOMINIO}#g" "$CONF_SRC" > "$tmp"
install -m0644 "$tmp" "$CONF_DST"

# 5. Habilitar site (idempotente).
ln -sf "$CONF_DST" "$ENABLED"

# 6. Quitar default de Debian si choca con el catch-all de lab.conf.
rm -f /etc/nginx/sites-enabled/default

# 7. Validar config ANTES de reload.
nginx -t

# 8. Hook de renovación: validar antes de reload.
install -d "$(dirname "$RELOAD_HOOK")"
install -m0755 /dev/stdin "$RELOAD_HOOK" <<'EOF'
#!/bin/bash
# Deploy hook de certbot: solo recarga si la config es válida.
nginx -t && nginx -s reload
EOF

# 9. Recarga final.
nginx -t && nginx -s reload

echo "[install.sh] OK — https://${DOMINIO} configurado."