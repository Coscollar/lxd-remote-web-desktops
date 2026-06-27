# Despliegue del Entorno de Laboratorio con LXD

Guía de despliegue del host completo (FASES 0–5). El repo se edita desde
Windows (CRLF); los scripts abortan si detectan CRLF, así que hay que
convertirlos a LF antes de ejecutarlos.

> Nota: el script de setup en disco se llama `server-setup-lxd.sh` (un
> comentario interno aún referencia `1-server-setup-lxd.sh`).

## Despliegue en un comando (recomendado)

El entrypoint único es `install-all.sh`: desinstala cualquier instalación
previa, instala dependencias del sistema, y ejecuta todas las fases
(0→5) generando secretos automáticamente.

```bash
git clone https://github.com/Coscollar/lxd-remote-web-desktops.git
cd lxd-remote-web-desktops
sudo bash install-all.sh --domain=lab.example.com --email=admin@example.com \
     [--smtp-user=xxx --smtp-pass=yyy]
```

- `--domain` y `--email` son **obligatorios**.
- `--smtp-user` / `--smtp-pass` opcionales (si se omiten, se deja Mailtrap
  sin credenciales para rellenar a mano en `/etc/provision/provision.env`).
- Re-ejecutable: siempre hace limpieza previa (`uninstall-all.sh --yes`).
- Si el grupo `lxd` no está activo en la sesión, aborta con `exit 100` →
  re-login y reejecutar.

Para **desinstalar todo**:

```bash
sudo bash uninstall-all.sh --domain=lab.example.com           # con confirmación
sudo bash uninstall-all.sh --yes --domain=lab.example.com    # sin confirmación
sudo bash uninstall-all.sh --purge-lxd --domain=lab.example.com  # + pools/redes/perfiles/proyectos
```

El resto del documento describe el despliegue **paso a paso** (manual),
útil para diagnóstico o cuando se quiere ejecutar una fase aislada.

## 0. Pre-requisitos del host

- **Ubuntu Server LTS** (22.04 o 24.04) con acceso root/sudo.
- **Conectividad saliente** (snap, simplestreams, Docker, certbot, schema
  Guacamole 1.5.5).
- **DNS**: registro `A` apuntando `lab.<dominio>` a la IP pública del host
  (necesario para Let's Encrypt HTTP-01).
- **Firewall edge**: abrir `80/tcp` y `443/tcp` hacia el host. **No** abrir
  3389, 4822, 3306 ni 8000.
- **Cuenta SMTP** para magic links: Mailtrap (dev) o SendGrid/SES (prod).
- **Recursos mínimos** (cota documentada en `docs/policy.md` §7):
  - `persistent-pool` 40GB → **≤2-3 alumnos** con snapshots k1..k5.
  - RAM: ~4GB por VM concurrente.

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

## 6. Chequeo final end-to-end

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

Elimina: servicios systemd, instancias e imágenes LXD, stack Docker
Guacamole, site Nginx, reglas iptables, certs certbot, usuario
`provision` y directorios. **No** desinstala paquetes del sistema (nginx,
docker, certbot, snap LXD) ni el repo en disco. Ver `docs/USO.md` para
desinstalar paquetes del sistema manualmente.