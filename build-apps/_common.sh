#!/usr/bin/env bash
# FASE 6.3 — Helpers compartidos por los builders de apps stateless.
# Centraliza IMAGE_SOURCE (regla triple de fingerprints) + funciones idempotentes.
# Source desde cada build-app-<nombre>.sh:  source "$(dirname "$0")/_common.sh"

set -Eeuo pipefail

# Regla triple: si cambias de release, actualiza fingerprints en:
#   1. server-setup-lxd.sh
#   2. build-lab-vm-base-mate.sh (IMAGE_SOURCE)
#   3. build-apps/_common.sh (IMAGE_SOURCE aquí)
PROJECT="labs"
PROFILE="stateless"
IMAGE_SOURCE="local:ubuntu-22.04-container"

# CRLF guard
if grep -q $'\r' "$0"; then echo "CRLF detectado: dos2unix $0" >&2; exit 1; fi

# Precheck de alias: SKIP si existe (rc=10), --force para reconstruir.
precheck_alias() {
  local alias="$1"
  if lxc image show "$alias" --project "$PROJECT" >/dev/null 2>&1; then
    if [ "${1:-}" != "--force" ] && [ "${FORCE:-0}" != "1" ]; then
      echo "SKIP: $alias ya existe. Use --force para reconstruir."
      exit 10
    fi
    lxc image delete "$alias" --project "$PROJECT" 2>/dev/null || true
  fi
}

# Purgar alias versionados previos del mismo prefijo (evita acumulación).
purge_versioned_aliases() {
  local prefix="$1"
  for a in $(lxc image list --project "$PROJECT" --format csv -c a 2>/dev/null | grep "^${prefix}-v[0-9]" || true); do
    lxc image delete "$a" --project "$PROJECT" 2>/dev/null || true
  done
}

# Esperar agente LXD en contenedor (timeout 120s).
wait_agent() {
  local name="$1"
  timeout 120 bash -c "until lxc exec $name --project $PROJECT -- true 2>/dev/null; do sleep 2; done" \
    || { echo "ERROR: agente LXD no respondió en 120s para $name" >&2; exit 1; }
}

# Esperar cloud-init status --wait + validar status: done.
wait_cloud_init() {
  local name="$1"
  timeout 300 lxc exec "$name" --project "$PROJECT" -- cloud-init status --wait \
    || { lxc exec "$name" --project "$PROJECT" -- cloud-init status --long >&2; exit 1; }
  lxc exec "$name" --project "$PROJECT" -- cloud-init status --long | grep -q "status: done" \
    || { echo "ERROR: cloud-init no terminó en done para $name" >&2; exit 1; }
}

# Limpieza completa para que hijas ejecuten su cloud-init.
clean_for_publish() {
  local name="$1"
  lxc exec "$name" --project "$PROJECT" -- bash -c '
    set -euo pipefail
    cloud-init clean --logs --machine-id 2>/dev/null || true
    rm -rf /var/lib/cloud/instances/* 2>/dev/null || true
    truncate -s 0 /etc/machine-id 2>/dev/null || true
    rm -f /etc/cloud/cloud.cfg.d/99-installer.cfg 2>/dev/null || true
    rm -f /etc/ssh/ssh_host_* 2>/dev/null || true
    journalctl --rotate 2>/dev/null || true
    journalctl --vacuum-time=1s 2>/dev/null || true
    apt-get clean 2>/dev/null || true
    rm -rf /var/lib/apt/lists/* 2>/dev/null || true
    dpkg --audit || true
  '
}

# Stop + validar STOPPED.
stop_and_validate() {
  local name="$1"
  lxc stop "$name" --project "$PROJECT" --timeout=30 \
    || lxc stop "$name" --project "$PROJECT" --force
  [ "$(lxc list "$name" -c s --project "$PROJECT" --format csv)" = "STOPPED" ] \
    || { echo "ERROR: contenedor $name no parado" >&2; exit 1; }
}

# Publish alias dual (estable + versionado) + validar.
publish_app() {
  local name="$1"; local alias="$2"
  local versioned="${alias}-v$(date +%Y%m%d)"
  purge_versioned_aliases "$alias"
  lxc publish "$name" --project "$PROJECT" \
    --alias "$alias" --alias "$versioned" --force
  lxc image set "$alias" --project "$PROJECT" auto_update=false 2>/dev/null || true
  lxc image show "$alias"     --project "$PROJECT" >/dev/null \
    || { echo "ERROR: $alias no publicada" >&2; exit 1; }
  lxc image show "$versioned" --project "$PROJECT" >/dev/null \
    || { echo "ERROR: $versioned no publicada" >&2; exit 1; }
  echo "OK: $alias (+ $versioned) publicada en $PROJECT"
}