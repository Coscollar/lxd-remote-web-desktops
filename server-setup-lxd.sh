#!/usr/bin/env bash
# FASE 0 — LXD server setup (idempotent, fail-closed preseed).
# Usage: sudo bash 1-server-setup-lxd.sh [--force-preseed]
set -Eeuo pipefail

# CRLF guard: scripts edited from Windows must be dos2unix'd first.
if grep -q $'\r' "$0"; then
  echo "ERROR: CRLF detectado en $0. Ejecuta: sudo apt install dos2unix -y && sudo dos2unix $0"
  exit 1
fi

PRESEED_FLAG="/var/lib/lab/.preseed-applied"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# 0.2 Group membership: validate lxd group is ACTIVE for this session.
#     newgrp in a subshell does not persist; abort and ask for re-login.
# ---------------------------------------------------------------------------
if ! id -nG | tr ' ' '\n' | grep -qx lxd; then
  echo "==> Usuario '$USER' sin grupo lxd activo en esta sesión."
  if ! getent group lxd >/dev/null 2>&1; then
    echo "ERROR: el grupo 'lxd' no existe. ¿LXD instalado?" >&2
    exit 1
  fi
  sudo usermod -aG lxd "$USER"
  echo "Re-login requerido para activar el grupo lxd. Vuelve a ejecutar este script tras reiniciar sesión."
  exit 100
fi

# ---------------------------------------------------------------------------
# Install LXD via snap (idempotent).
# ---------------------------------------------------------------------------
echo "==> Instalando LXD vía snap"
if ! command -v lxd >/dev/null 2>&1; then
  if ! command -v snap >/dev/null 2>&1; then
    echo "ERROR: snapd no está instalado. Ejecuta install-all.sh (lo instala en el preflight)" >&2
    echo "       o instala manualmente: sudo apt-get install -y snapd" >&2
    exit 1
  fi
  # Esperar a que snapd esté sembrado (uso standalone sin install-all.sh).
  if ! sudo timeout 300 snap wait system seed.loaded; then
    echo "ERROR: snapd no terminó de sembrarse en 300s (snap wait system seed.loaded)" >&2
    exit 1
  fi
  sudo snap install lxd
else
  echo "LXD ya está instalado"
fi

# ---------------------------------------------------------------------------
# Add ubuntu-releases simplestreams remote (idempotent, exact match).
# ---------------------------------------------------------------------------
echo "==> Añadiendo remote ubuntu-releases"
if ! lxc remote list --format csv --columns n 2>/dev/null | grep -qx ubuntu-releases; then
  lxc remote add ubuntu-releases https://cloud-images.ubuntu.com/releases --protocol simplestreams
else
  echo "Remote ubuntu-releases ya existe"
fi

# ---------------------------------------------------------------------------
# 0.3 Preseed guardian (fail-closed). Destructive: only loads on first run
#     (flag absent) or with explicit --force-preseed for intentional recreate.
# ---------------------------------------------------------------------------
echo "==> Evaluando preseed LXD"
if [ ! -f "$PRESEED_FLAG" ] || [ "${1:-}" = "--force-preseed" ]; then
  if [ ! -f "$SCRIPT_DIR/lxd-preseed.yaml" ]; then
    echo "ERROR: no se encontró lxd-preseed.yaml en $SCRIPT_DIR" >&2
    exit 1
  fi
  echo "==> Aplicando preseed (DESTRUCTIVO: machaca config del daemon)"
  sudo lxd init --preseed < "$SCRIPT_DIR/lxd-preseed.yaml"
  sudo mkdir -p /var/lib/lab
  sudo touch "$PRESEED_FLAG"
  echo "==> Preseed aplicado. Flag $PRESEED_FLAG creado."
else
  echo "==> Preseed ya aplicado. Use --force-preseed para recreación intencionada."
fi

