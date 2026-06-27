#!/usr/bin/env bash
# install-all.sh — Instalación limpia y completa del proyecto en el servidor.
#
# Siempre que se ejecuta: desinstala el proyecto completo (uninstall-all.sh)
# y lo reinstala de cero. Genera secretos automáticamente con openssl.
#
# Uso:
#   sudo bash install-all.sh --domain=lab.example.com --email=admin@example.com \
#       [--smtp-user=xxx --smtp-pass=yyy]
#
# Flags obligatorias:
#   --domain=DOM     Dominio público (ej. lab.example.com) para Nginx + certbot.
#   --email=EMAIL    Email admin para certbot (Let's Encrypt).
#
# Flags opcionales:
#   --smtp-user=U    Usuario SMTP (Mailtrap o real). Si vacío, se deja para rellenar.
#   --smtp-pass=P    Password SMTP.
#
# Requisitos previos:
#   - Ubuntu Server LTS con acceso root.
#   - DNS: registro A apuntando DOM a la IP pública del host.
#   - Firewall edge: 80/tcp y 443/tcp abiertos hacia el host.
set -Eeuo pipefail

if grep -q $'\r' "$0"; then
  echo "ERROR: CRLF detectado en $0. Ejecuta: sudo dos2unix $0" >&2
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: ejecuta con sudo: sudo bash $0 ..." >&2
  exit 1
fi

# --- Parse args ---
DOMAIN=""
EMAIL=""
SMTP_USER=""
SMTP_PASS=""

for arg in "$@"; do
  case "$arg" in
    --domain=*)    DOMAIN="${arg#--domain=}" ;;
    --email=*)     EMAIL="${arg#--email=}" ;;
    --smtp-user=*) SMTP_USER="${arg#--smtp-user=}" ;;
    --smtp-pass=*) SMTP_PASS="${arg#--smtp-pass=}" ;;
    --help|-h)     sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "Argumento desconocido: $arg" >&2; exit 1 ;;
  esac
done

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
  echo "ERROR: --domain y --email son obligatorios." >&2
  echo "Uso: sudo bash $0 --domain=lab.example.com --email=admin@example.com" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  INSTALACIÓN LXD REMOTE WEB DESKTOPS"
echo "  Dominio : $DOMAIN"
echo "  Email   : $EMAIL"
echo "============================================================"

