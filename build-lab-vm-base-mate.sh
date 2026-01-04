#!/usr/bin/env bash
set -e

PROJECT="labs"
BASE_VM="vm-base"
IMAGE_ALIAS="lab-vm-base"
IMAGE_SOURCE="local:ubuntu-22.04-vm"
PROFILE="persistent"

echo "==> Usando proyecto $PROJECT"
lxc project switch "$PROJECT"

if lxc image list | grep -q "$IMAGE_ALIAS"; then
  echo "==> La imagen $IMAGE_ALIAS ya existe. Abortando."
  exit 0
fi

echo "==> Creando VM temporal $BASE_VM"
lxc launch "$IMAGE_SOURCE" "$BASE_VM" \
  --vm \
  -p "$PROFILE"

echo "==> Esperando arranque"
sleep 30

echo "==> Instalando escritorio MATE y servicios"
lxc exec "$BASE_VM" -- bash <<'EOF'
set -e

apt update

# Escritorio MATE + display manager ligero
apt install -y \
  ubuntu-mate-desktop-core \
  lightdm \
  xrdp \
  cloud-init \
  openssh-server \
  sudo \
  curl \
  vim \
  ca-certificates

# Configuración XRDP para MATE
sed -i 's/^test -x/#test -x/' /etc/xrdp/startwm.sh
sed -i 's/^exec .*/exec mate-session/' /etc/xrdp/startwm.sh

systemctl enable xrdp
systemctl enable ssh
systemctl set-default graphical.target

# Limpieza
apt clean
rm -rf /var/lib/apt/lists/*
rm -f /etc/cloud/cloud.cfg.d/99-installer.cfg
EOF

echo "==> Apagando VM base"
lxc stop "$BASE_VM"

echo "==> Publicando imagen $IMAGE_ALIAS"
lxc publish "$BASE_VM" --alias "$IMAGE_ALIAS"

echo "==> Eliminando VM temporal"
lxc delete "$BASE_VM"

echo "==> Imagen base con MATE creada correctamente"
lxc image list | grep "$IMAGE_ALIAS"
