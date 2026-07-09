#!/usr/bin/env bash
# install-all.sh — Instalación limpia y completa del proyecto en el servidor.
#
# Siempre que se ejecuta: desinstala el proyecto completo (uninstall-all.sh)
# y lo reinstala de cero. Genera secretos automáticamente con openssl.
#
# Uso (asistente dirigido — recomendado):
#   sudo bash install-all.sh
#   Sin flags y desde un terminal, pide interactivamente todo lo necesario
#   (dominio, email certbot, admin de la consola, SMTP) con validación y
#   resumen de confirmación antes de tocar nada.
#
# Uso (no interactivo, automatización):
#   sudo bash install-all.sh --domain=lab.example.com --email=admin@example.com \
#       [--admin-email=admin@example.com --smtp-user=xxx --smtp-pass=yyy]
#
# Flags:
#   --domain=DOM       Dominio público (ej. lab.example.com) para Nginx + certbot.
#   --email=EMAIL      Email admin para certbot (Let's Encrypt).
#   --admin-email=E    Primer admin de la consola web (se siembra en BD).
#   --smtp-user=U      Usuario SMTP (Mailtrap o real). Si vacío, se deja para rellenar.
#   --smtp-pass=P      Password SMTP (visible en ps/historial; en hosts
#                      compartidos usa el asistente, que lo pide oculto).
#   --skip-preflight   Degrada los aborts del preflight a warnings (bajo tu
#                      responsabilidad; útil en entornos no estándar).
#
# Requisitos previos:
#   - Ubuntu Server 22.04/24.04 limpio con acceso root (el preflight lo verifica).
#   - DNS: registro A apuntando DOM a la IP pública del host.
#   - Firewall edge: 80/tcp y 443/tcp abiertos hacia el host.
#   - Virtualización KVM disponible (/dev/kvm) — VT-x/AMD-V o nested KVM.
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
ADMIN_EMAIL=""
SMTP_USER=""
SMTP_PASS=""
SKIP_PREFLIGHT=0

for arg in "$@"; do
  case "$arg" in
    --domain=*)       DOMAIN="${arg#--domain=}" ;;
    --email=*)        EMAIL="${arg#--email=}" ;;
    --admin-email=*)  ADMIN_EMAIL="${arg#--admin-email=}" ;;
    --smtp-user=*)    SMTP_USER="${arg#--smtp-user=}" ;;
    --smtp-pass=*)    SMTP_PASS="${arg#--smtp-pass=}" ;;
    --skip-preflight) SKIP_PREFLIGHT=1 ;;
    --help|-h)        sed -n '2,32p' "$0"; exit 0 ;;
    *) echo "Argumento desconocido: $arg" >&2; exit 1 ;;
  esac
done

# Validación de formato (misma para flags y asistente). Charsets cerrados:
# también protegen las interpolaciones posteriores (sqlite, nginx, certbot).
RE_DOMAIN='^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'
RE_EMAIL='^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'

valida() { # valida VALOR REGEX → 0/1
  printf '%s' "$1" | grep -Eq "$2"
}

# pregunta "texto" VAR REGEX "default" "mensaje de error"
pregunta() {
  local texto="$1" var="$2" re="$3" def="${4:-}" err="${5:-valor no válido}" val
  while :; do
    if [ -n "$def" ]; then
      read -r -p "$texto [$def]: " val
      val="${val:-$def}"
    else
      read -r -p "$texto: " val
    fi
    val="$(printf '%s' "$val" | tr -d '[:space:]')"
    if valida "$val" "$re"; then
      printf -v "$var" '%s' "$val"
      return 0
    fi
    echo "  ERROR: $err" >&2
  done
}

