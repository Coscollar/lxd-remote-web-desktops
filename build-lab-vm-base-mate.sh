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

echo "==> Verificando que la imagen $IMAGE_SOURCE exista"
if ! $LXC image list local: 2>/dev/null | grep -q ubuntu-22.04-vm; then
  echo "ERROR: La imagen $IMAGE_SOURCE no existe localmente"
  echo "       Ejecuta primero 1-server-setup-lxd.sh o copia la imagen manualmente"
  exit 1
fi
echo "   Verificando que la imagen sea VM..."
IMG_TYPE=$($LXC image list local: --format json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for img in data:
    aliases = [a['name'] for a in (img.get('aliases') or [])]
    if any('ubuntu-22.04-vm' in a for a in aliases):
        print(img.get('type', 'unknown'))
        break
" 2>/dev/null || echo "unknown")
if [ "$IMG_TYPE" != "virtual-machine" ]; then
  echo "WARNING: La imagen local no es de tipo virtual-machine (tipo: $IMG_TYPE)"
  echo "         El lanzamiento como VM podría fallar"
fi

echo "==> Creando VM temporal $BASE_VM"
$LXC launch "$IMAGE_SOURCE" "$BASE_VM" \
  --vm \
  -p persistent

echo "==> Esperando que la VM $BASE_VM esté en ejecución..."
for i in $(seq 1 120); do
  STATE=$($LXC list "$BASE_VM" --format csv -c s 2>/dev/null)
  case "$STATE" in
    Running)
      echo "   OK - VM Running tras ${i}s"
      break
      ;;
    Error)
      echo "ERROR: VM $BASE_VM entró en estado 'Error'"
      $LXC delete -f "$BASE_VM" 2>/dev/null || true
      exit 1
      ;;
    Stopped)
      echo "ERROR: VM $BASE_VM se detuvo inesperadamente"
      $LXC delete -f "$BASE_VM" 2>/dev/null || true
      exit 1
      ;;
    "")
      if [ "$i" -ge 120 ]; then
        echo "ERROR: VM $BASE_VM no aparece en lxc list tras 120s"
        $LXC list "$BASE_VM" 2>/dev/null || true
        exit 1
      fi
      ;;
  esac
  sleep 1
done

echo "==> Verificando tipo de instancia..."
INST_TYPE=$($LXC list "$BASE_VM" --format csv -c T 2>/dev/null)
if [ "$INST_TYPE" != "VIRTUAL-MACHINE" ]; then
  echo "ERROR: $BASE_VM no es una VM (tipo: $INST_TYPE)"
  $LXC delete -f "$BASE_VM" 2>/dev/null || true
  exit 1
fi

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
