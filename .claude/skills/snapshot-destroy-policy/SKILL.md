---
name: snapshot-destroy-policy
description: Politica de snapshots nativos LXD solo para VMs + auto-destruccion por inactividad/fecha/curso. Esquema base-tag, reset via restore, retention limitada para no saturar persistent-pool 40GB.
---

# Politica de snapshots y destroy

## Solo VMs
- Snapshots nativos LXD **solo para VMs persistentes** (profile `persistent`, proyecto `labs`).
- Los contenedores stateless NO persisten; tras cierre se destruyen sin snapshot.

## Tag canonico
- `<instancia>:base` — snapshot en el estado tras el primer cloud-init (hecho por provision-api al confirmar `cloud-init status --wait`).
- `<instancia>:k<n>` — estados intermedios del alumno con retention maxima (por defecto 5 snapshots). El n+1 elimina el mas viejo.

## Comandos
```bash
# crear base (una vez por instancia, tras primer boot)
lxc snapshot <instancia> base --project labs

# save: snapshot numerado
lxc snapshot <instancia> k1 --project labs
# retention:
lxc info <instancia> --project labs | grep -A20 Snapshots   # listar
# purgar sobrantes: enumerar y lxc delete <instancia>/<tag> --project labs

# reset: restaurar base
lxc restore <instancia> base --project labs

# borrar snapshot
lxc delete <instancia>/k3 --project labs
```

## API expuesta a scripts dentro de la VM
La VM no ejecuta `lxc`; llama al provision-api:
- `POST /save?lab=<hostname>` → `lxc snapshot`
- `POST /reset?lab=<hostname>` → `lxc restore ... base`
- `POST /restore?lab=<hostname>&tag=k2` → restaurar estado concreto
- `GET /snapshots?lab=<hostname>` → listar

## Auto-destruccion (triggers)
- **Por inactividad**: provision-api guarda `last_seen` por instancia; un ticker/cron cada N min destruye las > `idle_minutes`.
- **Por fecha**: deadline por curso en `config.toml`; ticker destruye caducadas.
- **Por logout explicito**: opcional, llamar a `destroy` si el alumno pulsa cerrar.

## Limpieza en arranque del servidor
```bash
# inventario actual
lxc list --project labs --format csv | awk -F, '{print $1}'
# cotejar contra estado de provision-api
```
Si la VM existe pero no esta en estado, marcarla para reaper o eliminar (con confirmacion/telemetry).

## Riesgo de pool
`persistent-pool` 40GB. Sin retention, snapshots colapsan la capacidad; por eso limite `keep:5`.

## Una instancia por alumno/lab
Re-lanzar reset reusa el mismo nombre `<alumno>-<lab>`; nunca crear paralelas.