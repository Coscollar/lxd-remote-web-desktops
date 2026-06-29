#!/usr/bin/env bash
# uninstall-all.sh — Elimina todo rastro del proyecto del servidor.
#
# Uso:
#   sudo bash uninstall-all.sh [--yes] [--purge-lxd] [--domain=lab.example.com]
#
# Flags:
#   --yes            No pedir confirmación (para uso desde install-all.sh).
#   --purge-lxd      DESTRUCTIVO: elimina pools, redes, perfiles y proyectos LXD.
#                    No desinstala el snap LXD.
#   --domain=DOM     Dominio para borrar el cert de certbot.
#
# Cada paso es tolerante a "ya no existe": no aborta si algo falta.
set -Eeuo pipefail

if grep -q $'\r' "$0"; then
  echo "ERROR: CRLF detectado en $0. Ejecuta: sudo dos2unix $0" >&2
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: ejecuta con sudo: sudo bash $0" >&2
  exit 1
fi

# --- Parse args ---
YES=false
PURGE_LXD=false
DOMAIN=""

for arg in "$@"; do
  case "$arg" in
    --yes)         YES=true ;;
    --purge-lxd)   PURGE_LXD=true ;;
    --domain=*)    DOMAIN="${arg#--domain=}" ;;
    --help|-h)     sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Argumento desconocido: $arg" >&2; exit 1 ;;
  esac
done

# --- Confirmación interactiva ---
if [ "$YES" = "false" ]; then
  echo "============================================================"
  echo "  DESINSTALACIÓN DEL PROYECTO LXD REMOTE WEB DESKTOPS"
  echo "============================================================"
  echo "Esto eliminará:"
  echo "  - Servicios systemd (provision, provision-reap)"
  echo "  - Usuario provision + /opt/provision + /etc/provision + /var/lib/provision"
  echo "  - Contenedores Docker (guacd, guacamole, mysql) + volúmenes"
  echo "  - Site Nginx + log_format"
  echo "  - Reglas iptables del proyecto"
  echo "  - Instancias e imágenes LXD del proyecto labs"
  if [ "$PURGE_LXD" = "true" ]; then
    echo "  - (--purge-lxd) Pools ZFS, redes, perfiles y proyectos LXD"
  fi
  if [ -n "$DOMAIN" ]; then
    echo "  - Cert certbot para $DOMAIN"
  fi
  echo "NO se desinstalará: snap LXD, nginx, docker, certbot, paquetes del sistema."
  echo "============================================================"
  read -p "¿Continuar? [y/N] " -n1 -r
  echo
  [[ ! $REPLY =~ ^[Yy]$ ]] && { echo "Cancelado."; exit 0; }
fi

echo "==> Iniciando desinstalación..."

# 1. Servicios systemd
echo "--- 1. Servicios systemd ---"
for svc in provision.service provision-reap.service provision-reap.timer \
           provision-reap-apps.service provision-reap-apps.timer; do
  systemctl stop "$svc" 2>/dev/null || true
  systemctl disable "$svc" 2>/dev/null || true
  rm -f "/etc/systemd/system/$svc"
done
systemctl daemon-reload 2>/dev/null || true
echo "OK"

# 2. Instancias LXD del proyecto labs
echo "--- 2. Instancias LXD (proyecto labs) ---"
if command -v lxc >/dev/null 2>&1; then
  lxc project switch default 2>/dev/null || true
  for inst in $(lxc list --project labs --format csv -c n 2>/dev/null); do
    echo "  borrando instancia: $inst"
    lxc delete -f "$inst" --project labs 2>/dev/null || true
  done
  echo "OK"
else
  echo "SKIP: lxc no disponible"
fi

# 3. Imágenes LXD del proyecto labs
echo "--- 3. Imágenes LXD (proyecto labs) ---"
if command -v lxc >/dev/null 2>&1; then
  for img in $(lxc image list --project labs --format csv -c a 2>/dev/null); do
    [ -z "$img" ] && continue
    echo "  borrando imagen (labs): $img"
    lxc image delete "$img" --project labs 2>/dev/null || true
  done
  echo "OK"