# Ensure we operate in the default project for the next propagation steps.
if ! lxc project switch default >/dev/null 2>&1; then
  echo "ERROR: no se pudo cambiar al proyecto default" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 0.4 NO storage create here. Pools come from the preseed (single source of
#     truth). We only verify they exist.
# ---------------------------------------------------------------------------
echo "==> Verificando pools ZFS"
for pool in stateless-pool persistent-pool; do
  if ! lxc storage list --format csv --columns n 2>/dev/null | grep -qx "$pool"; then
    echo "ERROR: pool '$pool' no existe tras preseed. ¿Preseed cargado?" >&2
    exit 1
  fi
  echo "Pool $pool OK"
done

# ---------------------------------------------------------------------------
# Copy images to default project (idempotent, exact alias match).
# Fingerprints hardcoded for Ubuntu 22.04 (see image-fingerprints skill).
#   cf181d732f32 -> ubuntu-22.04-vm
#   a6d2f7222476 -> ubuntu-22.04-container
# ---------------------------------------------------------------------------
echo "==> Copiando imágenes a proyecto default"
for pair in "cf181d732f32:ubuntu-22.04-vm" "a6d2f7222476:ubuntu-22.04-container"; do
  fp="${pair%%:*}"; alias="${pair##*:}"
  if ! lxc image list local: --format csv --columns a 2>/dev/null | grep -qx "$alias"; then
    lxc image copy "ubuntu-releases:$fp" local: --alias "$alias"
  else
    echo "Imagen $alias ya en default"
  fi
done

# ---------------------------------------------------------------------------
# 0.6 Copy images to labs project (catalog isolated by features.images=true).
#     Builder and provision-api operate in labs; they cannot see default images.
# ---------------------------------------------------------------------------
echo "==> Copiando imágenes a proyecto labs"
for pair in "cf181d732f32:ubuntu-22.04-vm" "a6d2f7222476:ubuntu-22.04-container"; do
  fp="${pair%%:*}"; alias="${pair##*:}"
  if ! lxc image list local: --project labs --format csv --columns a 2>/dev/null | grep -qx "$alias"; then
    lxc image copy "local:$fp" local: --alias "$alias" --project labs
  else
    echo "Imagen $alias ya en labs"
  fi
done

# ---------------------------------------------------------------------------
# 0.5 Propagate profiles to labs project (features.profiles=true isolates
#     catalogs). Idempotent via exact name match.
# ---------------------------------------------------------------------------
echo "==> Propagando perfiles a labs"
for prof in stateless persistent admin; do
  if ! lxc profile list --project labs --format csv --columns n 2>/dev/null | grep -qx "$prof"; then
    lxc profile copy "$prof" "$prof" --project default --target-project labs
  else
    echo "Perfil $prof ya en labs"
  fi
done

# ---------------------------------------------------------------------------
# 0.5 Propagate networks to labs project (features.networks=true isolates).
#     LXD has no `network copy`; recreate with the same config extracted from
#     the default-project network via `lxc network show`.
# ---------------------------------------------------------------------------
echo "==> Propagando redes a labs"
net_config_args() {
  # Emit `key=value` lines for each config key of the network in default project.
  lxc network show "$1" --project default | awk '
    /^config:/ { inconf=1; next }
    /^[a-zA-Z]/ && inconf { inconf=0 }
    inconf && /^[[:space:]]+[a-zA-Z0-9._-]+:/ {
      line=$0
      gsub(/^[[:space:]]+/, "", line)
      idx=index(line, ":")
      key=substr(line, 1, idx-1)
      val=substr(line, idx+2)
      gsub(/^"|"$/, "", val)
      print key"="val
    }
  '
}

for net in lab-stateless lab-persistent admin-net; do
  if ! lxc network list --project labs --format csv --columns n 2>/dev/null | grep -qx "$net"; then
    mapfile -t cfg < <(net_config_args "$net")
    if [ "${#cfg[@]}" -eq 0 ]; then
      echo "ERROR: no se pudo leer config de red $net (default)" >&2
      exit 1
    fi
    lxc network create "$net" --project labs "${cfg[@]}"
  else
    echo "Red $net ya en labs"
  fi
done

# ---------------------------------------------------------------------------
# 0.7 Harden persistent profile in BOTH projects (idempotent sets).
#     boot.autostart=false, security.devlxd=false, security.secureboot=true
# ---------------------------------------------------------------------------
echo "==> Endureciendo perfil persistent (default + labs)"
for proj in default labs; do
  lxc profile set persistent --project "$proj" boot.autostart=false
  lxc profile set persistent --project "$proj" security.devlxd=false
  lxc profile set persistent --project "$proj" security.secureboot=true
  echo "persistent endurecido en $proj"
done

# Endurecer stateless (contenedores de alumnos: devlxd=false evita fuga del host)
for proj in default labs; do
  lxc profile set stateless --project "$proj" security.devlxd=false
  lxc profile set stateless --project "$proj" security.nesting=false
  echo "stateless endurecido en $proj"
done

# ---------------------------------------------------------------------------
# 0.8 Move admin profile root device to stateless-pool in BOTH projects
#     (convention: no separate admin-pool). Idempotent device set.
# ---------------------------------------------------------------------------
echo "==> Moviendo admin a stateless-pool (default + labs)"
lxc profile device set admin root pool stateless-pool
lxc profile device set admin root pool stateless-pool --project labs

# ---------------------------------------------------------------------------
# 0.9 Remove trust_password and https_address TCP exposure (security).
#     Daemon config requires root -> sudo. Tolerant if already unset.
# ---------------------------------------------------------------------------
echo "==> Eliminando core.trust_password y core.https_address"
sudo lxc config unset core.trust_password 2>/dev/null || true
sudo lxc config unset core.https_address 2>/dev/null || true

# ---------------------------------------------------------------------------
# 0.12 Cleanup residual lxdbr0 if unused (USED BY == 0).
# ---------------------------------------------------------------------------
echo "==> Limpieza lxdbr0 residual"
if lxc network list --format csv --columns n,u 2>/dev/null | grep -qE '^lxdbr0,0$'; then
  lxc network delete lxdbr0 2>/dev/null || true
  echo "lxdbr0 eliminado (sin instancias)"
else
  echo "lxdbr0 ausente o en uso; se conserva"
fi

# ---------------------------------------------------------------------------
# Build the lab VM base image (operates in labs project).
# ---------------------------------------------------------------------------
echo "==> Construyendo imagen base VM (lab-vm-base)"
set +e
"$SCRIPT_DIR/build-lab-vm-base-mate.sh"
builder_rc=$?
set -e
if [ "$builder_rc" -ne 0 ] && [ "$builder_rc" -ne 10 ]; then
  echo "ERROR: build-lab-vm-base-mate.sh falló con rc=$builder_rc" >&2
  exit "$builder_rc"
fi
[ "$builder_rc" -eq 10 ] && echo "(imagen base ya existía — SKIP)"

# 0.12 Return to default project so final validations list default catalogs.
lxc project switch default >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# Final validations.
# ---------------------------------------------------------------------------
echo "==> Validaciones finales"
echo "--- storage ---"; lxc storage list
echo "--- networks ---"; lxc network list
echo "--- profiles ---"; lxc profile list
echo "--- projects ---"; lxc project list
echo "--- images (default) ---"; lxc image list local
echo "--- images (labs) ---"; lxc image list local --project labs
echo "--- daemon config (trust_password/https_address must be empty) ---"
daemon_cfg="$(lxc config show 2>/dev/null)" || { echo "ERROR: lxc config show falló — no se puede validar"; exit 1; }
if printf '%s' "$daemon_cfg" | grep -qE 'trust_password|https_address'; then
  echo "WARN: trust_password o https_address siguen presentes (no se muestran por seguridad)"
else
  echo "(limpio: sin trust_password ni https_address)"
fi

echo "==> Configuración de LXD completada (FASE 0)"