# ---------------------------------------------------------------------------
# 0. Convertir CRLF → LF en todos los scripts
# ---------------------------------------------------------------------------
echo "==> 0. Conversión CRLF → LF"
apt-get update -qq
apt-get install -y -qq dos2unix >/dev/null 2>&1
for f in *.sh provision/*.sh guacamole/*.sh nginx/*.sh; do
  [ -f "$f" ] && dos2unix "$f" 2>/dev/null || true
done
echo "OK"

# ---------------------------------------------------------------------------
# 1. Desinstalación previa (instalación limpia)
# ---------------------------------------------------------------------------
echo "==> 1. Desinstalación previa (instalación limpia)"
set +e
bash "$SCRIPT_DIR/uninstall-all.sh" --yes --domain="$DOMAIN"
rc=$?
set -e
if [ "$rc" -ne 0 ]; then
  echo "  (uninstall devolvió rc=$rc; continuando — puede ser primera instalación)"
fi
echo "OK"

# ---------------------------------------------------------------------------
# 2. Instalar dependencias del sistema
# ---------------------------------------------------------------------------
echo "==> 2. Dependencias del sistema"
DEPS="dos2unix sqlite3 nginx certbot python3-venv rsync curl openssl iptables-persistent"
apt-get install -y -qq $DEPS >/dev/null 2>&1 || {
  # iptables-persistent puede pedir input; reintentar con DEBIAN_FRONTEND
  export DEBIAN_FRONTEND=noninteractive
  apt-get install -y $DEPS
}

# Docker + compose v2
if ! command -v docker >/dev/null 2>&1; then
  apt-get install -y -qq docker.io >/dev/null 2>&1 || apt-get install -y docker.io
fi
systemctl enable --now docker 2>/dev/null || true

# docker compose v2 plugin
if ! docker compose version >/dev/null 2>&1; then
  apt-get install -y -qq docker-compose-v2 >/dev/null 2>&1 \
    || apt-get install -y -qq docker-compose-plugin >/dev/null 2>&1 \
    || apt-get install -y docker-compose-v2 docker-compose-plugin 2>/dev/null \
    || true
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: 'docker compose' v2 no disponible. Instala docker-compose-plugin manualmente." >&2
  exit 1
fi
echo "OK"

# ---------------------------------------------------------------------------
# 3. FASE 0 — Infra LXD + imagen base VM
# ---------------------------------------------------------------------------
echo "==> 3. FASE 0 — Infra LXD + imagen base VM"

# Pre-añadir root al grupo lxd para que el check de server-setup-lxd.sh pase
if getent group lxd >/dev/null 2>&1; then
  usermod -aG lxd root 2>/dev/null || true
  if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    usermod -aG lxd "$SUDO_USER" 2>/dev/null || true
  fi
fi

set +e
bash "$SCRIPT_DIR/server-setup-lxd.sh"
rc=$?
set -e

if [ "$rc" -eq 100 ]; then
  # Grupo lxd no activo en la sesión actual. Reintentar con sg.
  echo ">> Grupo lxd no activo. Reintentando con sg lxd..."
  if getent group lxd >/dev/null 2>&1; then
    sg lxd -c "bash $SCRIPT_DIR/server-setup-lxd.sh" || {
      echo "ERROR: no se pudo activar el grupo lxd." >&2
      echo "   Cierra sesión, vuelve a entrar (para activar el grupo lxd) y reejecuta:" >&2
      echo "   sudo bash $0 --domain=$DOMAIN --email=$EMAIL" >&2
      exit 100
    }
  else
    echo "ERROR: grupo lxd no existe. ¿LXD instalado?" >&2
    exit 1
  fi
elif [ "$rc" -ne 0 ]; then
  echo "ERROR: server-setup-lxd.sh falló (rc=$rc)" >&2
  exit "$rc"
fi

# Validaciones FASE 0
echo "  Validando FASE 0..."
lxc storage list >/dev/null 2>&1 || { echo "ERROR: lxc storage list falló" >&2; exit 1; }
lxc image show lab-vm-base --project labs >/dev/null 2>&1 || {
  echo "ERROR: lab-vm-base no existe en labs" >&2; exit 1
}
echo "OK: lab-vm-base publicada en labs"

# ---------------------------------------------------------------------------
# 4. FASE 1-3 — provision-api (auth + cloud-init + provisión on-demand)
# ---------------------------------------------------------------------------
echo "==> 4. FASE 1-3 — provision-api"

# 4.1 Instalar provision-api (crea usuario, venv, systemd, .env placeholder)
bash "$SCRIPT_DIR/provision/install.sh"

# 4.2 Generar secretos y sobrescribir /etc/provision/provision.env
JWT_SECRET="$(openssl rand -hex 32)"
JWT_SECRET_PREV="$(openssl rand -hex 32)"
SERVICE_JWT_SECRET="$(openssl rand -hex 32)"
ADMIN_TOKEN="$(openssl rand -hex 32)"

ENV_FILE="/etc/provision/provision.env"
cat > "$ENV_FILE" <<EOF
# Generado por install-all.sh el $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Proveedor SMTP (dev=mailtrap, prod=real)
SMTP_PROVIDER=mailtrap
MAILTRAP_HOST=smtp.mailtrap.io
MAILTRAP_PORT=587
MAILTRAP_USER=${SMTP_USER}
MAILTRAP_PASS=${SMTP_PASS}

# JWT navegador (HS256)
JWT_SECRET=${JWT_SECRET}
JWT_SECRET_PREV=${JWT_SECRET_PREV}
JWT_TTL=3600
JWT_ISS=provision-api
JWT_AUD=lab-gateway

# Service token de VM (secreto separado)
SERVICE_JWT_SECRET=${SERVICE_JWT_SECRET}
SERVICE_JWT_TTL=86400

# Admin token (para /admin/*)
ADMIN_TOKEN=${ADMIN_TOKEN}

# Dominio público y URLs internas
PUBLIC_DOMAIN=${DOMAIN}
PROVISION_URL=http://127.0.0.1:8000
PROVISION_URL_VM=http://10.50.20.1:8000

# Magic link
MAGIC_LINK_TTL=900
MAGIC_LINK_LEN=32

# Rate-limit (slowapi)
RL_PER_IP=5/minute
RL_PER_EMAIL=3/10minutes
RL_GLOBAL=60/minute

# DB
DB_PATH=/var/lib/provision/provision.db

# Policy engine (FASE 5)
IDLE_MINUTES=60
COURSE_DEADLINE=
KEEP_SNAPSHOTS=5
CREATING_TIMEOUT=600
EOF
chmod 0640 "$ENV_FILE"
chown root:provision "$ENV_FILE"

# 4.3 Reiniciar provision para que coja el grupo lxd y el nuevo .env
systemctl restart provision
sleep 2

# 4.4 Validar
if curl -s http://127.0.0.1:8000/healthz 2>/dev/null | grep -q '"ok"'; then
  echo "OK: provision-api responde"
else
  echo "WARN: provision-api no responde aún. Revisa: journalctl -u provision" >&2
  journalctl -u provision --no-pager -n 20 >&2 || true
fi

# ---------------------------------------------------------------------------
# 5. FASE 4 — Guacamole + guacd + Nginx + iptables
# ---------------------------------------------------------------------------
echo "==> 5. FASE 4 — Acceso web"

# 5.1 Guacamole stack
bash "$SCRIPT_DIR/guacamole/install.sh"
# Validar guacd sin puertos publicados
if docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -q 'guacd.*0.0.0.0'; then
  echo "WARN: guacd tiene puertos publicados (no debería)" >&2
fi
echo "OK: Guacamole stack levantado"

# 5.2 Nginx + certbot
bash "$SCRIPT_DIR/nginx/install.sh" "$DOMAIN" "$EMAIL"
nginx -t 2>/dev/null || { echo "ERROR: nginx -t falló" >&2; exit 1; }
echo "OK: Nginx + certbot configurados"

# 5.3 iptables (aislamiento inter-VM)
bash "$SCRIPT_DIR/nginx/iptables-lab.sh"
echo "OK: iptables configuradas"

# ---------------------------------------------------------------------------
# 6. FASE 5 — Policy engine (ya integrado en provision-api + systemd timer)
# ---------------------------------------------------------------------------
echo "==> 6. FASE 5 — Policy engine"
systemctl is-active provision-reap.timer >/dev/null 2>&1 \
  && echo "OK: provision-reap.timer activo" \
  || echo "WARN: provision-reap.timer no activo"

# ---------------------------------------------------------------------------
# Resumen final
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  INSTALACIÓN COMPLETADA"
echo "============================================================"
echo ""
echo "Servicios:"
systemctl is-active provision provision-reap.timer nginx 2>/dev/null \
  | paste - - - | while read p r n; do
    echo "  provision          : $p"
    echo "  provision-reap.timer: $r"
    echo "  nginx              : $n"
  done
docker compose -f "$SCRIPT_DIR/guacamole/docker-compose.yml" ps --format '{{.Name}} {{.Status}}' 2>/dev/null \
  | while read -r name status; do echo "  $name: $status"; done
echo ""
echo "URL de acceso: https://$DOMAIN"
echo ""
echo "Secretos generados (guárdalos en un sitio seguro):"
echo "  ADMIN_TOKEN        : $ADMIN_TOKEN"
echo "  JWT_SECRET         : $JWT_SECRET"
echo "  (demás secretos en /etc/provision/provision.env)"
echo ""
if [ -z "$SMTP_USER" ] || [ -z "$SMTP_PASS" ]; then
  echo "⚠️  SMTP sin configurar. Edita /etc/provision/provision.env y rellena:"
  echo "    MAILTRAP_USER y MAILTRAP_PASS"
  echo "  Luego: sudo systemctl restart provision"
  echo ""
fi
echo "Pasos siguientes:"
echo "  1. Sembrar matrícula (alumno → lab):"
echo "     sudo sqlite3 /var/lib/provision/provision.db <<SQL"
echo "     INSERT OR IGNORE INTO labs(nombre, imagen, activo) VALUES('lab1','local:lab-vm-base',1);"
echo "     INSERT OR IGNORE INTO enrollments(alumno_id,email,lab,active,created_at)"
echo "       VALUES('alumno1','alumno@ejemplo.com','lab1',1,datetime('now'));"
echo "     SQL"
echo "  2. Probar magic link: curl -X POST http://127.0.0.1:8000/auth/request -H 'Content-Type: application/json' -d '{\"email\":\"alumno@ejemplo.com\"}'"
echo "  3. Abrir https://$DOMAIN en el navegador."
echo ""
echo "Para desinstalar: sudo bash uninstall-all.sh --domain=$DOMAIN"
echo "Para reinstalar : sudo bash $0 --domain=$DOMAIN --email=$EMAIL"