fi

# 4. Imágenes LXD del proyecto default
echo "--- 4. Imágenes LXD (proyecto default) ---"
if command -v lxc >/dev/null 2>&1; then
  for img in lab-vm-base ubuntu-22.04-vm ubuntu-22.04-container; do
    lxc image delete "$img" 2>/dev/null || true
  done
  # Alias versionados lab-vm-base-v*
  for alias in $(lxc image list local: --format csv -c a 2>/dev/null | grep '^lab-vm-base-v' 2>/dev/null || true); do
    lxc image delete "$alias" 2>/dev/null || true
  done
  echo "OK"
fi

# 5. --purge-lxd: pools, redes, perfiles, proyectos
if [ "$PURGE_LXD" = "true" ]; then
  echo "--- 5. --purge-lxd: pools, redes, perfiles, proyectos ---"
  if command -v lxc >/dev/null 2>&1; then
    # Perfiles en labs
    for prof in stateless persistent admin; do
      lxc profile delete "$prof" --project labs 2>/dev/null || true
    done
    # Redes en labs
    for net in lab-stateless lab-persistent admin-net; do
      lxc network delete "$net" --project labs 2>/dev/null || true
    done
    # Proyectos (switch a default antes de borrar)
    lxc project switch default 2>/dev/null || true
    for proj in labs test; do
      lxc project delete "$proj" 2>/dev/null || true
    done
    # Perfiles en default
    for prof in stateless persistent admin; do
      lxc profile delete "$prof" 2>/dev/null || true
    done
    # Redes en default
    for net in lab-stateless lab-persistent admin-net; do
      lxc network delete "$net" 2>/dev/null || true
    done
    # Pools ZFS
    for pool in stateless-pool persistent-pool; do
      lxc storage delete "$pool" 2>/dev/null || true
    done
    # lxdbr0 residual
    lxc network delete lxdbr0 2>/dev/null || true
    echo "OK"
  else
    echo "SKIP: lxc no disponible"
  fi
fi

# 6. Stack Docker Guacamole
echo "--- 6. Stack Docker Guacamole ---"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/guacamole/docker-compose.yml" ]; then
  docker compose -f "$SCRIPT_DIR/guacamole/docker-compose.yml" down -v 2>/dev/null || true
fi
for c in guacd guacamole mysql guacamole-guacd guacamole-guacamole guacamole-mysql; do
  docker rm -f "$c" 2>/dev/null || true
done
for v in guacamole_mysql_data mysql_data; do
  docker volume rm "$v" 2>/dev/null || true
done
rm -f "$SCRIPT_DIR/guacamole/.schema-imported" 2>/dev/null || true
rm -f "$SCRIPT_DIR/guacamole/.env" 2>/dev/null || true
echo "OK"

# 7. Site Nginx
echo "--- 7. Nginx ---"
rm -f /etc/nginx/sites-enabled/lab.conf 2>/dev/null || true
rm -f /etc/nginx/sites-available/lab.conf 2>/dev/null || true
rm -f /etc/nginx/conf.d/lab-log.conf 2>/dev/null || true
# Restaurar default de Debian si se quitó
if [ ! -L /etc/nginx/sites-enabled/default ] && [ -f /etc/nginx/sites-available/default ]; then
  ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default 2>/dev/null || true
fi
nginx -t 2>/dev/null && nginx -s reload 2>/dev/null || true
echo "OK"

# 8. Reglas iptables
echo "--- 8. iptables ---"
while iptables -D FORWARD -i lab-persistent -o lab-persistent -j DROP 2>/dev/null; do :; done
while iptables -D FORWARD -s 10.50.20.1 -d 10.50.20.0/24 -p tcp --dport 3389 -j ACCEPT 2>/dev/null; do :; done
# OUTPUT: parsear y borrar reglas con 10.50.20.0/24 dport 3389
iptables -S OUTPUT 2>/dev/null | grep '10.50.20.0/24.*3389' | while read -r rule; do
  del_rule="$(echo "$rule" | sed 's/^-A /-D /')"
  # shellcheck disable=SC2086
  iptables $del_rule 2>/dev/null || true
