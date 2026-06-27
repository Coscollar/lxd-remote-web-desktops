# lxd-remote-web-desktops
Escritorios remotos por navegador con LXD

https://github.com/Coscollar/lxd-remote-web-desktops.git

## Documentación

- [`docs/DEPLOY.md`](docs/DEPLOY.md) — Guía de despliegue del host completo (FASES 0–5).
- [`docs/USO.md`](docs/USO.md) — Guía de uso para alumnos y administradores.
- [`docs/cloud-init-render.md`](docs/cloud-init-render.md) — Contrato de renderización de `cloud-init-template.yml`.
- [`docs/web-gateway.md`](docs/web-gateway.md) — Acceso web (Guacamole + guacd + Nginx).
- [`docs/policy.md`](docs/policy.md) — Policy engine: snapshots, reset y auto-destrucción.
- [`PLAN.md`](PLAN.md) — Plan de implementación (FASES 0–5) y deudas técnicas.

## Instalación rápida (un comando)

`install-all.sh` es el entrypoint único: desinstala cualquier instalación
previa, instala dependencias del sistema y ejecuta todas las fases (0→5)
generando secretos automáticamente.

```bash
git clone https://github.com/Coscollar/lxd-remote-web-desktops.git
cd lxd-remote-web-desktops
sudo bash install-all.sh --domain=lab.example.com --email=admin@example.com
```

`--domain` y `--email` son obligatorios. Opcionales: `--smtp-user`,
`--smtp-pass`. El script convierte CRLF→LF internamente. Si el grupo `lxd`
no está activo, aborta con `exit 100` → re-login y reejecutar.

## Desinstalación

```bash
sudo bash uninstall-all.sh --domain=lab.example.com           # con confirmación
sudo bash uninstall-all.sh --yes --domain=lab.example.com    # sin confirmación
sudo bash uninstall-all.sh --purge-lxd --domain=lab.example.com  # + pools/redes/perfiles
```

No desinstala paquetes del sistema (nginx, docker, certbot, snap LXD) ni
el repo en disco.

## Instalación paso a paso (avanzado)

Los scripts se editan desde Windows (CRLF) y abortan si detectan CRLF.
Convertir a LF antes de ejecutarlos:

```bash
sudo apt update && sudo apt install dos2unix -y
for f in *.sh provision/*.sh guacamole/*.sh nginx/*.sh; do
  dos2unix "$f" 2>/dev/null || true
done
```

Puesta en marcha fase por fase (ver [`docs/DEPLOY.md`](docs/DEPLOY.md)
para el detalle de cada una):

```bash
sudo bash server-setup-lxd.sh          # FASE 0: infra LXD + imagen base VM
sudo bash provision/install.sh          # FASE 1-3: provision-api
cd guacamole && sudo bash install.sh && cd ..   # FASE 4: Guacamole + guacd
sudo bash nginx/install.sh lab.<dominio> admin@<dominio>  # FASE 4: Nginx + certbot
sudo bash nginx/iptables-lab.sh         # FASE 4: aislamiento inter-VM
# FASE 5 (policy engine) ya integrada en provision-api + systemd timer
```

Validaciones tras configurar:

```bash
lxc storage list && lxc network list && lxc profile list && lxc project list && lxc image list local
```