# --- Asistente dirigido: sin --domain/--email y con terminal ----------------
if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
  if [ ! -t 0 ]; then
    echo "ERROR: sin terminal interactivo, --domain y --email son obligatorios." >&2
    echo "Uso: sudo bash $0 --domain=lab.example.com --email=admin@example.com" >&2
    echo "     (o ejecuta 'sudo bash $0' desde un terminal para el asistente dirigido)" >&2
    exit 1
  fi

  echo "============================================================"
  echo "  ASISTENTE DE INSTALACIÓN — LXD REMOTE WEB DESKTOPS"
  echo "============================================================"
  echo "Este asistente pide los datos necesarios y después instala TODO"
  echo "el sistema (dependencias, LXD, provision-api, Guacamole, Nginx,"
  echo "certificado TLS) sin más intervención."
  echo ""
  echo "ATENCIÓN: si existe una instalación previa del proyecto en este"
  echo "host, se desinstalará y se reinstalará de cero."
  echo ""

  echo "1/4 — Dominio público del portal. Necesita un registro DNS A"
  echo "      apuntando a la IP pública de este host (certbot emitirá el"
  echo "      certificado TLS para él)."
  pregunta "  Dominio (ej. lab.example.com)" DOMAIN "$RE_DOMAIN" "" \
    "dominio no válido (minúsculas, ej. lab.example.com)"
  echo ""

  echo "2/4 — Email para Let's Encrypt (avisos de caducidad del certificado)."
  pregunta "  Email para certbot" EMAIL "$RE_EMAIL" "" "email no válido"
  echo ""

  echo "3/4 — Primer administrador de la consola web (/admin). Se dará de"
  echo "      alta automáticamente para que puedas entrar con magic link."
  pregunta "  Email del administrador" ADMIN_EMAIL "$RE_EMAIL" "$EMAIL" "email no válido"
  echo ""

  echo "4/4 — Credenciales SMTP para enviar los magic links (Mailtrap en"
  echo "      dev; SendGrid/SES u otro real en prod). Puedes dejarlo para"
  echo "      después editando /etc/provision/provision.env, pero sin SMTP"
  echo "      nadie podrá iniciar sesión."
  read -r -p "  ¿Configurar SMTP ahora? [S/n]: " resp
  case "${resp,,}" in
    n|no)
      echo "  (SMTP quedará pendiente: MAILTRAP_USER/MAILTRAP_PASS en el .env)"
      ;;
    *)
      read -r -p "  Usuario SMTP: " SMTP_USER
      read -r -s -p "  Password SMTP (no se muestra al teclear): " SMTP_PASS
      echo ""
      ;;
  esac
  echo ""

  echo "============================================================"
  echo "  RESUMEN DE LA INSTALACIÓN"
  echo "  Dominio            : $DOMAIN"
  echo "  Email certbot      : $EMAIL"
  echo "  Admin de la consola: $ADMIN_EMAIL"
  if [ -n "$SMTP_USER" ]; then
    echo "  SMTP               : configurado (usuario: $SMTP_USER)"
  else
    echo "  SMTP               : pendiente (rellenar tras instalar)"
  fi
  echo "  Instalación limpia : desinstala cualquier instalación previa"
  echo "============================================================"
  read -r -p "¿Continuar con la instalación? [s/N]: " resp
  case "${resp,,}" in
    s|si|sí|y|yes) ;;
    *) echo "Instalación cancelada. No se ha tocado nada."; exit 0 ;;
  esac
fi

# Validar también los valores llegados por flag (mismo charset cerrado).
valida "$DOMAIN" "$RE_DOMAIN" || { echo "ERROR: --domain no válido: $DOMAIN" >&2; exit 1; }
valida "$EMAIL" "$RE_EMAIL"   || { echo "ERROR: --email no válido: $EMAIL" >&2; exit 1; }
if [ -n "$ADMIN_EMAIL" ]; then
  valida "$ADMIN_EMAIL" "$RE_EMAIL" || { echo "ERROR: --admin-email no válido: $ADMIN_EMAIL" >&2; exit 1; }
fi

