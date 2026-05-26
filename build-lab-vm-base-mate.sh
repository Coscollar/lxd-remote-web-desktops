#!/usr/bin/env bash
set -e

BASE_VM="vm-base"
IMAGE_ALIAS="lab-vm-base"
IMAGE_SOURCE="local:ubuntu-22.04-vm"

cleanup() {
  if $LXC info "$BASE_VM" >/dev/null 2>&1; then
    echo "   Limpiando VM temporal $BASE_VM..."
    $LXC delete -f "$BASE_VM" 2>/dev/null || true
  fi
}
trap 'echo "ERROR: Fallo en build-lab-vm-base-mate.sh"; cleanup' ERR

echo "==> Detectando acceso a LXD"
if lxc list >/dev/null 2>&1; then
  LXC="lxc"
else
  LXC="sudo lxc"
fi

if $LXC image list local: | grep -q "$IMAGE_ALIAS"; then
  echo "==> La imagen $IMAGE_ALIAS ya existe. Abortando."
  exit 0
fi

echo "==> Verificando que el perfil persistent exista"
if ! $LXC profile show persistent >/dev/null 2>&1; then
  echo "   -> Perfil persistent no existe. Creándolo..."
  $LXC profile create persistent
  $LXC profile set persistent limits.cpu 4
  $LXC profile set persistent limits.memory 4GB
  $LXC profile device add persistent root disk pool=persistent-pool path=/
  $LXC profile device add persistent eth0 nic network=lab-persistent name=eth0
fi

echo "==> Creando VM temporal $BASE_VM"
$LXC launch "$IMAGE_SOURCE" "$BASE_VM" \
  --vm \
  -p persistent

echo "==> Esperando que la VM $BASE_VM esté en ejecución..."
for i in $(seq 1 120); do
  STATUS=$($LXC info "$BASE_VM" 2>/dev/null | awk '/^Status:/ {print $2}')
  if [ "$STATUS" = "Running" ]; then
    echo "   OK - VM Running tras ${i}s"
    break
  fi
  if [ "$i" -ge 120 ]; then
    echo "ERROR: La VM $BASE_VM no arrancó en 120s"
    $LXC delete -f "$BASE_VM" 2>/dev/null || true
    exit 1
  fi
  sleep 1
done

echo "==> Esperando cloud-init (máx 120s)..."
for i in $(seq 1 120); do
  CI_STATUS=$($LXC exec "$BASE_VM" -- cloud-init status 2>/dev/null || echo "error")
  if echo "$CI_STATUS" | grep -q "done"; then
    echo "   OK - cloud-init completado en ${i}s"
    break
  fi
  if [ "$i" -ge 120 ]; then
    echo "   WARNING: cloud-init no completó en 120s, continuando..."
  fi
  sleep 1
done

echo "==> Instalando escritorio MATE y servicios"
$LXC exec "$BASE_VM" -- bash <<'EOF'
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
$LXC stop "$BASE_VM"

echo "==> Publicando imagen $IMAGE_ALIAS"
$LXC publish "$BASE_VM" --alias "$IMAGE_ALIAS"

echo "==> Eliminando VM temporal"
$LXC delete "$BASE_VM"

echo "==> Imagen base con MATE creada correctamente"
$LXC image list | grep "$IMAGE_ALIAS"
