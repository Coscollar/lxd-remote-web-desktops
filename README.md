# lxd-remote-web-desktops
Escritorios remotos por navegador con LXD

https://github.com/Coscollar/lxd-remote-web-desktops.git

## Documentación

- [`docs/DEPLOY.md`](docs/DEPLOY.md) — Guía de despliegue del host completo (FASES 0–6).
- [`docs/USO.md`](docs/USO.md) — Guía de uso para alumnos y administradores.
- [`docs/cloud-init-render.md`](docs/cloud-init-render.md) — Contrato de renderización de `cloud-init-template.yml`.
- [`docs/web-gateway.md`](docs/web-gateway.md) — Acceso web (Guacamole + guacd + Nginx, multi-ruta FASE 6).
- [`docs/policy.md`](docs/policy.md) — Policy engine: snapshots, reset, auto-destrucción y apps stateless (FASE 6).
- [`docs/FASE-6-apps-stateless.md`](docs/FASE-6-apps-stateless.md) — Diseño de apps stateless, portal web y consola admin (FASE 6).
- [`PLAN.md`](PLAN.md) — Plan de implementación (FASES 0–6) y deudas técnicas.

## Instalación rápida (un comando)

`install-all.sh` es el entrypoint único: desinstala cualquier instalación
previa, instala dependencias del sistema y ejecuta todas las fases (0→6)
generando secretos automáticamente.

```bash
git clone https://github.com/Coscollar/lxd-remote-web-desktops.git
cd lxd-remote-web-desktops
sudo bash install-all.sh --domain=lab.example.com --email=admin@example.com
```

`--domain` y `--email` son obligatorios. Opcionales: `--smtp-user`,
`--smtp-pass`. El script convierte CRLF→LF internamente. Si el grupo `lxd`
no está activo, aborta con `exit 100` → re-login y reejecutar.

`install-all.sh` incluye la FASE 6 (portal web + apps stateless + consola
admin): amplía `stateless-pool` a 80GB, `lab-stateless` a /23, construye
imágenes de apps (`build-apps/build-app-*.sh`), instala reglas
`iptables-apps.sh` y el timer `provision-reap-apps`. Los secretos
adicionales (`ADMIN_JWT_SECRET`, `ADMIN_TOKEN`, `INTERNAL_TOKEN`,
`ADMIN_TOTP_KEY`) se generan automáticamente.

## Desinstalación

```bash
sudo bash uninstall-all.sh --domain=lab.example.com           # con confirmación
sudo bash uninstall-all.sh --yes --domain=lab.example.com    # sin confirmación
sudo bash uninstall-all.sh --purge-lxd --domain=lab.example.com  # + pools/redes/perfiles
```

`uninstall-all.sh` elimina también las reglas `iptables-apps`, el allowlist
8000, el timer `provision-reap-apps`, y las imágenes/instancias `app-*`
(cubiertas por el bucle de labs). No desinstala paquetes del sistema (nginx,
docker, certbot, snap LXD) ni el repo en disco. No revierte la ampliación de
pool/subred (ZFS shrink peligroso; /23 no perjudica). Usa `--purge-lxd` para
eliminar pools completamente.

## Instalación paso a paso (avanzado)

Los scripts se editan desde Windows (CRLF) y abortan si detectan CRLF.
Convertir a LF antes de ejecutarlos:

```bash
sudo apt update && sudo apt install dos2unix -y
for f in *.sh provision/*.sh guacamole/*.sh nginx/*.sh build-apps/*.sh; do
  dos2unix "$f" 2>/dev/null || true
done
```

Puesta en marcha fase por fase (ver [`docs/DEPLOY.md`](docs/DEPLOY.md)
para el detalle de cada una):

```bash
sudo bash server-setup-lxd.sh          # FASE 0: infra LXD + imagen base VM
sudo bash provision/install.sh          # FASE 1-3: provision-api (incluye web/ FASE 6.2)
cd guacamole && sudo bash install.sh && cd ..   # FASE 4: Guacamole + guacd
sudo bash nginx/install.sh lab.<dominio> admin@<dominio>  # FASE 4: Nginx + certbot
sudo bash nginx/iptables-lab.sh         # FASE 4: aislamiento inter-VM
# FASE 5 (policy engine) ya integrada en provision-api + systemd timer
# FASE 6 (portal web + apps stateless) — integrada en install-all.sh.
# Si se hace paso a paso:
lxc storage set stateless-pool size=80GB                    # FASE 6.3: ampliar pool
lxc network set lab-stateless ipv4.address=10.50.10.1/23 --project labs  # /23
lxc network set lab-stateless ipv4.address=10.50.10.1/23 --project default
for f in build-apps/build-app-*.sh; do sudo bash "$f"; done   # construir imágenes apps
sudo bash nginx/iptables-apps.sh        # FASE 6.3: aislamiento apps stateless
# FASE 6.0 (fix preexistente): uvicorn --host 0.0.0.0 + iptables allowlist 8000
#   ya aplicado por install-all.sh
```

Validaciones tras configurar:

```bash
lxc storage list && lxc network list && lxc profile list && lxc project list && lxc image list local
lxc image list local --project labs | grep app-   # FASE 6: imágenes de apps
sudo ss -tlnp | grep -E ':(3389|5900|3000|8888)'   # FASE 6: vacío (no expuestos)
```
