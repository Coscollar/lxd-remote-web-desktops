# lxd-remote-web-desktops

Escritorios remotos y aplicaciones por navegador para alumnos, construido
sobre LXD. https://github.com/Coscollar/lxd-remote-web-desktops.git

## Qué es

Un único host Ubuntu Server ejecuta:

- **VMs LXD persistentes** — un escritorio MATE por alumno y lab, accesible
  por navegador vía xrdp + Apache Guacamole. Con snapshots de guardado/reset.
- **Contenedores LXD stateless** — apps HTTP (Jupyter, demos...) compartidas
  o por alumno, proxyadas directamente por Nginx (sin RDP).
- **provision-api** (`provision/`) — orquestador FastAPI: autenticación por
  magic link + JWT, provisión on-demand con cola de jobs persistente,
  política de snapshots y auto-destrucción, consola de administración.
- **Nginx** — TLS (Let's Encrypt) + reverse proxy multi-ruta + puerta de
  autenticación (`auth_request`) delante de todo.
- **Guacamole + guacd** (Docker) — túnel RDP-en-navegador. guacd es SIEMPRE
  el intermediario RDP/VNC; los puertos 3389/5900 nunca se exponen.

## Arquitectura

```
Navegador ──HTTPS──▶ Nginx (:443)
                        │
                        ├── / , /dashboard , /lab/* , /api/* , /admin/* , /static/*
                        │   auth_request /verify (o /admin/verify para /admin/*)
                        │   → provision-api (:8000)
                        │
                        ├── /desktop/{lab}/...
                        │   auth_request /verify (exige X-Lab-Scope=lab)
                        │   → Guacamole Server (:8080)
                        │       → guacd (:4822)
                        │           → VM alumno (xrdp :3389, NO expuesto)
                        │
                        └── /apps/{app_id}/...
                            auth_request /verify/app (READ-ONLY, valida pertenencia)
                            → app stateless (10.50.10.x:puerto, HTTP directo, NO guacd)
```

| Servicio        | Bind            | Origen permitido          | Destino real        |
|-----------------|-----------------|---------------------------|---------------------|
| Nginx           | 0.0.0.0:80/443  | Internet (TLS)            | provision-api 8000 / Guacamole 8080 / app stateless |
| provision-api   | 0.0.0.0:8000    | Nginx (127.0.0.1), VMs (10.50.20.0/24), apps (10.50.10.0/23) — allowlist iptables | — |
| Guacamole Server| 127.0.0.1:8080  | Nginx (loopback)          | guacd 4822          |
| guacd           | 127.0.0.1:4822  | Guacamole (loopback)      | VM 10.50.20.x:3389  |
| mysql           | 127.0.0.1:3306  | Guacamole (loopback)      | —                   |
| app stateless   | 10.50.10.x:puerto | Nginx (10.50.10.1)      | —                   |

Validación rápida: `sudo ss -tlnp | grep -E ':(3389|5900|3000|8888)'` debe
estar vacío, y `docker ps` debe mostrar guacd **sin** puertos publicados.

## Identidad y seguridad

- **Alumnos:** magic link por email (15 min) → JWT HS256 en cookie (1h) con
  claim `scope`: `dashboard` (multi-lab, sin lab fijado) o `lab` (lab
  seleccionado vía `/lab/select`). Nginx solo enruta a Guacamole si
  `scope=lab`.
- **Admin:** magic link separado (5 min, TOTP opcional) → cookie
  `admin_token` (`Path=/admin`, TTL 30 min sin renovación deslizante),
  firmada con `ADMIN_JWT_SECRET` (distinto del secreto de alumnos). El alta
  de admins es **solo-SQL por diseño** (sin UI ni endpoint).
- **Identidad SOLO desde el JWT**: Nginx obtiene `X-Lab-Alumno`/`X-Lab-Name`
  del `auth_request` a provision-api y sobreescribe siempre `Remote-User`;
  el cliente no puede inyectarlos. Un middleware en `provision/main.py`
  elimina cualquier header forjado (`X-Lab-Role`, `X-Admin-Email`,
  `X-Lab-Alumno`, `X-Lab-Name`, `X-App-Target`).
- **`X-Internal`:** secreto compartido Nginx→provision-api (≥32 bytes, nunca
  logueado) como defensa en profundidad; lo genera el instalador en
  `/etc/nginx/conf.d/lab-internal.conf` (0600).
- **VMs y apps** se autentican ante la API con service tokens propios
  (HS256, `scope=save|reset|heartbeat`, ligados a IP). Nunca ejecutan `lxc`.
- **Apps en iframe** con `sandbox="allow-scripts allow-forms"` **sin**
  `allow-same-origin`: efectivamente cross-origin, no leen cookies del padre.
  `/verify/app` valida la pertenencia app↔alumno y devuelve `X-App-Target`
  (generado por la API, no por el cliente — anti-SSRF).
- **Aislamiento de red (iptables):** DROP inter-VM, DROP inter-app, DROP
  app↔VM bidireccional; solo host→VM:3389 (UID de guacd) y host→app:puerto
  (UID de provision). Scripts: `nginx/iptables-lab.sh`,
  `nginx/iptables-apps.sh`.
- **CSP estricta** (`script-src 'self'`, sin `unsafe-inline` ni nonce): todo
  el JS del portal es estático (`provision/web/static/js/`), render DOM con
  `createElement`/`textContent`.
- **Logs seguros:** sin cookies, magic links redactados, `X-App-Target` y
  `X-Internal` nunca logueados.

## Ciclo de vida de las instancias

**VMs persistentes** (perfil `persistent`, proyecto `labs`):

- Se lanzan on-demand vía **cola de jobs persistente** (tabla `jobs` +
  worker; nunca síncronamente) desde una imagen base `lab-vm-base`
  (MATE + xrdp, autologin, sin password RDP conocida — "Modelo A"), con un
  cloud-init por alumno renderizado en memoria (contrato completo en
  `docs/DEPLOY.md`, Anexo A).
- **Snapshots**: `base` (inviolable, tras el primer arranque sano) +
  `k1..k5` bajo demanda del alumno (`lab-save`), rotación FIFO con LXD como
  fuente de verdad. `lab-reset` restaura a `base`.
- **Pool guard** sobre `persistent-pool`: >60% de uso reduce retención a
  `k1..k3`; >75% purga el snapshot más viejo antes de crear; >90% rechaza
  con 503 (también rechaza lanzar VMs nuevas). Fail-closed.
- **Auto-destrucción** (reaper standalone por systemd timer, anti-TOCTOU):
  por inactividad (`IDLE_MINUTES`, heartbeat de la VM cada 5 min), por
  deadline del lab o por fin de curso (`COURSE_DEADLINE`), y `creando`
  estancadas (`CREATING_TIMEOUT`).

**Apps stateless** (perfil `stateless`, imagen prebuilt `local:app-<id>`):

- `shared=1`: una instancia para todo el lab (`always_on=1` = siempre viva,
  con presupuesto `ALWAYS_ON_BUDGET_MB` y auto-heal al arrancar el
  servicio). `shared=0`: una por alumno, destruida tras `APP_IDLE_MINUTES`.
- Sin snapshots: reset = destroy + recreate. Reaper propio
  (`provision-reap-apps.timer`) con grace period tras reinicios.
- Al arrancar, provision-api **reconcilia BD↔LXD siempre en dry-run**: marca
  huérfanas, nunca borra a ciegas.

## Cotas de escalabilidad

| Recurso                          | Cota              | Límite dominante       |
|----------------------------------|-------------------|------------------------|
| `persistent-pool` 40GB + k1..k5  | ≤2-3 alumnos      | Pool ZFS (cuello actual) |
| Retención reducida k1..k3 (>60%) | ~más alumnos      | Pool guard             |
| SQLite single-writer             | ≤50 alumnos       | Writer lock            |
| uvicorn workers=1 + job queue    | ≤4 lanzamientos concurrentes | Event loop  |
| `lab-persistent` /24             | ≤250 VMs          | Subred                 |
| RAM host (4GB/VM)                | N ≤ RAM_host / 4  | RAM                    |
| `stateless-pool` 80GB            | ~60-80 contenedores | Pool ZFS             |
| RAM host (2GB/app)               | `min((RAM−VMs)/2GB, MAX_APP_INSTANCES)` | RAM |
| `lab-stateless` /23              | ~510 IPs          | Subred                 |
| `/verify/app` read-only          | ~200-500 req/s    | JWT decode             |
| Apps shared `always_on=1`        | `sum(memory_mb) ≤ ALWAYS_ON_BUDGET_MB` | RAM |

## Estructura del repo

- `install-all.sh` / `uninstall-all.sh` — entrypoints únicos de
  instalación/desinstalación (con preflight fail-fast).
- `server-setup-lxd.sh` — FASE 0: pools ZFS, redes, perfiles restringidos,
  proyecto `labs`, imágenes simplestreams.
- `build-lab-vm-base-mate.sh` — imagen base VM (MATE + xrdp).
- `build-apps/` — imágenes de apps stateless (`build-app-<id>.sh`).
- `provision/` — la API FastAPI (auth, instancias, jobs, policy, reaper,
  apps, consola admin, portal web).
- `cloud-init-template.yml` — plantilla Jinja2 por alumno (ver
  `docs/DEPLOY.md`, Anexo A).
- `nginx/` — `lab.conf`, `install.sh`, `iptables-lab.sh`, `iptables-apps.sh`.
- `guacamole/` — stack Docker (guacd + guacamole + mysql) + `install.sh`.
- `systemd/` — `provision.service` y timers de los reapers.

## Documentación

- [`docs/DEPLOY.md`](docs/DEPLOY.md) — Instalación y despliegue: preflight,
  instalación en un comando, paso a paso por fases, troubleshooting, deudas,
  y anexos técnicos (contrato cloud-init, gateway web, policy engine).
- [`docs/USO.md`](docs/USO.md) — Instrucciones de uso para alumnos y
  administradores (consola web + CLI de respaldo).

## Instalación rápida (un comando)

Requisitos: un **Ubuntu Server 22.04/24.04 limpio** con root, DNS apuntando
al host, 80/443 abiertos y virtualización KVM (`/dev/kvm`). **Sin
dependencias previas**: `install-all.sh` es el entrypoint único — ejecuta un
preflight (KVM, ZFS, snapd, puertos, DNS...), desinstala cualquier
instalación previa, instala todas las dependencias del sistema y ejecuta
todas las fases (0→6) generando secretos automáticamente (quedan en
`/etc/provision/provision.env`, no se imprimen por pantalla).

```bash
git clone https://github.com/Coscollar/lxd-remote-web-desktops.git
cd lxd-remote-web-desktops
sudo bash install-all.sh --domain=lab.example.com --email=admin@example.com
```

`--domain` y `--email` son obligatorios. Opcionales: `--smtp-user`,
`--smtp-pass`, `--skip-preflight` (degrada los aborts del preflight a
warnings). El script convierte CRLF→LF internamente. Si el grupo `lxd`
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
