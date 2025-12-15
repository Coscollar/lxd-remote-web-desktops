#!/usr/bin/env bash
set -e

echo "==> Instalando LXD vía snap"
if ! command -v lxd >/dev/null 2>&1; then
  sudo snap install lxd
else
  echo "LXD ya está instalado"
fi

echo "==> Verificando grupo lxd para el usuario $USER"
if ! getent group lxd | grep -q "$USER"; then
  echo "Añadiendo usuario $USER al grupo lxd"
  sudo usermod -aG lxd "$USER"
  echo "Recargando grupos (newgrp lxd)"
  newgrp lxd <<EOF
echo "Grupo lxd aplicado"
EOF
else
  echo "El usuario ya pertenece al grupo lxd"
fi

echo "==> Creando pools ZFS"
if ! lxc storage list | grep -q stateless-pool; then
  sudo lxc storage create stateless-pool zfs size=20GB
else
  echo "stateless-pool ya existe"
fi

if ! lxc storage list | grep -q persistent-pool; then
  sudo lxc storage create persistent-pool zfs size=40GB
else
  echo "persistent-pool ya existe"
fi

echo "==> Añadiendo remote ubuntu-releases"
if ! lxc remote list | grep -q ubuntu-releases; then
  lxc remote add ubuntu-releases https://cloud-images.ubuntu.com/releases --protocol simplestreams
else
  echo "Remote ubuntu-releases ya existe"
fi

echo "==> Listando imágenes Ubuntu 22.04 x86_64"
lxc image list ubuntu-releases: | grep 22.04 | grep x86_64 || true

echo "==> Copiando imágenes locales"
if ! lxc image list local: | grep -q ubuntu-22.04-vm; then
  lxc image copy ubuntu-releases:cf181d732f32 local: --alias ubuntu-22.04-vm
fi

if ! lxc image list local: | grep -q ubuntu-22.04-container; then
  lxc image copy ubuntu-releases:a6d2f7222476 local: --alias ubuntu-22.04-container
fi

echo "==> Inicializando LXD desde preseed"
if [ -f lxd-preseed.yaml ]; then
  sudo lxd init --preseed < ./lxd-preseed.yaml
else
  echo "ERROR: No se encontró lxd-preseed.yaml"
  exit 1
fi

echo "==> Validaciones finales"
lxc storage list
lxc network list
lxc profile list
lxc project list
lxc image list local

echo "Configuración de LXD completada"
