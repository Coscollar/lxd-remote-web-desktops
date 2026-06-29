#!/usr/bin/env bash
# Instalación idempotente de provision-api en el host.
# Crea usuario provision (grupo lxd), venv, copia código, instala deps,
# instala units systemd y habilita servicios. Re-ejecutable sin romper.
set -Eeuo pipefail
if grep -q $'\r' "$0"; then echo "CRLF detectado: dos2unix primero"; exit 1; fi

INSTALL_DIR="/opt/provision"
ENV_DIR="/etc/provision"
ENV_FILE="$ENV_DIR/provision.env"
DATA_DIR="/var/lib/provision"
VENV="$INSTALL_DIR/.venv"
SERVICE_USER="provision"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# 1. Usuario provision en grupo lxd (no newgrp en subshell: no persiste)
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
if ! id -nG "$SERVICE_USER" | tr ' ' '\n' | grep -qx lxd; then
  usermod -aG lxd "$SERVICE_USER"
  echo ">> Aviso: $SERVICE_USER necesita re-login o reinicio del servicio para activar grupo lxd"
fi

# 2. Directorios
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$DATA_DIR"
install -d -o root             -g "$SERVICE_USER" -m 0750 "$ENV_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0755 "$INSTALL_DIR"

# 3. Copiar código (idempotente: rsync --delete mantiene el dir limpio)
rsync -a --delete \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.db' --exclude='.env' \
  "$SCRIPT_DIR/provision/" "$INSTALL_DIR/"

# 4. venv + deps (idempotente: solo crea si falta)
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# 5. env file (NO sobreescribe si ya existe: protege secretos reales)
if [ ! -f "$ENV_FILE" ]; then
  cp "$SCRIPT_DIR/provision/.env.example" "$ENV_FILE"
  # El servicio corre con ReadWritePaths=/var/lib/provision y WorkingDirectory=/opt/provision:
  # la DB debe vivir en /var/lib/provision para que ProtectSystem=strict la permita escribir.
  sed -i "s|^DB_PATH=.*|DB_PATH=$DATA_DIR/provision.db|" "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
  chown root:"$SERVICE_USER" "$ENV_FILE"
  echo ">> EDITAR $ENV_FILE con secretos reales (JWT_SECRET, SERVICE_JWT_SECRET, SMTP_*) antes de arrancar"
fi

# 6. systemd units
for unit in provision.service provision-reap.service provision-reap.timer \
            provision-reap-apps.service provision-reap-apps.timer; do
  install -m 0644 "$SCRIPT_DIR/systemd/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now provision.service
systemctl enable --now provision-reap.timer
systemctl enable --now provision-reap-apps.timer

echo ">> Instalación completa."
echo "   systemctl status provision"
echo "   journalctl -u provision -f"