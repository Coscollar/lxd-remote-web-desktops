---
name: preseed-destructive
description: Recordatorio critico. `lxd init --preseed` es DESTRUCTIVO y machaca toda la config del daemon. Solo re cargar para recreacion intencionada; ajustes puntuales via lxc CLI.
---

# Preseed es DESTRUCTIVO

- `lxd init --preseed < lxd-preseed.yaml` reescribe desde cero redes, pools, perfiles, proyectos y config global del daemon.
- **No recargar** este archivo por cada cambio menor. Para ajustes puntuales (limites de CPU, nuevo device, ajustar red), usar `lxc` CLI directamente:
  - `lxc profile device set persistent root size 50GB`
  - `lxc profile set persistent limits.cpu=4`
  - `lxc network set lab-persistent ipv4.address=...`
- Recargar el preseed deja huerfano lo que no este declarado en el (snapshots, instancias, imagenes locales copiadas).
- Si sueles tocar el YAML para probar, confina el cambio en un script aparte con `--preseed` y documenta que solo corre en re-init.
- `1-server-setup-lxd.sh` ya aplica el preseed; ese script es el que decide cuando se hace. No llamar `lxd init --preseed` suelto.
- Cuando hayas de recrear, haz snapshot/export de instancias vivas antes.

Ver `opencode.json` y `1-server-setup-lxd.sh` para el flujo autorizado.