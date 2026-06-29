#!/usr/bin/env bash
# FASE 6.3 — Builder de la app stateless Jupyter Notebook.
# Espejo de build-lab-vm-base-mate.sh adaptado a contenedores (sin --vm).
# Idempotente: SKIP si la imagen existe (rc=10), --force para reconstruir.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

APP="jupyter"
BASE="app-${APP}-build"
IMAGE_ALIAS="app-${APP}"
PUERTO=8888

# Parse --force
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    *) echo "Argumento desconocido: $arg" >&2; exit 1 ;;
  esac
done
export FORCE

cleanup() { local rc=$?; lxc delete -f "$BASE" --project "$PROJECT" 2>/dev/null || true; return $rc; }
trap cleanup EXIT INT TERM

lxc project switch "$PROJECT"
lxc delete -f "$BASE" --project "$PROJECT" 2>/dev/null || true

precheck_alias "$IMAGE_ALIAS"

# Lanzar CONTENEDOR temporal (sin --vm, perfil stateless)
lxc launch "$IMAGE_SOURCE" "$BASE" -p "$PROFILE" --project "$PROJECT"

wait_agent "$BASE"

# Instalar Jupyter Notebook
lxc exec "$BASE" --project "$PROJECT" -- bash <<'EOF'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3-pip python3-venv curl ca-certificates
pip3 install --no-cache-dir --break-system-packages notebook
# Config Jupyter para escuchar en 0.0.0.0 sin token (el acceso lo controla Nginx)
mkdir -p /root/.jupyter
cat > /root/.jupyter/jupyter_notebook_config.py <<'JUP'
c.NotebookApp.ip = '0.0.0.0'
c.NotebookApp.port = 8888
c.NotebookApp.open_browser = False
c.NotebookApp.token = ''
c.NotebookApp.password = ''
c.NotebookApp.allow_origin = '*'
JUP
# Servicio systemd para arrancar Jupyter
cat > /etc/systemd/system/jupyter.service <<'SVC'
[Unit]
Description=Jupyter Notebook
After=network.target
[Service]
Type=simple
ExecStart=/usr/local/bin/jupyter-notebook --notebook-dir=/root
Restart=always
[Install]
WantedBy=multi-user.target
SVC
systemctl enable jupyter
EOF

# Smoke test HTTP real (no TCP): arrancar y probar
lxc exec "$BASE" --project "$PROJECT" -- bash -c "
  systemctl start jupyter 2>/dev/null || true
  sleep 3
  curl -sf http://localhost:${PUERTO}/ >/dev/null
" || { echo "ERROR: smoke test HTTP ${PUERTO} falló" >&2; exit 1; }

clean_for_publish "$BASE"
stop_and_validate "$BASE"
publish_app "$BASE" "$IMAGE_ALIAS"