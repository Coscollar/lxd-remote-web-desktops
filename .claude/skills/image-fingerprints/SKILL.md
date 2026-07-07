---
name: image-fingerprints
description: Fingerprints hardcoded de Ubuntu 22.04 usados en el repo y la regla de actualización dual (1-server-setup-lxd.sh + build-lab-vm-base-mate.sh).
---

# Imagenes fijadas del repo

| Fingerprint | Alias local | Tipo |
|---|---|---|
| `cf181d732f32` | `local:ubuntu-22.04-vm` | container type=virtual-machine |
| `a6d2f7222476` | `local:ubuntu-22.04-container` | container type=container |

La base del laboratorio es `local:lab-vm-base` (publicada por `build-lab-vm-base-mate.sh`).

## Regla de actualizacion
Si cambias de release de Ubuntu:
1. Actualiza los fingerprints en `1-server-setup-lxd.sh`.
2. **Y** actualiza `IMAGE_SOURCE` en `build-lab-vm-base-mate.sh`.

Si solo lo haces en uno:
- Solo en `1-server-setup-lxd.sh`: el builder lanza desde alias viejo todavia existente pero en freeze.
- Solo en `build-lab-vm-base-mate.sh`: el builder cae si el alias no existe.

## Como obtener nuevos fingerprints
```bash
lxc image list ubuntu-releases: | grep 22.04 | grep x86_64
# para 24.04 LTS:
lxc image list ubuntu-releases: | grep 24.04 | grep x86_64
```

`images.auto_update_interval: "0"`: las imagenes NO se autoactualizan; rotacion manual.