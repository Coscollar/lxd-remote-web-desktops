#!/usr/bin/env bash
# FASE 4 — Aislamiento inter-VM en lab-persistent + acceso host→VM:3389.
# Regla de oro: guacd SIEMPRE intermedio. 3389 no se expone al navegador.
# DROP todo el tráfico entre VMs (no solo 3389) para evitar lateral movement.
# Idempotente: verifica con iptables -C antes de añadir.
set -euo pipefail

BRIDGE="lab-persistent"
VM_NET="10.50.20.0/24"
HOST_IP="10.50.20.1"

# 1. DROP inter-VM (cualquier puerto, no solo 3389)
if ! sudo iptables -C FORWARD -i "$BRIDGE" -o "$BRIDGE" -j DROP 2>/dev/null; then
  sudo iptables -A FORWARD -i "$BRIDGE" -o "$BRIDGE" -j DROP
  echo "[iptables-lab] DROP inter-VM añadido"
else
  echo "[iptables-lab] DROP inter-VM ya existe"
fi

# 2. ACCEPT host (10.50.20.1 en bridge) → VMs:3389 (guacd alcanza xrdp)
if ! sudo iptables -C FORWARD -s "$HOST_IP" -d "$VM_NET" -p tcp --dport 3389 -j ACCEPT 2>/dev/null; then
  sudo iptables -I FORWARD -s "$HOST_IP" -d "$VM_NET" -p tcp --dport 3389 -j ACCEPT
  echo "[iptables-lab] ACCEPT host→VM:3389 añadido"
else
  echo "[iptables-lab] ACCEPT host→VM:3389 ya existe"
fi

# 3. Defensa en profundidad: restringir OUTPUT al UID de guacd (si corre como host process)
#    En Docker network_mode: host, guacd corre con su UID dentro del contenedor.
#    Ajustar GUACD_UID según el despliegue (ver docs/DEPLOY.md, Anexo B).
GUACD_UID="${GUACD_UID:-1000}"
if ! sudo iptables -C OUTPUT -m owner --uid-owner "$GUACD_UID" -d "$VM_NET" -p tcp --dport 3389 -j ACCEPT 2>/dev/null; then
  sudo iptables -I OUTPUT -m owner --uid-owner "$GUACD_UID" -d "$VM_NET" -p tcp --dport 3389 -j ACCEPT
  echo "[iptables-lab] ACCEPT OUTPUT guacd UID=$GUACD_UID añadido"
else
  echo "[iptables-lab] ACCEPT OUTPUT guacd ya existe"
fi

# 4. Persistir reglas
if command -v netfilter-persistent >/dev/null 2>&1; then
  sudo netfilter-persistent save
  echo "[iptables-lab] reglas persistidas"
else
  echo "[iptables-lab] WARN: netfilter-persistent no instalado; reglas no persisten tras reboot"
fi

# 5. Validación: 3389 NO escucha en el host
if sudo ss -tlnp | grep -q ':3389'; then
  echo "[iptables-lab] ERROR: 3389 escucha en el host (no debería)" >&2
  exit 1
fi
echo "[iptables-lab] OK — 3389 no expuesto en el host"