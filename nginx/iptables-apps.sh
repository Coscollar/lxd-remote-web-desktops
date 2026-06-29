#!/usr/bin/env bash
# FASE 6.3 — Aislamiento de apps stateless en lab-stateless.
# DROP inter-app + DROP app↔VM + ACCEPT host→app:HTTP + ACCEPT app→host:8000.
# Idempotente: verifica con iptables -C antes de añadir.
# Regla de oro: las apps NO pasan por guacd (HTTP directo). 3389/5900 no aplican.
set -euo pipefail

BRIDGE_APP="lab-stateless"
BRIDGE_VM="lab-persistent"
APP_NET="10.50.10.0/23"
VM_NET="10.50.20.0/24"
HOST_APP_IP="10.50.10.1"
APP_PORT_RANGE="3000:9999"
PROVISION_UID="$(id -u provision 2>/dev/null || echo 1000)"

add_rule() {
  # $1 = tabla, $2 = -I|-A, resto = regla
  local pos="$2"; shift 2
  if ! sudo iptables -C "$@" 2>/dev/null; then
    sudo iptables "$pos" "$@"
    echo "[iptables-apps] añadido: $*"
  else
    echo "[iptables-apps] ya existe: $*"
  fi
}

# 1. DROP inter-app (lateral movement prevention)
add_rule FORWARD -A -i "$BRIDGE_APP" -o "$BRIDGE_APP" -j DROP

# 2. DROP app↔VM bidireccional (cross-tenant)
add_rule FORWARD -A -i "$BRIDGE_APP" -o "$BRIDGE_VM" -j DROP
add_rule FORWARD -A -i "$BRIDGE_VM" -o "$BRIDGE_APP" -j DROP

# 3. ACCEPT host→app:HTTP (-I antes de DROP)
add_rule FORWARD -I -s "$HOST_APP_IP" -d "$APP_NET" -p tcp --dport "$APP_PORT_RANGE" -j ACCEPT

# 4. ACCEPT app→host:8000 (heartbeat a provision-api)
add_rule FORWARD -I -s "$APP_NET" -d "$HOST_APP_IP" -p tcp --dport 8000 -j ACCEPT

# 5. Defensa en profundidad: solo UID provision alcanza apps
add_rule OUTPUT -I -m owner --uid-owner "$PROVISION_UID" -d "$APP_NET" -p tcp --dport "$APP_PORT_RANGE" -j ACCEPT

# 6. Persistir
if command -v netfilter-persistent >/dev/null 2>&1; then
  sudo netfilter-persistent save
  echo "[iptables-apps] reglas persistidas"
else
  echo "[iptables-apps] WARN: netfilter-persistent no instalado; reglas no persisten tras reboot"
fi

# 7. Validación: ningún puerto de app escucha en el host
if sudo ss -tlnp | grep -qE ':(3000|8888|8080)\b'; then
  echo "[iptables-apps] ERROR: puerto de app escucha en el host (no debería)" >&2
  exit 1
fi
echo "[iptables-apps] OK — apps aisladas, puertos no expuestos en el host"