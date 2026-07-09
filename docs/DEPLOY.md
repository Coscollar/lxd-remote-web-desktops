# Despliegue del Entorno de Laboratorio con LXD

Guía de despliegue del host completo (FASES 0–5). El repo se edita desde
Windows (CRLF); los scripts abortan si detectan CRLF, así que hay que
convertirlos a LF antes de ejecutarlos.

> Nota: el script de setup en disco se llama `server-setup-lxd.sh` (un
> comentario interno aún referencia `1-server-setup-lxd.sh`).

## Despliegue con un único script (recomendado)

El entrypoint único es `install-all.sh`: desinstala cualquier instalación
previa, instala dependencias del sistema, y ejecuta todas las fases
(0→6) generando secretos automáticamente.

**Modo dirigido (por defecto).** Ejecutado sin flags desde un terminal,
arranca un asistente que pide todo lo necesario, valida cada dato, muestra
un resumen y pide confirmación antes de tocar nada:

```bash
git clone https://github.com/Coscollar/lxd-remote-web-desktops.git
cd lxd-remote-web-desktops
sudo bash install-all.sh
```

El asistente pregunta:

1. **Dominio público** del portal (necesita registro DNS A hacia el host).
2. **Email para certbot** (avisos de Let's Encrypt).
3. **Email del primer administrador** de la consola `/admin` (se siembra
   automáticamente en la tabla `admins`; por defecto, el mismo de certbot).
4. **Credenciales SMTP** para los magic links (el password se pide oculto,
   sin quedar en `ps` ni en el historial). Se puede posponer y rellenar
   después en `/etc/provision/provision.env`.

**Modo no interactivo (automatización).** Los mismos datos por flags:

```bash
sudo bash install-all.sh --domain=lab.example.com --email=admin@example.com \
     [--admin-email=admin@example.com --smtp-user=xxx --smtp-pass=yyy]
```

- `--domain` y `--email` son **obligatorios** en este modo (sin terminal no
  hay asistente).
- `--admin-email` opcional: siembra el primer admin de la consola.
- `--smtp-user` / `--smtp-pass` opcionales (si se omiten, se deja Mailtrap
  sin credenciales para rellenar a mano en `/etc/provision/provision.env`).
  Nota: los valores pasados por flag quedan visibles en `ps`/historial de
  shell; en hosts compartidos usa el asistente (los pide ocultos).
- `--skip-preflight` degrada los aborts del preflight a warnings (bajo tu
  responsabilidad; ver §0b).
- Re-ejecutable: siempre hace limpieza previa (`uninstall-all.sh --yes`).
- Si el grupo `lxd` no está activo en la sesión, aborta con `exit 100` →
  re-login y reejecutar.
- Los secretos generados **no se imprimen por stdout**: quedan en
  `/etc/provision/provision.env` (root:provision, 0640).
- **FASE 6 incluida:** amplía `stateless-pool` a 80GB y `lab-stateless` a /23,
  construye imágenes de apps (`build-apps/build-app-*.sh`), instala
  `nginx/iptables-apps.sh` y el timer `provision-reap-apps`. Los secretos
  adicionales (`ADMIN_JWT_SECRET`, `ADMIN_TOKEN`, `INTERNAL_TOKEN`,
  `ADMIN_TOTP_KEY`) se generan automáticamente.

Para **desinstalar todo**:

```bash
sudo bash uninstall-all.sh --domain=lab.example.com           # con confirmación
sudo bash uninstall-all.sh --yes --domain=lab.example.com    # sin confirmación
sudo bash uninstall-all.sh --purge-lxd --domain=lab.example.com  # + pools/redes/perfiles/proyectos
```

El resto del documento describe el despliegue **paso a paso** (manual),
útil para diagnóstico o cuando se quiere ejecutar una fase aislada.

## 0. Pre-requisitos del host

Un **Ubuntu Server 22.04/24.04 limpio** con acceso root basta:
`install-all.sh` instala todo lo demás (dos2unix, snapd, zfsutils, nginx,
certbot, docker.io, python3, iptables-persistent...).

- **Virtualización KVM** (`/dev/kvm`): VT-x/AMD-V en BIOS o nested KVM en el
  hipervisor. Sin esto el preflight **aborta** (las VMs LXD no arrancan).
- **Conectividad saliente** (snap, simplestreams, Docker, certbot, schema
  Guacamole 1.5.5).
- **DNS**: registro `A` apuntando `lab.<dominio>` a la IP pública del host
  (necesario para Let's Encrypt HTTP-01).
- **Firewall edge**: abrir `80/tcp` y `443/tcp` hacia el host. **No** abrir
  3389, 4822, 3306 ni 8000.
- **Cuenta SMTP** para magic links: Mailtrap (dev) o SendGrid/SES (prod).
- **Recursos mínimos** (tabla completa de cotas en el `README.md` §"Cotas
  de escalabilidad"):
  - `persistent-pool` 40GB → **≤2-3 alumnos** con snapshots k1..k5.
  - RAM: ~4GB por VM concurrente (el preflight avisa si <8GB total o
    <100GB libres en `/`).

### 0b. Preflight de `install-all.sh` (qué comprueba y cómo falla)

Antes de tocar nada, `install-all.sh` ejecuta un preflight fail-fast:

| Check | Acción si falla |
|---|---|
| SO Ubuntu 22.04/24.04 | **ABORT** |
| `/dev/kvm` presente | **ABORT** — habilita VT-x/AMD-V o virtualización anidada |
| Módulo `zfs` cargable (instala `zfsutils-linux` + `linux-modules-extra-$(uname -r)` si falta) | **ABORT** — en kernels cloud (`-kvm`/`-aws`) puede no existir el paquete de módulos extra: usa kernel `-generic` o `zfs-dkms`; log en `/var/log/lab-preflight-apt.log` |
| `snapd` instalado y sembrado (`snap wait system seed.loaded`, timeout 180s) | instala si falta; WARN si no siembra |
| Puertos 80/443 libres (u ocupados solo por nginx) | **ABORT** |
| DNS del `--domain` resuelve | WARN (el veredicto lo da certbot) |
| `ufw` activo | WARN (convive mal con las reglas iptables del proyecto) |
| RAM ≥8GB / disco ≥100GB | WARN |

Con `--skip-preflight` los ABORT se degradan a WARN ("bajo tu
responsabilidad"). Errores típicos:

- `exit 100` → el grupo `lxd` no está activo: cierra sesión, vuelve a entrar
  y re-ejecuta.
- certbot falla → revisa que el registro A del dominio apunte a este host y
  que 80/tcp esté abierto desde Internet.
- SMTP vacío → los magic links no se envían; rellena `MAILTRAP_USER/PASS` en
  `/etc/provision/provision.env` y `sudo systemctl restart provision`.

## 1. Preparar el repo en el servidor

```bash
git clone https://github.com/Coscollar/lxd-remote-web-desktops.git
cd lxd-remote-web-desktops

# Convertir CRLF → LF antes de ejecutar cualquier .sh
sudo apt update && sudo apt install -y dos2unix
for f in *.sh provision/*.sh guacamole/*.sh nginx/*.sh; do
  dos2unix "$f" 2>/dev/null || true
done
```

## 2. FASE 0 — Infra LXD + imagen base VM

```bash
sudo bash server-setup-lxd.sh
```

- Idempotente. En la **primera** ejecución aplica `lxd-preseed.yaml`
  (DESTRUCTIVO) y crea el flag `/var/lib/lab/.preseed-applied`.
- Para **recrear** la config del daemon intencionadamente:
  `sudo bash server-setup-lxd.sh --force-preseed`.
- Si el usuario no está en el grupo `lxd`, aborta con `exit 100` →
  **re-login** y volver a ejecutar.
- Construye `lab-vm-base` (MATE + xrdp). Si ya existe, SKIP (`rc=10`).
  Para reconstruir: `sudo bash build-lab-vm-base-mate.sh --force`.

### Validación FASE 0

```bash
lxc storage list && lxc network list && lxc profile list && lxc project list
lxc image list local --project labs          # lab-vm-base, ubuntu-22.04-vm/container
lxc profile show persistent --project labs | grep -E 'boot.autostart|security.devlxd'
lxc config show | grep -E 'trust_password|https_address'   # debe estar vacío
sudo bash server-setup-lxd.sh                 # re-ejecutable sin romper
```

## 3. FASE 1–3 — provision-api (auth + cloud-init + provisión on-demand)

### 3.1 Rellenar secretos

```bash
sudo cp provision/.env.example /etc/provision/provision.env   # si no existe aún
sudo chmod 0640 /etc/provision/provision.env
sudo chown root:provision /etc/provision/provision.env
sudo nano /etc/provision/provision.env
```

Obligatorios antes de arrancar:

| Variable | Cómo generar / valor |
|---|---|
| `JWT_SECRET`, `JWT_SECRET_PREV` | `openssl rand -hex 32` |
| `SERVICE_JWT_SECRET` | `openssl rand -hex 32` |
| `SMTP_PROVIDER`, `MAILTRAP_USER`, `MAILTRAP_PASS` | credenciales Mailtrap (dev) o reales (prod) |
| `PUBLIC_DOMAIN` | `lab.<tu-dominio>` |
| `ADMIN_TOKEN` | `openssl rand -hex 32` (para `/admin/*`) |
| `PROVISION_URL_VM` | `http://10.50.20.1:8000` (IP del host en `lab-persistent`, **no** 127.0.0.1) |

### 3.2 Instalar provision-api

```bash
sudo bash provision/install.sh
```

- Crea usuario `provision` (grupo `lxd`), venv en `/opt/provision/.venv`,
  copia código, instala units systemd y arranca `provision.service` +
  `provision-reap.timer`.
- Si `provision` acaba de entrar en el grupo `lxd`, reinicia el servicio
  para activarlo: `sudo systemctl restart provision`.

### 3.3 Sembrar matrícula (alumno → lab)

El lab se **deduce** del email, no lo elige el alumno. Insertar filas en
SQLite:

```bash
sudo sqlite3 /var/lib/provision/provision.db <<SQL
INSERT OR IGNORE INTO labs(nombre, imagen, activo) VALUES('lab1','local:lab-vm-base',1);
INSERT OR IGNORE INTO enrollments(alumno_id,email,lab,active,created_at)
  VALUES('alumno1','alumno@ejemplo.com','lab1',1,datetime('now'));
SQL
```

### Validación FASE 1–3

```bash
curl -s http://127.0.0.1:8000/healthz                       # {"status":"ok"}
systemctl status provision
journalctl -u provision -f

# Magic link (Mailtrap capturará el email):
curl -s -X POST http://127.0.0.1:8000/auth/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"alumno@ejemplo.com"}'
```

## 4. FASE 4 — Acceso web (Guacamole + guacd + Nginx)

### 4.1 Guacamole stack (Docker)

```bash
cd guacamole
sudo bash install.sh
cd ..
```

- Levanta `guacd`, `guacamole`, `mysql` en `network_mode: host` con bind
  `127.0.0.1`.
- Genera `.env` con passwords aleatorios (guárdalos fuera del repo).
- Importa el schema JDBC de Guacamole 1.5.5 (idempotente vía
  `.schema-imported`).

Validación:

```bash
docker ps --format '{{.Names}} {{.Ports}}' | grep guacd     # sin columna PORTS
curl -sI http://127.0.0.1:8080/guacamole/ | head -1
```

### 4.2 Nginx + certbot

```bash
sudo apt install -y nginx certbot
sudo bash nginx/install.sh lab.<tu-dominio> admin@<tu-dominio>
```

- Emite cert Let's Encrypt HTTP-01 (standalone, nginx parado), instala
  `lab.conf`, hook de renovación que valida `nginx -t` antes de reload.
- Genera `/etc/nginx/conf.d/lab-internal.conf` (0600) con la `map` de
  `$internal_token` leída de `INTERNAL_TOKEN` en
  `/etc/provision/provision.env`. **Requiere** por tanto haber ejecutado
  antes la instalación de provision-api con secretos (orden que ya respeta
  `install-all.sh`); aborta si el token falta o es <32 chars.

### 4.3 Aislamiento inter-VM (iptables)

```bash
sudo apt install -y iptables-persistent
sudo bash nginx/iptables-lab.sh
```

- DROP inter-VM en `lab-persistent`, ACCEPT host→VM:3389, defensa en
  profundidad por UID de guacd.
- Persiste con `netfilter-persistent`.

### Validación FASE 4

```bash
curl -kI https://lab.<tu-dominio>/guacamole/ | head -1       # 401 sin cookie
sudo ss -tlnp | grep 3389                                    # debe estar VACÍO
sudo iptables -L FORWARD -n | grep -E 'DROP|3389'
sudo certbot renew --dry-run
```

## 5. FASE 5 — Policy engine (snapshots + reaper)

Ya integrado en `provision/policy.py` y `provision/reap.py`. El timer
`provision-reap.timer` (cada 5 min) invoca `provision-reap.service`
(standalone, no HTTP).

Ajustar en `/etc/provision/provision.env`:

```
IDLE_MINUTES=60
COURSE_DEADLINE=2026-07-31
KEEP_SNAPSHOTS=5
CREATING_TIMEOUT=600
```

Reiniciar: `sudo systemctl restart provision`.

### Validación FASE 5

```bash
# Con una VM viva del alumno:
lxc info <lab>-<alumno> --project labs                       # base + k1..k5 tras /save
sudo systemctl start provision-reap.service                 # dispara reaper manual
journalctl -u provision-reap.service -e
```

## 6. FASE 6 — Portal web + apps stateless + consola admin

Integrada en `install-all.sh`. Si se hace paso a paso:

### 6.0 Fix preexistente (FASE 6.0)
- `systemd/provision.service`: `--host 0.0.0.0` (era 127.0.0.1) para que VMs
  y apps alcancen provision-api.
- iptables allowlist 8000 (127.0.0.1, 10.50.10.0/24, 10.50.20.0/24).
- Nginx `proxy_set_header X-Real-IP $remote_addr`.
- `lab_safe` redacta query de `/auth/verify` (token).
- `/docs` y `/openapi.json` deshabilitados en prod.

### 6.1 Auth admin + multi-lab (FASE 6.1)
- Rellenar secretos en `/etc/provision/provision.env`:
  `ADMIN_JWT_SECRET`, `ADMIN_JWT_SECRET_PREV`, `ADMIN_TOKEN`,
  `INTERNAL_TOKEN`, `ADMIN_TOTP_KEY` (generar con `openssl rand -hex 32`).
- Sembrar admins:
  ```bash
  sudo sqlite3 /var/lib/provision/provision.db \
    "INSERT OR IGNORE INTO admins(email,role,active,created_at)
     VALUES('admin@ejemplo.com','admin',1,datetime('now'));"
  ```

### 6.2 UI (FASE 6.2)
- Servida por FastAPI desde `/opt/provision/provision/web/` (rsync en
  `provision/install.sh`). No requiere paso manual.

### 6.3 Apps stateless infra (FASE 6.3)
```bash
# Ampliar pool + subred (no destructivo, NO --force-preseed)
lxc storage set stateless-pool size=80GB
lxc network set lab-stateless ipv4.address=10.50.10.1/23 --project labs
lxc network set lab-stateless ipv4.address=10.50.10.1/23 --project default

# Construir imágenes de apps
for f in build-apps/build-app-*.sh; do sudo bash "$f"; done

# Aislamiento iptables apps
sudo bash nginx/iptables-apps.sh
```

### 6.4 Apps stateless API (FASE 6.4)
- Integrada en `provision/install.sh` (schema, endpoints, job queue, reaper).
- Timer `provision-reap-apps` (OnUnitActiveSec=2min).
- Ajustar en `/etc/provision/provision.env`:
  ```
  APP_IDLE_MINUTES=30
  SHARED_IDLE_HOURS=6
  APP_CREATING_TIMEOUT=300
  GRACE_AFTER_RESTART=900
  MAX_APP_INSTANCES=40
  ALWAYS_ON_BUDGET_MB=8192
  APP_LAUNCH_SEM=6
  ```
- Reiniciar: `sudo systemctl restart provision`.

### 6.5 Web-gateway multi-ruta (FASE 6.5)
- `nginx/install.sh` instala `lab.conf` multi-ruta (locations + 3 auth_request).
- `limit_req_zone appuser` en `lab-log.conf`.

### Validación FASE 6
```bash
# Apps
lxc image list local --project labs | grep app-
lxc list ^app- --project labs

# Portal web
curl -kI https://lab.<dominio>/                          # 200 login
curl -kI https://lab.<dominio>/dashboard                 # 401 sin cookie, 200 con
curl -kI https://lab.<dominio>/admin                     # 401 sin admin_token, 200 con

# Aislamiento
sudo ss -tlnp | grep -E ':(3389|5900|3000|8888)'          # vacío
sudo iptables -L FORWARD -n | grep lab-stateless

# Servicios
systemctl is-active provision provision-reap-apps.timer nginx
```

## 7. Chequeo final end-to-end

```bash
# 1. Sin sesión → 401
curl -kI https://lab.<tu-dominio>/

# 2. Flujo completo alumno (ver docs/USO.md)
#    Email → magic link → cookie JWT → escritorio MATE en el navegador

# 3. 3389 nunca expuesto en el host
sudo ss -tlnp | grep 3389 || echo "OK: 3389 no escucha en el host"

# 4. guacd sin puertos publicados
docker ps --format '{{.Names}} {{.Ports}}' | grep guacd

# 5. Servicios activos
systemctl is-active provision provision-reap.timer nginx
docker compose -f guacamole/docker-compose.yml ps
```

## Deudas y límites conocidos (operación)

- **`persistent-pool` 40GB** → cota real **2-3 alumnos** con k1..k5. Para
  más: ampliar pool (recreación con `--force-preseed`) o reducir retención
  a `KEEP_SNAPSHOTS=3`.
- **SQLite single-writer** → ≤50 alumnos concurrentes. Migrar a Postgres
  por encima.
- **guacd en `network_mode: host`** (Opción A, dev/lab). Para prod
  multi-host: migrar a Opción C (socket Unix).
- **SMTP Mailtrap** en dev. En prod: SendGrid/SES + DKIM/SPF.
- **certbot HTTP-01** con dominio fijo. Subdominio por alumno requeriría
  wildcard DNS-01 (no aporta valor hoy: la identidad viene del JWT, no del
  subdominio).
- **`provision` en grupo `lxd`** ≈ root. Deuda: wrapper sudo whitelist de
  comandos `lxc`.
- **`stateless-pool` 80GB** (FASE 6) → cota ~60-80 contenedores. Para más:
  ampliar pool con `lxc storage set stateless-pool size=` (no destructivo).
- **`lab-stateless` /23** (FASE 6) → ~510 IPs. Para más: /22.
- **Apps per-alumno** (FASE 6) satura RAM (2GB/app). Cota real: ~10-12
  concurrentes pool-wide en host 32GB. Shared por defecto.
- **Egress filtering de apps** (FASE 6, NAT saliente): deuda prod
  (squid + allowlist de dominios).
- **Subdominio por app** (FASE 6) con wildcard DNS-01: deuda si se quiere
  aislar cross-origin sin sandbox.
- **`limit_req_zone appuser`** usa `$lab_alumno`, que solo se define vía
  `auth_request_set` en `/desktop/`; en la location de apps la key queda
  vacía → el rate-limit por alumno es hoy inefectivo en apps (deuda: usar
  una variable poblada por `/verify_app`).
- **Purga de histórico**: las filas `estado='destruida'`
  (instancias/app_instances) y los `jobs` terminados no se purgan nunca
  (crecimiento lento de SQLite; deuda: tarea de retención).
- **DELETE /admin/apps** con muchas instancias encola N jobs con N commits
  individuales (aceptable a esta escala; deuda: INSERT batch).
- **Budget always_on**: la revalidación de `ALWAYS_ON_BUDGET_MB` en
  POST/PATCH de apps se hace fuera de la transacción del UPDATE (ventana
  TOCTOU teórica entre dos admins concurrentes; irrelevante con un solo
  admin operando).

## Recreación intencionada de la infra LXD (destructiva)

```bash
sudo bash server-setup-lxd.sh --force-preseed
```

⚠️ Machaca toda la config del daemon LXD. Solo para recreación planificada;
haz snapshot/backup antes.

## Desinstalación completa

```bash
# Con confirmación interactiva:
sudo bash uninstall-all.sh --domain=lab.example.com

# Sin confirmación (automatización):
sudo bash uninstall-all.sh --yes --domain=lab.example.com

# Incluye pools ZFS, redes, perfiles y proyectos LXD (NO desinstala el snap):
sudo bash uninstall-all.sh --purge-lxd --domain=lab.example.com
```

Elimina: servicios systemd (incluido `provision-reap-apps`), instancias e
imágenes LXD (incluidas `app-*`), stack Docker Guacamole, site Nginx, reglas
iptables (incluidas iptables-apps y allowlist 8000), certs certbot, usuario
`provision` y directorios. **No** desinstala paquetes del sistema (nginx,
docker, certbot, snap LXD) ni el repo en disco. **No** revierte la ampliación
de pool/subred (ZFS shrink peligroso; /23 no perjudica). Usa `--purge-lxd`
para eliminar pools completamente. Ver `docs/USO.md` para desinstalar
paquetes del sistema manualmente.

---

# Anexo A — Contrato de renderización de `cloud-init-template.yml`

Define cómo `provision-api` renderiza la plantilla `cloud-init-template.yml`
al lanzar una VM de alumno. La plantilla **no** se procesa por cloud-init tal
cual: está escrita en **Jinja2** y provision-api la compila a un
`#cloud-config` YAML válido antes de inyectarla como `user.user-data`.

## A.1 Por qué Jinja2 (y no `${}` nativo)

cloud-init soporta `${VAR}` solo en contadas claves y no permite condicionales.
Necesitamos omitir `packages:` cuando el lab no aporta delta, omitir `sudo:`
cuando `SUDO_MODE` es vacío, y omitir `ssh_authorized_keys` cuando no hay
claves. Eso exige `{% if %}`/`{% for %}`, que solo Jinja2 (o equivalente)
provee. Por tanto la plantilla es Jinja2 y provision-api es el único renderer.

## A.2 Variables interpolables

| Variable | Tipo | Origen | Validación |
|---|---|---|---|
| `ALUMNO` | str | JWT del alumno (claim `sub`) | `^[a-z0-9][a-z0-9-]{1,30}$` |
| `LAB` | str | ruta/claim del lab | `^[a-z0-9][a-z0-9-]{1,30}$` |
| `PROVISION_URL_VM` | str (URL) | config del host | `http://10.50.20.1:8000` (IP del host en bridge `lab-persistent`). **Nunca** `127.0.0.1` ni `localhost`: la VM no ve el loopback del host. |
| `LAB_SERVICE_TOKEN` | str (secret) | tabla `vm_tokens` | no vacío; se inyecta en `/etc/lab/identity` (0640 root:root) |
| `SUDO_MODE` | str | config del lab | uno de: `ALL=(ALL) NOPASSWD:ALL`, `ALL=(ALL) ALL`, o vacío (sin sudo). Si vacío, la clave `sudo:` se omite. |
| `SSH_AUTHORIZED_KEYS` | list[str] | config del lab | lista de claves públicas OpenSSH. Si vacía, la clave `ssh_authorized_keys:` se omite. |
| `LAB_PACKAGES` | list[str] | config del lab | delta de paquetes del lab. **No** incluir MATE/xrdp/ssh (ya en `lab-vm-base`). Si vacía, la clave `packages:` se omite. |
| `TIMEZONE` | str | config del lab | tzdata válida (ej. `Europe/Madrid`). |

## A.3 Mecanismo de render

1. provision-api carga `cloud-init-template.yml` desde el repo (path fijado
   en config).
2. Construye el contexto con las variables de la tabla, validadas previamente.
3. Renderiza con Jinja2 (`autoescape=False` porque producimos YAML, no HTML;
   pero las variables se escapan como literales YAML entre comillas dobles
   donde corresponda — `sudo`, `content` de `/etc/lab/identity`).
4. **Whitelist estricta**: rechazar el render si cualquier variable falla su
   regex/enum. En particular `SUDO_MODE` debe estar en el conjunto cerrado de
   tres valores o vacío; cualquier otra cosa aborta el lanzamiento.
5. Parsea el resultado con `yaml.safe_load` y verifica que empieza por
   `#cloud-config` y que las claves top-level son un subconjunto conocido
   (`users`, `hostname`, `manage_etc_hosts`, `fqdn`, `package_update`,
   `packages`, `write_files`, `runcmd`, `timezone`). Si no parsea, abortar.
6. Pasa el YAML renderizado **por stdin** a:
   ```
   lxc launch local:lab-vm-base <alumno>-<lab> --vm \
     -p persistent --project labs \
     -c user.user-data=-
   ```
   El render se envía por stdin al proceso `lxc`, **no** como argumento shell.
   Esto evita inyección de flags y límites de longitud de línea de comandos.

## A.4 Qué NO hacer

- **No commitear el render.** El YAML con el token real nunca se escribe a
  disco en el repo ni en el host. Se pasa in-memory al `lxc launch`.
- **No usar `127.0.0.1` ni `localhost`** como `PROVISION_URL_VM`. La VM vive
  en su propio namespace de red (`lab-persistent`, 10.50.20.0/24); el
  loopback del host no es alcanzable. Usar la IP del host en ese bridge (por
  defecto `10.50.20.1`).
- **No usar `package_upgrade: true`.** Rompe idempotencia: en una
  re-aplicación de cloud-init cambiaría versiones de paquetes base y podría
  desincronizar con el snapshot base. Solo `package_update: true` (refresca
  índices APT).
- **No incluir `chpasswd`**, `ssh_pwauth: true` ni `final_modules: []`.
  Modelo A: sin password RDP conocida; el autologin lo gestiona `lab-vm-base`.
- **No reinstalar** MATE, xrdp, ssh, ni ningún paquete ya presente en
  `lab-vm-base`. `LAB_PACKAGES` es **delta** del lab.
- **No pasar `user.user-data` como argumento** al `lxc launch` (riesgo de
  inyección de flags y truncamiento). Siempre stdin (`-c user.user-data=-`).
- **No renderizar sin validar**. Cualquier fallo de regex/enum aborta el
  lanzamiento antes de tocar LXD.

## A.5 Idempotencia y guardián

El `runcmd` está envuelto en un guardián: si existe `/etc/lab/.provisioned`,
el bloque entero se omite. Al final, se escribe
`sha256sum /etc/lab/identity > /etc/lab/.provisioned`. Esto permite detectar
cambios de plantilla/token: si provision-api re-aplica cloud-init con un token
distinto, el sha cambia y el operador puede forzar re-provisionado borrando el
guardián. En operación normal, una re-aplicación de cloud-init es no-op.

## A.6 Cloud-init de apps stateless (opcional)

Las apps stateless usan **imagen preconstruida** (`local:app-<id>`) por
defecto, sin cloud-init. Si una app necesita config runtime (token del
alumno, binding de puerto, `PROVISION_URL_APP`), se pasa un cloud-init mínimo
vía stdin:

```bash
lxc launch local:app-<id> <nombre> -p stateless --project labs -c user.user-data=-
```

Si la app recibe cloud-init, **debe** esperar `cloud-init status --wait`
(timeout 120s) antes del healthcheck HTTP. Decisión binaria: o la app es 100%
preconstruida (sin cloud-init, healthcheck HTTP basta), o recibe cloud-init
(entonces wait). No hay término medio silencioso. Variables interpolables:
`APP_SERVICE_TOKEN`, `PROVISION_URL_APP` (`http://10.50.10.1:8000`), config
específica de la app. Tampoco se commitea nunca un render.

## A.7 Validación manual del render

```bash
lxc launch local:lab-vm-base test-alumno-lab1 --vm \
  -p persistent --project labs -c user.user-data=- < rendered.yml

lxc exec test-alumno-lab1 -- cloud-init status --wait      # status: done
lxc exec test-alumno-lab1 -- systemctl is-active xrdp       # active
lxc exec test-alumno-lab1 -- cat /etc/lab/.provisioned      # existe (sha256)

# Limpieza:
lxc delete test-alumno-lab1 --force --project labs
```

---

# Anexo B — Gateway web en detalle (Guacamole + guacd + Nginx)

La topología y la tabla de puertos están en el `README.md` §"Arquitectura".
**Regla de oro:** guacd SIEMPRE intermedio para RDP/VNC. El navegador nunca
alcanza `3389` ni `5900`. Nginx enruta a Guacamole (8080) solo para
`/desktop/{lab}/`, nunca a guacd ni a las VMs. Las apps stateless son HTTP
directo (no usan guacd).

## B.1 Opción A (dev/lab) vs Opción C (deuda prod)

- **Opción A (actual):** guacd, guacamole y mysql en `network_mode: host`,
  bind estricto `127.0.0.1`. guacd con `cap_drop: [ALL]` y
  `security_opt: [no-new-privileges]`. Suficiente para un host único.
- **Opción C (deuda prod):** guacd nativo con socket Unix en lugar de TCP
  4822, y Guacamole en su propia red Docker (no host). Reduce superficie
  de loopback y elimina el puerto TCP. Migrar cuando se multiplique el
  número de hosts o se aísle Guacamole por tenant.

## B.2 certbot: HTTP-01 vs wildcard DNS-01

- **HTTP-01 (actual):** host único `lab.<dominio>`. certbot sirve
  `/.well-known/acme-challenge/` en :80. Suficiente y simple.
- **DNS-01 (wildcard, futuro):** si se pasa a un subdominio por alumno
  (`<alumno>.lab.<dominio>`), HTTP-01 por host deja de escalar. DNS-01
  con wildcard `*.lab.<dominio>` + un único cert. Requiere plugin de DNS
  provider y credenciales fuera del repo. **No adoptar hasta que la
  identidad deje de venir del JWT** — hoy el subdominio no identifica al
  alumno, así que un wildcard no aporta valor y sí complejidad.

## B.3 Proxy de apps stateless

Las apps (contenedores LXD, perfil `stateless`) exponen HTTP en un puerto
interno. Nginx proxya vía path prefix `/apps/{app_id}/`:

1. `auth_request /verify/app` (READ-ONLY): valida JWT + pertenencia
   app↔alumno (app_lab↔enrollments) + IP ∈ 10.50.10.0/23. Devuelve
   `X-App-Target: <ip>:<puerto>`.
2. `auth_request_set $app_target $upstream_http_x_app_target`.
3. `proxy_pass http://$app_target` (con `resolver` y `valid=1s ipv6=off`).
4. `X-Forwarded-Prefix: /apps/{app_id}` para que la app genere URLs correctas.
5. WebSocket reusa `map $http_upgrade $connection_upgrade`.

**Cross-tenant:** `/verify/app` valida que `app_id ∈ apps_del_alumno`. Un
alumno no puede abrir `/apps/{app_de_otro}/`. `X-App-Target` lo genera
provision-api (upstream), no el cliente (anti-SSRF). La API que consume el
dashboard del alumno viaja bajo `/api/apps/*` (no bajo `/apps/`, que es el
proxy al contenedor).

## B.4 Contrato provision-api ↔ Guacamole

- Tras `healthcheck_rdp` OK, provision-api escribe en la DB JDBC de
  Guacamole una conexión `<alumno>-<lab>` con `hostname=<vm-ip>`,
  `port=3389`, `username=alumno`, `ignore-cert=true`, `security=any`,
  **sin password** (Modelo A: autologin en la imagen base; el alumno no se
  loguea dos veces).
- IP dinámica: provision-api reescribe `hostname` tras cada healthcheck
  dentro de la transición a estado `lista`.
- En `destroy`: `DELETE` de la conexión y del usuario Guacamole asociado.
- `/verify` devuelve `200` + `X-Lab-Alumno`/`X-Lab-Name`/`X-Lab-Scope` si el
  JWT es válido y la matrícula sigue activa; `401` en caso contrario (Nginx
  corta antes de llegar a Guacamole).
- `/verify/app` (READ-ONLY): **no escribe `last_seen`** (lo hace el
  heartbeat de la app, como las VMs).
- `/admin/verify`: valida cookie `admin_token` + role admin. Devuelve
  `X-Lab-Role: admin` + `X-Admin-Email`.

## B.5 Logging seguro

- `log_format lab_safe` SIN `$http_cookie`.
- Redacción de query: `lab_safe` usa `$loggable_request` (no `$request`) vía
  `map $request_uri` para no loguear el token de los magic links
  (`/auth/verify`, `/admin/auth/verify`).
- **No loguear** `X-App-Target` (filtra IPs internas 10.50.10.x) ni
  `X-Internal` (secreto compartido).
- uvicorn (provision-api) con filtro de logging que redacta `Authorization`,
  `Cookie`, `X-Internal`, `X-Admin-Token`.

## B.6 Validaciones del gateway

```bash
curl -kI https://lab.<dominio>/guacamole/ | head -1   # 401 sin cookie
docker ps --format '{{.Names}} {{.Ports}}' | grep guacd   # sin columna PORTS
sudo iptables -L FORWARD -n | grep -E 'DROP|3389'
sudo ss -tlnp | grep 3389                              # vacío
sudo certbot renew --dry-run
# Conexiones runtime en Guacamole:
docker compose exec -T mysql \
  mysql -h127.0.0.1 -uroot -p"$GUAC_MYSQL_ROOT" guacamole \
  -e "SELECT connection_name, hostname FROM guacamole_connection;"
```

---

# Anexo C — Policy engine en detalle (snapshots, reset, auto-destrucción)

Módulo: `provision/policy.py` (VMs) + `provision/reap.py` (reapers). Solo
las **VMs persistentes** reciben snapshots nativos LXD; los contenedores
stateless son efímeros (reset = destroy + recreate).

## C.1 Esquema de snapshots y rotación FIFO

| Tag        | Cuándo se crea                                  | Inviolable |
|------------|-------------------------------------------------|------------|
| `base`     | Tras `cloud-init status --wait` + `healthcheck_rdp` OK | Sí   |
| `k1..k5`   | Bajo demanda del alumno vía `POST /save`        | No (FIFO)  |

Source of truth = **LXD** (`instances.list_snapshots`), no un contador en BD
(evita desincronización si el servicio reinicia o un snapshot se borra a
mano). Al recibir `POST /save`: listar snapshots reales, filtrar `k1..k5`,
si `len >= keep` purgar el más viejo, y elegir el primer `kN` libre. Un `k3`
borrado manualmente se reutiliza en el siguiente `/save`.

## C.2 Pool guard reactivo

`persistent-pool` es ZFS sobre loop file de **40GB** → cota real ≤2-3
alumnos con retención k1..k5:

| Uso del pool | Acción                                              |
|--------------|-----------------------------------------------------|
| > 90%        | `503` — no se crea snapshot (ni se lanza VM nueva; la decisión de no lanzar vive en `jobs.py`) |
| > 75%        | Purgar el oldest **antes** de crear (despresurizar) |
| > 60%        | Reducir retención a `k1..k3` (`KEEP_LOW=3`)         |
| ≤ 60%        | Retención nominal `k1..k5`                          |

`pool_usage_ok()` es fail-closed: si no puede leer el pool, devuelve `False`.

## C.3 Reset y restore

**Reset** = `lxc restore <instancia> base` (NO destroy + recreate; una
instancia por (alumno, lab)). Secuencia: precheck de que `base` existe (si
no, `409`) → `stop --force` → `restore base` → `start` → `healthcheck_rdp`.
`restore_tag` es igual con tag validado contra `^(base|k[1-5])$` (`404` si
no existe).

## C.4 Auto-destrucción (reaper VMs)

Tres criterios configurables vía `.env`:

| Criterio              | Variable          | Comportamiento                                  |
|-----------------------|-------------------|--------------------------------------------------|
| Inactividad           | `IDLE_MINUTES=60` | `last_seen < now - IDLE_MINUTES`                 |
| Deadline del lab      | `labs.deadline`   | Fecha límite por lab (en BD)                     |
| Fin de curso          | `COURSE_DEADLINE` | Fecha global `YYYY-MM-DD` (vacío = sin deadline) |

`last_seen` se actualiza por `POST /heartbeat` (la VM llama cada 5 min vía
`lab-heartbeat.timer`). `CREATING_TIMEOUT` (default 600s) caduca instancias
estancadas en `creando`; el alumno puede relanzar vía `/lab/start`.

`provision/reap.py` es un **proceso standalone** invocado por systemd timer
(`provision-reap.timer`, cada 5 min), NO un endpoint HTTP al worker único.
Algoritmo anti-TOCTOU:

1. **Fase 1 (autocommit, WAL):** `SELECT` de candidatos por `idle_sec`
   calculado con `datetime('now')` de SQLite (consistente ante saltos de
   reloj).
2. **Fase 2 (por candidato):** `BEGIN IMMEDIATE` + re-check de estado e
   `idle_sec` **dentro** de la transacción. Si un `/heartbeat` o
   `/lab/start` lo actualizó, `ROLLBACK` y skip. Si sigue cumpliendo:
   `UPDATE estado='destruida'` + limpieza de tokens, `COMMIT`, y **fuera**
   de la tx `instances.delete` (idempotente).
3. **Batch deletes** en lotes con pausa entre lotes (no saturar LXD).

## C.5 Reconciliación al arranque

`reconcile_dry_run()` (en `lifespan`) compara BD vs LXD: instancias en BD
ausentes en LXD se marcan `error`. **Nunca** `lxc delete` ciego en arranque
(destruiría VMs legítimas tras un reinicio del servicio).

## C.6 Apps stateless — lifecycle

- **Shared vs per-alumno:** `shared=1` = 1 instancia para todo el lab
  (`always_on=1` siempre viva; `always_on=0` se reap tras
  `SHARED_IDLE_HOURS=6`). `shared=0` = 1 por alumno, reap tras
  `APP_IDLE_MINUTES=30`.
- **Lanzamiento** siempre vía job queue: `launch_container()` (sin `--vm`,
  perfil `stateless`) → `healthcheck_http` (HTTP real) → `get_ip` →
  `issue_app_token` → `estado='lista'`. `worker_heartbeat` cada 10s permite
  al reaper distinguir `creando` activo de estancado. Semáforo de
  lanzamientos concurrentes. En fallo: cleanup + `estado='error'`.
- **Reaper apps** (`provision-reap-apps.timer`, cada 2 min): per-alumno
  inactiva, shared `always_on=0` inactiva, shared `always_on=1` solo si la
  app está desactivada (`activo=0`), `creando`/`destruyendo` estancadas.
  **Grace period tras reinicio** (`GRACE_AFTER_RESTART=15min`) para no
  masacrar apps legítimas. Delete con retry y clasificación de error
  (not-found = éxito).
- **Pool guard `stateless-pool`** generalizado (cache 30s, fail-closed con
  cache): >90% → 503; >75% → purgar apps inactivas oldest (nunca shared
  `always_on=1`); >60% → reaper agresivo. Budget preventivo por RAM + hard
  cap `MAX_APP_INSTANCES`.
- **Reset app** = destroy + recreate. Per-alumno: el alumno propietario.
  Shared: **solo admin** (afecta a todos).
- **Reconciliación apps al arranque** (asíncrona tras `yield`, nunca bloquea
  el boot): huérfanas → `destruida`/`error`; shared `always_on=1` ausente →
  encolar job de auto-heal (respetando `ALWAYS_ON_BUDGET_MB`). NUNCA delete
  ciego.

## C.7 Endpoints delegados en policy

| Endpoint                  | Delega en                | Respuesta         |
|---------------------------|--------------------------|-------------------|
| `POST /save`              | `policy.snapshot_save`   | `200 {tag}` / `503` |
| `POST /reset`             | `policy.reset_to_base`   | `200` / `409`     |
| `POST /restore?tag=k2`    | `policy.restore_tag`     | `200` / `404`     |
| `GET /snapshots`          | `instances.list_snapshots` | `200 {snapshots}` |
| `POST /admin/reap`        | `reap.reap_stale`        | `200 {destruidas}` |
| `POST /api/apps/{id}/reset` | destroy + recreate     | `200` / `403` (shared no admin) |

La VM invoca estos endpoints vía `curl` desde `lab-save`/`lab-reset` con su
service token (HS256, `scope=save|reset|heartbeat`, IP origen validada).
Nunca ejecuta `lxc` directamente.

## C.8 Validación del policy engine

```bash
# VM viva → 5× POST /save → lxc info muestra k1..k5; el 6º purga k1 (FIFO).
lxc info <lab>-<alumno> --project labs
# IDLE_MINUTES=1 → esperar → systemctl start provision-reap.service → destruida.
# Pool guard: pool >90% → /save devuelve 503; >75% purga oldest; >60% retención k1..k3.
# App per-alumno inactiva → systemctl start provision-reap-apps.service → destruida.
# App shared always_on=1 → reiniciar provision → auto-heal la relanza (asíncrono).
# Reset app shared sin admin → 403.
```