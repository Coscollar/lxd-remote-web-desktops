#!/usr/bin/env bash
set -e

echo "==> Verificando requisitos del sistema..."

echo "   [1/6] Verificando virtualización hardware (KVM)..."
if ! egrep -q '(vmx|svm)' /proc/cpuinfo 2>/dev/null; then
  echo "ERROR: La CPU no soporta virtualización hardware (Intel VT-x / AMD-V)"
  echo "       Necesario para crear VMs."
  exit 1
fi
if [ ! -c /dev/kvm ]; then
  echo "ERROR: /dev/kvm no disponible"
  echo "       Habilita virtualización anidada en el hipervisor o BIOS"
  exit 1
fi
echo "       OK - KVM disponible"

echo "   [2/6] Verificando soporte ZFS..."
if ! modprobe zfs 2>/dev/null; then
  echo "ERROR: No se pudo cargar el módulo ZFS"
  echo "       Ejecuta: sudo apt install zfsutils-linux"
  exit 1
fi
echo "       OK - ZFS disponible"

echo "   [3/6] Verificando RAM (mínimo 8GB)..."
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
TOTAL_RAM_GB=$((TOTAL_RAM_KB / 1024 / 1024))
if [ "$TOTAL_RAM_GB" -lt 8 ]; then
  echo "WARNING: RAM detectada: ${TOTAL_RAM_GB}GB (recomendado: 8GB+)"
  echo "         El sistema puede funcionar, pero con limitaciones."
fi
echo "       OK - RAM: ${TOTAL_RAM_GB}GB"

echo "   [4/6] Verificando espacio en disco (mínimo 100GB libres)..."
FREE_DISK_KB=$(df -k / | tail -1 | awk '{print $4}')
FREE_DISK_GB=$((FREE_DISK_KB / 1024 / 1024))
if [ "$FREE_DISK_GB" -lt 100 ]; then
  echo "WARNING: Espacio libre: ${FREE_DISK_GB}GB (recomendado: 100GB+)"
  echo "         Puede haber limitaciones para pools de almacenamiento."
fi
echo "       OK - Espacio libre: ${FREE_DISK_GB}GB"

echo "   [5/6] Verificando conectividad a internet..."
if ! ping -c 1 -W 5 cloud-images.ubuntu.com >/dev/null 2>&1; then
  echo "ERROR: No hay conexión a internet"
  echo "       Necesario para descargar imágenes de Ubuntu"
  exit 1
fi
echo "       OK - Conexión disponible"

echo "   [6/6] Verificando usuario root/sudo..."
if ! sudo -n true 2>/dev/null; then
  echo "ERROR: El usuario actual no tiene permisos sudo"
  exit 1
fi
echo "       OK - Permisos sudo disponibles"

echo "==> Instalando LXD vía snap"
if ! command -v lxd >/dev/null 2>&1; then
  sudo snap install lxd
else
  echo "LXD ya está instalado"
fi

echo "==> Asegurando que el daemon LXD esté corriendo"
sudo systemctl enable --now snap.lxd.daemon 2>/dev/null || sudo snap start lxd 2>/dev/null || true

echo "==> Esperando a que LXD esté listo"
sudo lxd waitready --timeout=300

echo "==> Inicializando LXD desde preseed"
if [ -f lxd-preseed.yaml ]; then
  sudo lxd init --preseed < ./lxd-preseed.yaml
else
  echo "ERROR: No se encontró lxd-preseed.yaml"
  exit 1
fi

echo "==> Añadiendo remote ubuntu-releases"
if ! lxc remote list 2>/dev/null | grep -q ubuntu-releases; then
  lxc remote add ubuntu-releases https://cloud-images.ubuntu.com/releases --protocol simplestreams
else
  echo "Remote ubuntu-releases ya existe"
fi

echo "==> Listando imágenes Ubuntu 22.04 x86_64"
echo "lxc image list ubuntu-releases: | grep 22.04 | grep x86_64 || true"

echo "==> Copiando imágenes locales"
if ! lxc image list local: 2>/dev/null | grep -q ubuntu-22.04-vm; then
  lxc image copy ubuntu-releases:cf181d732f32 local: --alias ubuntu-22.04-vm
fi

if ! lxc image list local: 2>/dev/null | grep -q ubuntu-22.04-container; then
  lxc image copy ubuntu-releases:a6d2f7222476 local: --alias ubuntu-22.04-container
fi

echo "==> Verificando grupo lxd para el usuario $USER"
if ! getent group lxd | grep -q "$USER"; then
  echo "Añadiendo usuario $USER al grupo lxd"
  sudo usermod -aG lxd "$USER"
else
  echo "El usuario ya pertenece al grupo lxd"
fi

echo "==> Creando imagen base VM con escritorio MATE"
./build-lab-vm-base-mate.sh

echo "==> Validaciones finales"
lxc storage list
lxc network list
lxc profile list
lxc project list
lxc image list local

echo "Configuración de LXD completada"
