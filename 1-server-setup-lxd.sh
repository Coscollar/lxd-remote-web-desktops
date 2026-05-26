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
  echo "       Módulo ZFS no disponible. Instalando zfsutils-linux..."
  sudo apt-get update -qq && sudo apt-get install -y zfsutils-linux
  if ! modprobe zfs 2>/dev/null; then
    echo "ERROR: No se pudo cargar el módulo ZFS incluso tras instalar zfsutils-linux"
    echo "       Prueba: sudo apt install zfsutils-linux y reinicia"
    exit 1
  fi
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

echo "==> Detectando método de acceso a LXD"
if lxc list >/dev/null 2>&1; then
  LXC="lxc"
  echo "       Usando lxc directamente"
else
  LXC="sudo lxc"
  echo "       Usando sudo lxc (acceso directo no disponible)"
fi

echo "==> Limpiando recursos previos para instalación limpia"
# Eliminar instancias existentes que usen nuestros perfiles
for inst in $($LXC list --format csv 2>/dev/null | cut -d, -f1); do
  $LXC delete -f "$inst" 2>/dev/null || true
done

# Eliminar imágenes locales gestionadas
for img in lab-vm-base ubuntu-22.04-vm ubuntu-22.04-container; do
  if $LXC image list local: 2>/dev/null | grep -q "$img"; then
    $LXC image delete "local:$img" 2>/dev/null || true
  fi
done

# Eliminar proyectos gestionados
for proj in labs test; do
  if $LXC project show "$proj" >/dev/null 2>&1; then
    $LXC project delete "$proj" 2>/dev/null || true
  fi
done

# Eliminar perfiles gestionados
for prof in stateless persistent admin; do
  if $LXC profile show "$prof" >/dev/null 2>&1; then
    $LXC profile delete "$prof" 2>/dev/null || true
  fi
done

# Eliminar redes gestionadas
for net in lab-stateless lab-persistent admin-net; do
  if $LXC network show "$net" >/dev/null 2>&1; then
    $LXC network delete "$net" 2>/dev/null || true
  fi
done

# Eliminar storage pools gestionados
for pool in stateless-pool persistent-pool; do
  if $LXC storage show "$pool" >/dev/null 2>&1; then
    $LXC storage delete "$pool" 2>/dev/null || true
  fi
done

echo "==> Inicializando LXD desde preseed"
if [ -f lxd-preseed.yaml ]; then
  sudo lxd init --preseed < ./lxd-preseed.yaml
else
  echo "ERROR: No se encontró lxd-preseed.yaml"
  exit 1
fi

echo "==> Verificando pools de almacenamiento"
for pool in stateless-pool persistent-pool; do
  if ! $LXC storage show "$pool" >/dev/null 2>&1; then
    echo "   Storage pool $pool no se creó desde el preseed. Creándolo..."
    if [ "$pool" = "stateless-pool" ]; then
      $LXC storage create "$pool" zfs size=20GB
    else
      $LXC storage create "$pool" zfs size=40GB
    fi
  fi
done

echo "==> Verificando redes"
for net in lab-stateless lab-persistent admin-net; do
  if ! $LXC network show "$net" >/dev/null 2>&1; then
    echo "   Red $net no se creó desde el preseed. Creándola..."
    case "$net" in
      lab-stateless)
        $LXC network create "$net" --type=bridge ipv4.address=10.50.10.1/24 ipv4.nat=true ipv6.address=none dns.domain=lab.internal dns.mode=managed
        ;;
      lab-persistent)
        $LXC network create "$net" --type=bridge ipv4.address=10.50.20.1/24 ipv4.nat=true ipv6.address=none dns.domain=vm.lab.internal dns.mode=managed
        ;;
      admin-net)
        $LXC network create "$net" --type=bridge ipv4.address=10.50.100.1/24 ipv4.nat=false ipv6.address=none
        ;;
    esac
  fi
done

echo "==> Verificando perfiles"
for pname in stateless persistent admin; do
  if ! $LXC profile show "$pname" >/dev/null 2>&1; then
    echo "   Perfil $pname no existe. Creándolo..."
    $LXC profile create "$pname"
  fi
done

echo "==> Asegurando configuración correcta de perfiles"

# Perfil stateless
$LXC profile set stateless limits.cpu 2 2>/dev/null || true
$LXC profile set stateless limits.memory 2GB 2>/dev/null || true
$LXC profile device add stateless root disk pool=stateless-pool path=/ 2>/dev/null || true
$LXC profile device add stateless eth0 nic network=lab-stateless name=eth0 2>/dev/null || true

# Perfil persistent
$LXC profile set persistent limits.cpu 4 2>/dev/null || true
$LXC profile set persistent limits.memory 4GB 2>/dev/null || true
$LXC profile device add persistent root disk pool=persistent-pool path=/ 2>/dev/null || true
$LXC profile device add persistent eth0 nic network=lab-persistent name=eth0 2>/dev/null || true

# Perfil admin
$LXC profile set admin limits.cpu 2 2>/dev/null || true
$LXC profile set admin limits.memory 2GB 2>/dev/null || true
$LXC profile device add admin root disk pool=persistent-pool path=/ 2>/dev/null || true
$LXC profile device add admin eth0 nic network=admin-net name=eth0 2>/dev/null || true

echo "==> Añadiendo remote ubuntu-releases"
if ! $LXC remote list 2>/dev/null | grep -q ubuntu-releases; then
  $LXC remote add ubuntu-releases https://cloud-images.ubuntu.com/releases --protocol simplestreams
else
  echo "Remote ubuntu-releases ya existe"
fi

echo "==> Buscando imágenes Ubuntu 22.04 en ubuntu-releases..."

echo "   Buscando imagen VM..."
VM_FP=$($LXC image list ubuntu-releases: --format json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for img in data:
    if img.get('type') == 'virtual-machine' and img.get('architecture') == 'x86_64':
        aliases = [a['name'] for a in (img.get('aliases') or [])]
        if any('22.04' in a for a in aliases):
            print(img['fingerprint'])
            break
")
if [ -n "$VM_FP" ]; then
  echo "   VM fingerprint: $VM_FP"
  if ! $LXC image list local: 2>/dev/null | grep -q ubuntu-22.04-vm; then
    $LXC image copy "ubuntu-releases:$VM_FP" local: --alias ubuntu-22.04-vm
  fi
else
  echo "   WARNING: No se encontró imagen VM Ubuntu 22.04"
fi

echo "   Buscando imagen contenedor..."
CT_FP=$($LXC image list ubuntu-releases: --format json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for img in data:
    if img.get('type') == 'container' and img.get('architecture') == 'x86_64':
        aliases = [a['name'] for a in (img.get('aliases') or [])]
        if any('22.04' in a for a in aliases):
            print(img['fingerprint'])
            break
")
if [ -n "$CT_FP" ]; then
  echo "   Container fingerprint: $CT_FP"
  if ! $LXC image list local: 2>/dev/null | grep -q ubuntu-22.04-container; then
    $LXC image copy "ubuntu-releases:$CT_FP" local: --alias ubuntu-22.04-container
  fi
else
  echo "   WARNING: No se encontró imagen contenedor Ubuntu 22.04"
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
$LXC storage list
$LXC network list
$LXC profile list
$LXC project list
$LXC image list local

echo "Configuración de LXD completada"
