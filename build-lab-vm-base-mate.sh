#!/usr/bin/env bash
set -Eeuo pipefail

# FASE 0.10: detección CRLF — dos2unix antes de ejecutar
if grep -q $'\r' "$0"; then
  echo "CRLF detectado en $0: ejecuta 'dos2unix $0' primero" >&2
  exit 1
fi

# FASE 0.11: constantes del builder
PROJECT="labs"
BASE_VM="vm-base"
IMAGE_ALIAS="lab-vm-base"
IMAGE_VERSIONED="lab-vm-base-v$(date +%Y%m%d)"
IMAGE_SOURCE="local:ubuntu-22.04-vm"
PROFILE="persistent"

# Limpieza robusta: preserva rc del caller (no lo aplasta con el del delete)
cleanup() {
  local rc=$?
  lxc delete -f "$BASE_VM" --project "$PROJECT" 2>/dev/null || true
  return $rc
}
trap cleanup EXIT INT TERM

echo "==> Switch a proyecto $PROJECT"
lxc project switch "$PROJECT"

# Pre-borrado de VM huérfana (kill -9 / OOM no disparan el trap)
lxc delete -f "$BASE_VM" --project "$PROJECT" 2>/dev/null || true

# Verificación exacta (no grep parcial sobre `lxc image list`)
if lxc image show "$IMAGE_ALIAS" --project "$PROJECT" >/dev/null 2>&1; then
  if [ "${1:-}" != "--force" ]; then
    echo "SKIP: $IMAGE_ALIAS ya existe en $PROJECT. Use --force para reconstruir."
    exit 10
  fi
  echo "==> --force: borrando alias previos"
  lxc image delete "$IMAGE_ALIAS"    --project "$PROJECT" 2>/dev/null || true
  lxc image delete "$IMAGE_VERSIONED" --project "$PROJECT" 2>/dev/null || true
fi

echo "==> Lanzando VM temporal $BASE_VM desde $IMAGE_SOURCE"
lxc launch "$IMAGE_SOURCE" "$BASE_VM" --vm -p "$PROFILE" --project "$PROJECT"

# Espera del agente LXD con timeout global (no sleep fijo, no bucle infinito)
echo "==> Esperando agente LXD (timeout 180s)"
timeout 180 bash -c "until lxc exec $BASE_VM --project $PROJECT -- true 2>/dev/null; do sleep 3; done" \
  || { echo "ERROR: el agente LXD no respondió en 180s" >&2; exit 1; }

# cloud-init status --wait con timeout + validación literal de `status: done` + sin errores
echo "==> Esperando cloud-init (timeout 600s)"
timeout 600 lxc exec "$BASE_VM" --project "$PROJECT" -- cloud-init status --wait \
  || { lxc exec "$BASE_VM" --project "$PROJECT" -- cloud-init status --long >&2; exit 1; }
ci_long="$(lxc exec "$BASE_VM" --project "$PROJECT" -- cloud-init status --long)"
printf '%s\n' "$ci_long" | grep -q "status: done" \
  || { echo "ERROR: cloud-init no terminó en 'status: done'" >&2; printf '%s\n' "$ci_long" >&2; exit 1; }
# Validar que no haya errores de módulos (level=ERROR en cloud-init logs)
if lxc exec "$BASE_VM" --project "$PROJECT" -- cloud-init status --long 2>&1 | grep -qiE 'level=error|fail'; then
  echo "ERROR: cloud-init terminó con errores de módulos" >&2
  lxc exec "$BASE_VM" --project "$PROJECT" -- cloud-init status --long >&2
  exit 1
fi

echo "==> Instalando escritorio MATE + xrdp + servicios"
lxc exec "$BASE_VM" --project "$PROJECT" -- bash <<'EOF'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Preseed debconf: lightdm como DM por defecto + teclado es
echo 'shared/default-x-display-manager select lightdm' | debconf-set-selections
echo 'keyboard-configuration keyboard-configuration/layoutcode select es' | debconf-set-selections