# apt nunca interactivo en toda la instalación + preseed de iptables-persistent
# (sin esto, iptables-persistent abre un diálogo debconf y bloquea el script).
export DEBIAN_FRONTEND=noninteractive
if command -v debconf-set-selections >/dev/null 2>&1; then
  echo 'iptables-persistent iptables-persistent/autosave_v4 boolean true' | debconf-set-selections
  echo 'iptables-persistent iptables-persistent/autosave_v6 boolean true' | debconf-set-selections
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
for f in *.sh provision/*.sh guacamole/*.sh nginx/*.sh build-apps/*.sh; do
  [ -f "$f" ] && dos2unix "$f" 2>/dev/null || true
done
echo "OK"

# ---------------------------------------------------------------------------
# 0b. Preflight — verificaciones fail-fast del host antes de tocar nada.
#     --skip-preflight degrada los ABORT a warnings (bajo responsabilidad
#     del operador). Cada check es re-ejecutable: verifica y solo instala
#     lo que falta.
# ---------------------------------------------------------------------------
echo "==> 0b. Preflight del host"
PREFLIGHT_ERRORS=0
PREFLIGHT_LOG="/var/log/lab-preflight-apt.log"

pf_abort() {
  if [ "$SKIP_PREFLIGHT" -eq 1 ]; then
    echo "  WARN (--skip-preflight): $1" >&2
  else
    echo "  ERROR: $1" >&2
    PREFLIGHT_ERRORS=1
  fi
}
pf_warn() { echo "  WARN: $1" >&2; }

# --- Checks read-only primero (no instalan nada) ---------------------------
# SO soportado: Ubuntu 22.04 / 24.04
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}-${VERSION_ID:-}" in
    ubuntu-22.04|ubuntu-24.04) echo "  SO: Ubuntu ${VERSION_ID} OK" ;;
    *) pf_abort "SO no soportado (${ID:-desconocido} ${VERSION_ID:-}). Se requiere Ubuntu Server 22.04 o 24.04." ;;
  esac
else
  pf_abort "no se puede leer /etc/os-release para verificar el SO."
fi

# KVM (ABORT): sin /dev/kvm las VMs LXD fallan tarde y de forma críptica
# en build-lab-vm-base-mate.sh.
if [ -c /dev/kvm ]; then
  echo "  KVM: /dev/kvm presente OK"
else
  pf_abort "/dev/kvm no existe. Habilita VT-x/AMD-V en la BIOS o la virtualización anidada en el hipervisor."
fi

# --- Checks que pueden instalar paquetes: solo si no hay aborts previos ----
if [ "$PREFLIGHT_ERRORS" -ne 0 ]; then
  echo "  (checks con instalación de paquetes omitidos: hay errores previos)" >&2
else
  # ZFS (ABORT): el preseed usa driver zfs en stateless-pool y persistent-pool.
  if modprobe zfs 2>/dev/null; then
    echo "  ZFS: módulo zfs cargado OK"
  else
    echo "  ZFS: módulo ausente; instalando zfsutils-linux + linux-modules-extra-$(uname -r) (log: $PREFLIGHT_LOG)..."
    apt-get install -y zfsutils-linux "linux-modules-extra-$(uname -r)" >>"$PREFLIGHT_LOG" 2>&1 || true
    if modprobe zfs 2>/dev/null; then
      echo "  ZFS: módulo zfs cargado tras instalación OK"
    else
      pf_abort "no se pudo cargar zfs.ko. Revisa $PREFLIGHT_LOG. En kernels cloud (-kvm/-aws) linux-modules-extra-$(uname -r) puede no existir: usa un kernel -generic o instala zfs-dkms. Si el kernel se actualizó, reinicia y reintenta."
    fi
  fi

  # snapd: necesario para 'snap install lxd' en server-setup-lxd.sh.
  if ! command -v snap >/dev/null 2>&1; then
    echo "  snapd: ausente; instalando (log: $PREFLIGHT_LOG)..."
    apt-get install -y snapd >>"$PREFLIGHT_LOG" 2>&1 || pf_abort "no se pudo instalar snapd. Revisa $PREFLIGHT_LOG."
  fi
  if command -v snap >/dev/null 2>&1; then
    if timeout 180 snap wait system seed.loaded 2>/dev/null; then
      echo "  snapd: OK"
    else
      pf_warn "snapd no terminó de sembrarse en 180s (snap wait system seed.loaded); snap install lxd podría fallar."
    fi
  fi
fi

# Puertos 80/443: ocupados por algo distinto de nginx → ABORT.
ports_ok=1
for port in 80 443; do
  occ="$(ss -tlnp "sport = :$port" 2>/dev/null | awk 'NR>1' || true)"
  if [ -n "$occ" ] && ! printf '%s\n' "$occ" | grep -q 'users:(("nginx"'; then
    pf_abort "puerto $port ocupado por un proceso distinto de nginx: $(printf '%s\n' "$occ" | head -n1)"
    ports_ok=0
  fi
done
if [ "$ports_ok" -eq 1 ]; then
  echo "  Puertos 80/443: OK"
fi

# DNS del dominio → WARN (el veredicto final lo da certbot).
if getent hosts "$DOMAIN" >/dev/null 2>&1; then
  echo "  DNS: $DOMAIN resuelve OK"
else
  pf_warn "el dominio $DOMAIN no resuelve (getent hosts). certbot fallará si el registro A no apunta a este host."
fi

# ufw activo → WARN (convivencia con las reglas iptables del proyecto).
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  pf_warn "ufw está activo; puede interferir con nginx/iptables-lab.sh e iptables-apps.sh."
fi

# RAM / disco → WARN (cotas en README.md §"Cotas de escalabilidad").
ram_gb="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo || true)"
if [ "${ram_gb:-0}" -lt 8 ]; then
  pf_warn "RAM total ${ram_gb:-?}GB < 8GB recomendados."
fi
disk_gb="$(df -BG --output=avail / 2>/dev/null | awk 'NR==2 {gsub("G",""); print $1}' || true)"
if [ "${disk_gb:-0}" -lt 100 ]; then
  pf_warn "espacio libre en / ${disk_gb:-?}GB < 100GB recomendados."
fi

if [ "$PREFLIGHT_ERRORS" -ne 0 ]; then
  echo "" >&2
  echo "Preflight FALLÓ. Corrige los ERROR anteriores, o re-ejecuta con --skip-preflight bajo tu responsabilidad." >&2
  exit 1
fi
echo "OK: preflight superado"

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
# DEBIAN_FRONTEND=noninteractive ya exportado tras el parse de args.
DEPS="dos2unix sqlite3 nginx certbot python3 python3-venv rsync curl openssl iptables-persistent ca-certificates snapd zfsutils-linux tar gzip"
apt-get install -y -qq $DEPS >/dev/null 2>&1 || apt-get install -y $DEPS

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
# 3b. FASE 6.3 — Ampliar stateless-pool y subred lab-stateless
# ---------------------------------------------------------------------------
echo "==> 3b. FASE 6.3 — Ampliar stateless-pool (80GB) y lab-stateless (/23)"
lxc storage set stateless-pool size=80GB 2>/dev/null \
  && echo "OK: stateless-pool ampliado a 80GB" \
  || echo "  (stateless-pool ya en 80GB o no se pudo ampliar)"
lxc network set lab-stateless ipv4.address=10.50.10.1/23 --project labs 2>/dev/null || true
lxc network set lab-stateless ipv4.address=10.50.10.1/23 --project default 2>/dev/null || true
echo "OK: lab-stateless /23"

# ---------------------------------------------------------------------------
# 3c. FASE 6.3 — Builders de apps stateless
# ---------------------------------------------------------------------------
echo "==> 3c. FASE 6.3 — Builders de apps stateless"
for app_script in "$SCRIPT_DIR"/build-apps/build-app-*.sh; do
  [ -f "$app_script" ] || continue
  set +e; bash "$app_script"; rc=$?; set -e
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 10 ]; then
    echo "ERROR: $app_script falló (rc=$rc)" >&2; exit "$rc"
  fi
  [ "$rc" -eq 10 ] && echo "  (app ya existía — SKIP)"
done
echo "OK: imágenes de apps construidas"

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
INTERNAL_TOKEN="$(openssl rand -hex 32)"
ADMIN_JWT_SECRET="$(openssl rand -hex 32)"
ADMIN_JWT_SECRET_PREV="$(openssl rand -hex 32)"
ADMIN_TOTP_KEY="$(openssl rand -hex 32)"

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

# Admin token (para /admin/* automatización)
ADMIN_TOKEN=${ADMIN_TOKEN}

# FASE 6: header secreto compartido Nginx→provision-api
INTERNAL_TOKEN=${INTERNAL_TOKEN}

# FASE 6: JWT admin (secreto separado del navegador)
ADMIN_JWT_SECRET=${ADMIN_JWT_SECRET}
ADMIN_JWT_SECRET_PREV=${ADMIN_JWT_SECRET_PREV}
ADMIN_JWT_TTL=1800
ADMIN_JWT_AUD=lab-admin
ADMIN_MAGIC_LINK_TTL=300
ADMIN_TOTP_REQUIRED=0
ADMIN_TOTP_KEY=${ADMIN_TOTP_KEY}
ADMIN_IP_BINDING=0

# Dominio público y URLs internas
PUBLIC_DOMAIN=${DOMAIN}
PROVISION_URL=http://127.0.0.1:8000
PROVISION_URL_VM=http://10.50.20.1:8000
PROVISION_URL_APP=http://10.50.10.1:8000

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

# FASE 6: Apps stateless
APP_IDLE_MINUTES=30
SHARED_IDLE_HOURS=6
APP_CREATING_TIMEOUT=300
GRACE_AFTER_RESTART=900
MAX_APP_INSTANCES=40
ALWAYS_ON_BUDGET_MB=8192
APP_LAUNCH_SEM=6
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

# 4.5 Sembrar el primer admin de la consola (email ya validado contra
#     RE_EMAIL, charset cerrado sin comillas → interpolación SQL segura).
if [ -n "$ADMIN_EMAIL" ]; then
  DB_PATH="/var/lib/provision/provision.db"
  if [ -f "$DB_PATH" ]; then
    if sqlite3 "$DB_PATH" "INSERT OR IGNORE INTO admins(email,role,active,created_at) VALUES('$ADMIN_EMAIL','admin',1,datetime('now'));"; then
      echo "OK: admin de la consola dado de alta: $ADMIN_EMAIL"
    else
      echo "WARN: no se pudo sembrar el admin; hazlo por SQL (ver docs/USO.md)" >&2
    fi
  else
    echo "WARN: $DB_PATH aún no existe; da de alta el admin por SQL (ver docs/USO.md)" >&2
  fi
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
echo "OK: iptables VMs configuradas"

# 5.4 FASE 6.3: iptables apps stateless
bash "$SCRIPT_DIR/nginx/iptables-apps.sh"
echo "OK: iptables apps configuradas"

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
echo "Secretos generados: NO se imprimen por seguridad."
echo "  Todos están en /etc/provision/provision.env (root:provision, 0640)."
echo "  Consulta: sudo less /etc/provision/provision.env"
echo ""
if [ -z "$SMTP_USER" ] || [ -z "$SMTP_PASS" ]; then
  echo "⚠️  SMTP sin configurar. Edita /etc/provision/provision.env y rellena:"
  echo "    MAILTRAP_USER y MAILTRAP_PASS"
  echo "  Luego: sudo systemctl restart provision"
  echo ""
fi
echo "Pasos siguientes:"
if [ -n "$ADMIN_EMAIL" ]; then
  echo "  1. Entra en la consola admin: https://$DOMAIN/admin/login"
  echo "     (magic link al email: $ADMIN_EMAIL)"
else
  echo "  1. Da de alta un admin (ver docs/USO.md) y entra en https://$DOMAIN/admin/login"
fi
echo "  2. Crea el lab (pestaña Labs) y matricula alumnos (pestaña Matrículas)."
echo "  3. El alumno entra en https://$DOMAIN con su email de matrícula."
echo "  (Alternativa por SQL/curl: ver docs/USO.md, sección 'Operación avanzada')"
echo ""
echo "Para desinstalar: sudo bash uninstall-all.sh --domain=$DOMAIN"
echo "Para reinstalar : sudo bash $0   (asistente) o con flags --domain/--email"