done
# FASE 6: borrar reglas iptables-apps (lab-stateless)
while iptables -D FORWARD -i lab-stateless -o lab-stateless -j DROP 2>/dev/null; do :; done
while iptables -D FORWARD -i lab-stateless -o lab-persistent -j DROP 2>/dev/null; do :; done
while iptables -D FORWARD -i lab-persistent -o lab-stateless -j DROP 2>/dev/null; do :; done
while iptables -D FORWARD -s 10.50.10.1 -d 10.50.10.0/23 -p tcp --dport 3000:9999 -j ACCEPT 2>/dev/null; do :; done
while iptables -D FORWARD -s 10.50.10.0/23 -d 10.50.10.1 -p tcp --dport 8000 -j ACCEPT 2>/dev/null; do :; done
# FASE 6.0: borrar allowlist 8000
while iptables -D INPUT -p tcp --dport 8000 -s 127.0.0.1 -j ACCEPT 2>/dev/null; do :; done
while iptables -D INPUT -p tcp --dport 8000 -s 10.50.10.0/23 -j ACCEPT 2>/dev/null; do :; done
while iptables -D INPUT -p tcp --dport 8000 -s 10.50.20.0/24 -j ACCEPT 2>/dev/null; do :; done
while iptables -D INPUT -p tcp --dport 8000 -j DROP 2>/dev/null; do :; done
netfilter-persistent save 2>/dev/null || true
echo "OK"

# 9. Certs de certbot
echo "--- 9. certbot ---"
if [ -n "$DOMAIN" ]; then
  certbot delete --cert-name "$DOMAIN" --non-interactive 2>/dev/null || true
  echo "OK: cert $DOMAIN eliminado"
else
  echo "SKIP: --domain no provisto"
fi

# 10. Usuario provision + directorios
echo "--- 10. Usuario provision + directorios ---"
pkill -u provision 2>/dev/null || true
userdel provision 2>/dev/null || true
rm -rf /opt/provision 2>/dev/null || true
rm -rf /etc/provision 2>/dev/null || true
rm -rf /var/lib/provision 2>/dev/null || true
echo "OK"

# 11. Flag preseed
echo "--- 11. Flag preseed ---"
rm -f /var/lib/lab/.preseed-applied 2>/dev/null || true
rmdir /var/lib/lab 2>/dev/null || true
echo "OK"

# Resumen
echo ""
echo "============================================================"
echo "  DESINSTALACIÓN COMPLETADA"
echo "============================================================"
echo "Eliminado:"
echo "  ✓ Servicios systemd (provision, provision-reap, provision-reap-apps)"
echo "  ✓ Instancias e imágenes LXD (proyecto labs)"
if [ "$PURGE_LXD" = "true" ]; then
  echo "  ✓ Pools, redes, perfiles, proyectos LXD (--purge-lxd)"
fi
echo "  ✓ Stack Docker Guacamole (contenedores + volúmenes)"
echo "  ✓ Site Nginx + log_format"
echo "  ✓ Reglas iptables del proyecto"
if [ -n "$DOMAIN" ]; then
  echo "  ✓ Cert certbot ($DOMAIN)"
fi
echo "  ✓ Usuario provision + /opt/provision + /etc/provision + /var/lib/provision"
echo "  ✓ Flag preseed"
echo ""
echo "NO eliminado (paquetes del sistema):"
echo "  - snap LXD, nginx, docker, certbot, iptables-persistent, sqlite3"
echo "  - El repo en disco"
echo ""
echo "Para desinstalar paquetes del sistema manualmente:"
echo "  sudo apt remove --purge nginx certbot docker.io iptables-persistent"
echo "  sudo snap remove lxd   # ⚠️ elimina LXD completamente"
