---
name: lxd-cli-patterns
description: Patrones de comandos lxc idempotentes para LXD (verificar antes de crear, evitar duplicados). Usar al escribir scripts bash del repo.
---

# Patron lxc idempotente

## Crear pool / red / profile / project
```bash
# SIEMPRE verificar antes de crear
if ! lxc storage list | grep -q stateless-pool; then
  sudo lxc storage create stateless-pool zfs size=20GB
fi

if ! lxc network list | grep -q lab-stateless; then
  lxc network create lab-stateless ...  # o se precrea via preseed
fi

if ! lxc profile list | grep -q persistent; then
  lxc profile create persistent
  lxc profile device add ...
fi
```

## Copiar imagen con alias estable
```bash
if ! lxc image list local: | grep -q ubuntu-22.04-vm; then
  lxc image copy ubuntu-releases:cf181d732f32 local: --alias ubuntu-22.04-vm
fi
```

## Lanzar instancia
```bash
NAME="alumnoX-labY"
if ! lxc list --project labs | grep -q "$NAME"; then
  lxc launch local:lab-vm-base "$NAME" --vm -p persistent --project labs
fi
```

## Esperar cloud-init
```bash
lxc exec "$NAME" -- cloud-init status --wait
# NO usar sleep N ciego
```

## Validaciones consolidadas
```bash
lxc storage list && lxc network list && lxc profile list && lxc project list && lxc image list local
```

## Snapshots (politica)
```bash
lxc snapshot "$NAME" base --project labs        # estado base post-primer-boot
lxc restore "$NAME" base --project labs         # reset
lxc delete "$NAME/base --project labs            # borrar snapshot
# listado
lxc info "$NAME" --project labs | grep -A20 Snapshots
```

`set -euo pipefail` siempre al inicio del script.