apt-get update
apt-get install -y --no-install-recommends \
  ubuntu-mate-desktop-core lightdm xrdp cloud-init openssh-server \
  sudo curl vim ca-certificates

# MATE como sesión por defecto (no sed sobre startwm.sh)
update-alternatives --set x-session-manager /usr/bin/mate-session 2>/dev/null || true

# Reescritura limpia de startwm.sh (dbus-launch para que MATE arranque bajo xrdp)
cat >/etc/xrdp/startwm.sh <<'WM'
#!/bin/sh
if [ -r /etc/default/locale ]; then . /etc/default/locale; export LANG LANGUAGE; fi
exec dbus-launch --exit-with-session mate-session
WM
chmod +x /etc/xrdp/startwm.sh

systemctl enable xrdp ssh
systemctl set-default graphical.target

# Autologin Modelo A: sin password RDP conocida por el alumno.
# La identidad vive solo en el edge (JWT); la VM no la conoce.
mkdir -p /etc/lightdm/lightdm.conf.d
cat >/etc/lightdm/lightdm.conf.d/99-lab-autologin.conf <<'AL'
[Seat:*]
autologin-user=alumno
autologin-user-timeout=0
AL
EOF

# Smoke test xrdp: valida servicio + sesman + puerto 3389 en escucha
echo "==> Smoke test xrdp"
lxc exec "$BASE_VM" --project "$PROJECT" -- bash -c '
  systemctl start xrdp 2>/dev/null || true
  sleep 2
  systemctl is-active xrdp xrdp-sesman &&
  ss -ltnp | awk "\$4 ~ /:3389$/ {found=1} END {exit !found}"
' || { echo "ERROR: smoke test xrdp falló (xrdp/sesman inactivos o 3389 no escucha)" >&2; exit 1; }

# Limpieza CRÍTICA: las VMs hijas deben poder ejecutar su cloud-init por alumno.
# Sin esto, cloud-init de la base marca "done" y el de alumno se salta módulos.
echo "==> Limpieza cloud-init / machine-id / ssh host keys / apt / journals"
lxc exec "$BASE_VM" --project "$PROJECT" -- bash -c '
  set -e
  cloud-init clean --logs --machine-id
  rm -rf /var/lib/cloud/instances/*
  truncate -s 0 /etc/machine-id
  rm -f /etc/cloud/cloud.cfg.d/99-installer.cfg
  rm -f /etc/ssh/ssh_host_*
  journalctl --rotate 2>/dev/null || true
  journalctl --vacuum-time=1s 2>/dev/null || true
  apt-get clean
  rm -rf /var/lib/apt/lists/*
  dpkg --audit || true
'

echo "==> Apagando VM base"
lxc stop "$BASE_VM" --project "$PROJECT" --timeout=60 \
  || lxc stop "$BASE_VM" --project "$PROJECT" --force
[ "$(lxc list "$BASE_VM" -c s --project "$PROJECT" --format csv)" = "STOPPED" ] \
  || { echo "ERROR: la VM no alcanzó estado STOPPED" >&2; exit 1; }

echo "==> Publicando imagen $IMAGE_ALIAS (+ $IMAGE_VERSIONED)"
lxc publish "$BASE_VM" --project "$PROJECT" \
  --alias "$IMAGE_ALIAS" --alias "$IMAGE_VERSIONED" --force

# Validación final: ambos alias deben resolverse
echo "==> Validación final"
lxc image show "$IMAGE_ALIAS"    --project "$PROJECT" >/dev/null \
  || { echo "ERROR: $IMAGE_ALIAS no se publicó" >&2; exit 1; }
lxc image show "$IMAGE_VERSIONED" --project "$PROJECT" >/dev/null \
  || { echo "ERROR: $IMAGE_VERSIONED no se publicó" >&2; exit 1; }

echo "==> OK: imagen base publicada"
echo "    alias estable   : $IMAGE_ALIAS"
echo "    alias versionado: $IMAGE_VERSIONED"