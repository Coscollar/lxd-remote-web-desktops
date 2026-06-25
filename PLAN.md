# PLAN DE IMPLEMENTACIÓN — Entorno de Laboratorio con LXD

> Generado por `lab-plan` (revisión v2), analizado por los subagentes de dominio (`@infra-lxd`, `@vm-base-builder`, `@cloud-init-author`, `@provision-api`, `@web-gateway`, `@policy-engine`, `@auth-designer`) y auditado por los críticones (`@critic-security`, `@critic-idempotency`, `@critic-reliability`, `@critic-scalability`, `@critic-lxd-conventions`). Aprobado por el usuario. Ejecutado por `lab-build`.
>
> **Premisa de la revisión v2:** lo ya implementado puede rehacerse o modificarse. Esto desbloquea correcciones estructurales en FASE 0 y FASE 2 que la v1 asumía congeladas.

## Estado actual (consolidado)

| Recurso | Estado real | Veredicto |
|---|---|---|
| Pools ZFS (`stateless-pool` 20GB, `persistent-pool` 40GB) | Definidos en preseed **y** script (duplicados) | Válido, fuente de verdad ambigua — corregir en FASE 0 |
| Redes (`lab-stateless`, `lab-persistent`, `admin-net`) | Solo en preseed (proyecto `default`) | OK, pero **no existen en `labs`** (features.networks=true aísla) |
| Perfiles (`stateless`, `persistent`, `admin`) | Solo en preseed (proyecto `default`) | **Incompleto**: no existen en `labs` (features.profiles=true) |
| Proyectos (`default`, `test`, `labs`) | `labs` con features.images/networks/profiles | OK, catálogos aislados no resueltos |
| Imágenes (`ubuntu-22.04-vm`, `ubuntu-22.04-container`) | Copiadas a `default`, **no a `labs`** | **Bug**: builder/provision-api operan en `labs` y no las ven |
| `lab-vm-base` | Publicada en `labs` (según builder) | Funcional pero frágil (`sleep 30`, sin `cloud-init clean`) |
| `cloud-init-template.yml` | Vacío | Pendiente (FASE 2) |
| `provision/`, web-gateway, policy-engine | No existen | Pendientes (FASES 3, 4, 5) |

### Hallazgos bloqueantes detectados por los críticos
- `newgrp lxd` en subshell no persiste → `lxc` sin sudo falla en primera ejecución.
- Imágenes copiadas a `default` pero builder/provision-api operan en `labs` (catálogo aislado por `features.images=true`).
- Perfiles y redes **no existen en `labs`** → `lxc launch -p persistent --project labs` falla.
- `sleep 30` frágil + sin `cloud-init clean --logs` → VMs hijas no ejecutan cloud-init por alumno.
- `trust_password: "123456"` + `core.https_address: 127.0.0.1:50000` exponen API LXD en TCP.
- `persistent-pool` 40GB → cota real **≤2-3 alumnos** con snapshots k1..k5.

## Decisiones firmadas (no se vuelven a discutir)

- **LXD** no se sustituye; config base (preseed/pools/redes/perfiles) no se re-carga salvo recreación intencionada con `--force-preseed`. Ajustes incrementales vía `lxc` CLI.
- **Proyecto `labs`** es el único destino de instancias de alumnos; perfiles, redes e imágenes deben propagarse a `labs` (catálogos aislados por `features.*`).
- **provision-api** corre en el host como servicio systemd, usuario `provision` en grupo `lxd`, invoca `lxc` vía `asyncio.create_subprocess_exec` (no `subprocess.run` bloqueante, no REST LXD, no `trust_password`).
- **Auth**: magic link por email + JWT HS256 en cookie httpOnly. **Modelo A** (sin password RDP conocida por el alumno): xrdp autologin/guest, la identidad del alumno vive solo en el edge (JWT), la VM no la conoce.
- **Service token de VM** (`SERVICE_JWT_SECRET` separado): HS256, claims `{sub=instancia, scope=save,reset,heartbeat}`, rotación por heartbeat, validación de IP origen exacta (no solo rango).
- **Guacamole+guacd** vía `docker-compose`. guacd SIEMPRE intermedio (regla de oro). Opción A (host network, dev/lab) con hardening; Opción C (guacd nativo socket) como deuda prod.
- **Reset** = `lxc restore <instancia> base` (no destroy+recreate), con precheck de existencia de `base`.
- **Reaper** = proceso standalone invocado por systemd timer (no HTTP al worker único), `Persistent=true`, `BEGIN IMMEDIATE` + re-check.
- **SMTP Mailtrap** en dev/lab; SendGrid/SES en prod; Postfix documentado pero no v1.
- **certbot** dominio fijo `lab.<dominio>` vía HTTP-01 (dev); wildcard `*.lab.<dominio>` con DNS-01 documentado como prod.
- **Commits**: `lab-build` no commitea nada; el usuario gestiona los commits.

## Orden de ejecución

```
FASE 0 (consolidación infra + builder) ──┐
   ├─ FASE 1 (auth magic link + JWT)      │
   ├─ FASE 2 (cloud-init por alumno) ◀────┤  depende de FASE 0 (cloud-init clean)
   ├─ FASE 3 (provision-api) ◀────────────┤  depende de FASE 1, 2
   ├─ FASE 4 (web-gateway) ◀───────────────┤  depende de FASE 3
   └─ FASE 5 (policy-engine) ◀────────────┘  depende de FASE 3
```

> Reordenación respecto al roadmap original: **auth (FASE 1) se adelanta** porque provision-api y web-gateway dependen del contrato JWT. Cloud-init (FASE 2) requiere que el builder deje cloud-init limpio.

## Mitigaciones críticas incorporadas (de los críticones)

- **Secrets fuera del repo**: ampliar `.gitignore` ANTES de crear `.env`.
- **`trust_password` + `https_address` TCP**: `lxc config unset` en FASE 0 + quitar del preseed (documentación).
- **Perfiles/redes en `labs`**: `lxc profile copy` + `lxc network create --project labs` en FASE 0.
- **`newgrp` subshell**: validar membresía con `id -nG` + abortar pidiendo re-login (no `newgrp` en scripts).
- **Preseed con guardián fail-closed**: solo carga con `--force-preseed` explícito; flag `lab.preseed-applied`.
- **Pools fuente única**: eliminar `lxc storage create` del script (pools vienen del preseed).
- **`grep` exacto**: `--format csv --columns a | grep -qx` (no substring).
- **Builder robusto**: `cloud-init clean --logs --machine-id` + `rm /var/lib/cloud/instances/*` + `rm /etc/ssh/ssh_host_*` + espera agente con timeout + `cloud-init status --wait` + validar `status: done` + smoke test xrdp + `trap cleanup EXIT INT TERM` + `--force` + alias dual.
- **Inyección en `lxc`**: `asyncio.create_subprocess_exec` (no `shell=True`) + whitelist `^[a-z0-9][a-z0-9-]{1,30}$` (nombres) y `^(base|k[1-5])$` (tags) + autorización por JWT.
- **Idempotencia snapshots**: source of truth = LXD (`lxc info`), precheck atómico antes de crear `base`/`k<n>`.
- **One instance per alumno-lab**: `UNIQUE(alumno,lab)` + `ON CONFLICT DO UPDATE SET estado='creando' WHERE estado IN ('destruido','error')`.
- **Inventario NEVER destroys ciego**: reconciliación dry-run por defecto en `ExecStartPre`; borrado solo con `--apply` + `SELECT count(*)>0` + grace period 10min.
- **Mutex concurrencia**: `BEGIN IMMEDIATE` + `estado='creando'` + `PRAGMA busy_timeout=5000`.
- **Job queue persistente**: tabla `jobs` + worker dedicado en `lifespan` (no `BackgroundTasks` que se pierden en restart).
- **Healthcheck antes de devolver RDP**: `systemctl is-active xrdp xrdp-sesman` + probe TCP 3389 con retries.
- **`cloud-init status --wait`** envuelto en `timeout 300` + validar `status: done` literal.
- **Auto-destroy via systemd timer externo** (proceso standalone, no HTTP), `Persistent=true`, `RandomizedDelaySec=30s`.
- **SQLite**: WAL + `busy_timeout=5000` + tabla `heartbeats` separada + batch reaper `DELETE LIMIT 50`.
- **Guacd aislamiento**: host network con `--cap-drop=ALL --security-opt no-new-privileges`; iptables inter-VM DROP + ACCEPT con source `10.50.20.1` (host en bridge) + `-m owner --uid-owner <guacd_uid>`.
- **Cross-tenant**: identidad solo desde JWT vía `auth_request_set` (no del subdominio); Nginx sobreescribe siempre `Remote-User`.
- **JWT**: `algorithms=["HS256"]` forzado, cookie `HttpOnly+Secure+SameSite=Lax` (corrección sobre Strict: el clic desde email es cross-site), token sha256 almacenado, rate-limit `5/min per IP, 3/10min per email`, `/lab/status` excluido del rate-limit global.
- **Pool guard reactivo**: >60% → k1..k3, >75% → purgar oldest, >90% → 503.
- **Cotas numéricas** documentadas en `DOIN.md`.

---

## FASE 0 — Consolidación de infra y builder (REHACER)

**Objetivo:** dejar `1-server-setup-lxd.sh` y `build-lab-vm-base-mate.sh` idempotentes, robustos y seguros, y propagar perfiles/redes/imágenes al proyecto `labs`.

**Agentes:** `@lab-build` ejecuta; `@infra-lxd`, `@vm-base-builder` diseñan; `@critic-security`, `@critic-idempotency`, `@critic-lxd-conventions`, `@critic-reliability` revisan.

### 0.1 Ampliar `.gitignore` (antes de crear ningún secret)
```
.env
.env.*
!.env.example
*.pem
*.key
/secrets/
/certbot/
guacamole/user-mapping.xml
provision/provision.db
provision/*.db
```

### 0.2 Fix `newgrp lxd` en `1-server-setup-lxd.sh`
No usar `newgrp` en subshell (no persiste). Validar membresía y abortar pidiendo re-login:
```bash
if ! id -nG | tr ' ' '\n' | grep -qx lxd; then
  sudo usermod -aG lxd "$USER"
  echo "Re-login requerido para activar grupo lxd"; exit 100
fi
```

### 0.3 Guardián preseed fail-closed
Solo carga el preseed con `--force-preseed` explícito:
```bash
if [ ! -f /var/lib/lab/.preseed-applied ] && [ "${1:-}" != "--force-preseed" ]; then
  sudo lxd init --preseed < ./lxd-preseed.yaml
  sudo mkdir -p /var/lib/lab && sudo touch /var/lib/lab/.preseed-applied
fi
```

### 0.4 Eliminar pools duplicados
Quitar las líneas `sudo lxc storage create stateless-pool/persistent-pool` del script (los pools vienen del preseed). Fuente única = preseed.

### 0.5 Propagar perfiles y redes al proyecto `labs`
`labs` tiene `features.profiles=true` y `features.networks=true` → catálogos aislados:
```bash
for prof in stateless persistent admin; do
  if ! lxc profile list --project labs --format csv --columns n 2>/dev/null | grep -qx "$prof"; then
    lxc profile copy "$prof" labs/"$prof"
  fi
done
for net in lab-stateless lab-persistent admin-net; do
  if ! lxc network list --project labs --format csv --columns n 2>/dev/null | grep -qx "$net"; then
    lxc network create "$net" --project labs \
      $(lxc network show "$net" --project default | grep -E 'ipv4|ipv6|dns|nat' | sed 's/^/ /')
  fi
done
```

### 0.6 Copiar imágenes a `labs` (después del preseed, que crea el proyecto)
```bash
for alias in ubuntu-22.04-vm ubuntu-22.04-container; do
  if ! lxc image list --project labs --format csv --columns a 2>/dev/null | grep -qx "$alias"; then
    fp=$(lxc image list --project default --format csv -c f --alias "$alias")
    lxc image copy "local:$fp" local: --alias "$alias" --project labs
  fi
done
```

### 0.7 Endurecer perfil `persistent` (en ambos proyectos)
```bash
for proj in default labs; do
  lxc profile set persistent --project "$proj" boot.autostart=false
  lxc profile set persistent --project "$proj" security.devlxd=false
  lxc profile set persistent --project "$proj" security.secureboot=true
done
```

### 0.8 Mover `admin` a `stateless-pool` (no crear `admin-pool` nuevo — convención)
```bash
lxc profile device set admin root pool stateless-pool
lxc profile device set admin root pool stateless-pool --project labs
```

### 0.9 Eliminar `trust_password` y `https_address` TCP (seguridad)
```bash
sudo lxc config unset core.trust_password 2>/dev/null || true
sudo lxc config unset core.https_address 2>/dev/null || true
```
Actualizar `lxd-preseed.yaml` (documentación) quitando `core.trust_password` y `core.https_address`.

### 0.10 `set -Eeuo pipefail` + auto-detección CRLF
En `1-server-setup-lxd.sh` y `build-lab-vm-base-mate.sh`:
```bash
set -Eeuo pipefail
if grep -q $'\r' "$0"; then echo "CRLF detectado: dos2unix primero"; exit 1; fi
```

### 0.11 Rehacer `build-lab-vm-base-mate.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT="labs"; BASE_VM="vm-base"; IMAGE_ALIAS="lab-vm-base"
IMAGE_VERSIONED="lab-vm-base-v$(date +%Y%m%d)"
IMAGE_SOURCE="local:ubuntu-22.04-vm"; PROFILE="persistent"

cleanup() {
  local rc=$?
  lxc delete -f "$BASE_VM" --project "$PROJECT" 2>/dev/null || true
  return $rc
}
trap cleanup EXIT INT TERM

lxc project switch "$PROJECT"

if lxc image show "$IMAGE_ALIAS" --project "$PROJECT" >/dev/null 2>&1; then
  if [ "${1:-}" != "--force" ]; then
    echo "SKIP: $IMAGE_ALIAS existe. Use --force para reconstruir."; exit 10
  fi
  lxc image delete "$IMAGE_ALIAS" --project "$PROJECT" 2>/dev/null || true
  lxc image delete "$IMAGE_VERSIONED" --project "$PROJECT" 2>/dev/null || true
fi

lxc launch "$IMAGE_SOURCE" "$BASE_VM" --vm -p "$PROFILE" --project "$PROJECT"

# Espera agente con timeout global (no bucle infinito)
timeout 180 bash -c "until lxc exec $BASE_VM --project $PROJECT -- true 2>/dev/null; do sleep 3; done" \
  || { echo "ERROR: agente LXD no respondió"; exit 1; }

# cloud-init status --wait con timeout + validación de estado
timeout 600 lxc exec "$BASE_VM" --project "$PROJECT" -- cloud-init status --wait \
  || { lxc exec "$BASE_VM" --project "$PROJECT" -- cloud-init status --long >&2; exit 1; }
lxc exec "$BASE_VM" --project "$PROJECT" -- cloud-init status --long | grep -q "status: done" \
  || { echo "ERROR: cloud-init no terminó en done"; exit 1; }

lxc exec "$BASE_VM" --project "$PROJECT" -- bash <<'EOF'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
echo 'set shared/default-x-display-manager select lightdm' | debconf-set-selections
echo 'keyboard-configuration keyboard-configuration/layoutcode select es' | debconf-set-selections
apt-get update
apt-get install -y --no-install-recommends \
  ubuntu-mate-desktop-core lightdm xrdp cloud-init openssh-server sudo curl vim ca-certificates
update-alternatives --set x-session-manager /usr/bin/mate-session 2>/dev/null || true
cat >/etc/xrdp/startwm.sh <<'WM'
#!/bin/sh
if [ -r /etc/default/locale ]; then . /etc/default/locale; export LANG LANGUAGE; fi
exec dbus-launch --exit-with-session mate-session
WM
chmod +x /etc/xrdp/startwm.sh
systemctl enable xrdp ssh
systemctl set-default graphical.target
# Autologin xrdp (Modelo A: sin password RDP conocida por el alumno)
mkdir -p /etc/lightdm/lightdm.conf.d
cat >/etc/lightdm/lightdm.conf.d/99-lab-autologin.conf <<'AL'
[Seat:*]
autologin-user=alumno
autologin-user-timeout=0
AL
EOF

# Smoke test xrdp robusto (anclar puerto, validar sesman)
lxc exec "$BASE_VM" --project "$PROJECT" -- bash -c '
  systemctl start xrdp 2>/dev/null || true
  sleep 2
  systemctl is-active xrdp xrdp-sesman &&
  ss -ltnp | awk "\$4 ~ /:3389$/ {found=1} END {exit !found}"
' || { echo "ERROR: smoke test xrdp falló"; exit 1; }

# Limpieza CRÍTICA para que hijas ejecuten cloud-init
lxc exec "$BASE_VM" --project "$PROJECT" -- bash -c '
  cloud-init clean --logs --machine-id
  rm -rf /var/lib/cloud/instances/*
  truncate -s 0 /etc/machine-id
  rm -f /etc/cloud/cloud.cfg.d/99-installer.cfg
  rm -f /etc/ssh/ssh_host_*
  journalctl --rotate 2>/dev/null || true
  journalctl --vacuum-time=1s 2>/dev/null || true
  apt-get clean
  rm -rf /var/lib/apt/lists/*
  dpkg --audit || true
'

lxc stop "$BASE_VM" --project "$PROJECT" --timeout=60 \
  || lxc stop "$BASE_VM" --project "$PROJECT" --force
[ "$(lxc list "$BASE_VM" -c s --project "$PROJECT" --format csv)" = "STOPPED" ] \
  || { echo "ERROR: VM no parada"; exit 1; }

lxc publish "$BASE_VM" --project "$PROJECT" \
  --alias "$IMAGE_ALIAS" --alias "$IMAGE_VERSIONED" --force

lxc image show "$IMAGE_ALIAS" --project "$PROJECT"
lxc image show "$IMAGE_VERSIONED" --project "$PROJECT"
```

### 0.12 Limpieza cosmética
- Eliminar `lxdbr0` residual si `USED BY == 0`.
- Volver a `lxc project switch default` tras el builder para que las validaciones finales listen `default`.

**Validación FASE 0:**
```bash
lxc storage list && lxc network list && lxc profile list && lxc project list
lxc image list local --project labs
lxc profile show persistent --project labs | grep -E 'boot.autostart|security.devlxd'
lxc config show | grep -E 'trust_password|https_address'  # debe estar vacío
sudo bash 1-server-setup-lxd.sh  # re-ejecutable sin romper
```

---

## FASE 1 — Auth (magic link + JWT)

**Objetivo:** magic link por email + JWT HS256 en cookie httpOnly, con matrícula que deduce el lab.

**Agentes:** `@auth-designer` + `@provision-api` (esqueleto); `@critic-security`, `@critic-idempotency` revisan.

### 1.1 Esqueleto `provision/`
```
provision/
├── main.py            # FastAPI app + lifespan (worker de jobs)
├── auth.py            # magic link + JWT + /verify
├── db.py              # SQLite schema + PRAGMAs
├── instances.py       # (vacío hasta FASE 3)
├── policy.py          # (vacío hasta FASE 5)
├── jobs.py            # job queue persistente (FASE 3)
├── config.py          # lee .env, valida obligatorios
├── requirements.txt
└── .env.example
```
`requirements.txt`:
```
fastapi>=0.110
uvicorn[standard]>=0.27
pyjwt>=2.8
python-dotenv>=1.0
slowapi>=0.1.9
aiosmtplib>=3.0
jinja2>=3.1
```

### 1.2 Schema SQLite (`db.py`)
```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA synchronous=NORMAL;

-- Magic-link tokens (almacenados como sha256, no en claro)
CREATE TABLE IF NOT EXISTS auth_tokens(
  token_hash TEXT PRIMARY KEY,          -- sha256(token) hex
  email      TEXT NOT NULL,
  lab        TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,          -- now + 900
  used_at    INTEGER DEFAULT NULL,
  used_from_ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_email ON auth_tokens(email);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_expires ON auth_tokens(expires_at);

-- Matrícula (el lab se deduce, no lo elige el alumno)
CREATE TABLE IF NOT EXISTS enrollments(
  alumno_id  TEXT NOT NULL,             -- id opaco (sub del JWT)
  email      TEXT NOT NULL,
  lab        TEXT NOT NULL,
  course     TEXT,
  active     INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  UNIQUE(email, lab, course)
);
CREATE INDEX IF NOT EXISTS idx_enrollments_email_active ON enrollments(email, active);

-- Revocación de sesiones JWT
CREATE TABLE IF NOT EXISTS jwt_jti(
  jti        TEXT PRIMARY KEY,
  revoked_at INTEGER NOT NULL
);

-- Labs definidos (catálogo)
CREATE TABLE IF NOT EXISTS labs(
  nombre     TEXT PRIMARY KEY,
  imagen     TEXT NOT NULL DEFAULT 'local:lab-vm-base',
  deadline   TEXT,
  activo     INTEGER NOT NULL DEFAULT 1
);
```

### 1.3 `POST /auth/request` (email)
- Consulta `enrollments WHERE email=? AND active=1`:
  - 0 filas → respuesta neutra `{"status":"enviado"}` (no se envía nada; anti-enumeración).
  - 1 fila → `lab` único.
  - >1 filas → `{"status":"choose", "labs":[...]}` → segundo `POST /auth/request {email, lab}` con `lab` validado contra la lista.
- Genera `token = secrets.token_urlsafe(32)` (256 bits).
- `INSERT INTO auth_tokens(token_hash=sha256(token), email, lab, expires_at=now+900)`.
- Envía email asíncrono (cola en memoria) con `https://lab.<dominio>/auth/verify?token=<token>`. Plantilla HTML+texto, asunto neutro, sin token en asunto.
- Rate-limit slowapi: `5/min per IP, 3/10min per email, 60/min global` (excluyendo `/lab/status`).
- Respuesta siempre `{"status":"enviado"}` con timing constante.

### 1.4 `POST /auth/verify?token=...`
- `BEGIN IMMEDIATE; UPDATE auth_tokens SET used_at=?, used_from_ip=? WHERE token_hash=sha256(?) AND used_at IS NULL AND expires_at>?;`
- Si `rowcount == 1`:
  - Lee `email`, `lab`. Resuelve `alumno_id` de `enrollments`.
  - Emite JWT HS256: `{"sub": alumno_id, "lab": lab, "iat": now, "exp": now+3600, "jti": uuid4, "iss": "provision-api", "aud": "lab-gateway"}`.
  - `jwt.encode(..., JWT_SECRET, algorithm="HS256")` — **fijado a HS256**, `algorithms=["HS256"]` en decode.
  - Set-Cookie: `lab_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=3600`.
  - `COMMIT`. Redirect 302 a `https://lab.<dominio>/lab/start`.
- Si `rowcount == 0`: rollback; `410 Gone`.

### 1.5 `GET /verify` (endpoint para `auth_request` de Nginx)
- Lee cookie `lab_token`.
- `jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"require":["exp","sub","jti","lab"]})`.
- Verifica `jti` no está en `jwt_jti` (revocados).
- Si valida: `200` + headers `X-Lab-Alumno: <sub>`, `X-Lab-Name: <lab>`.
- Si no: `401`.

### 1.6 `POST /logout`
- Revoca `jti`: `INSERT INTO jwt_jti(jti, revoked_at) VALUES(?, ?)`.
- `Set-Cookie: lab_token=; Max-Age=0; Path=/; Secure; SameSite=Lax`.

### 1.7 Service token de VM (`SERVICE_JWT_SECRET` separado)
- Claims: `{"sub": "<alumno>-<lab>", "scope": ["save","reset","heartbeat"], "iat":..., "exp": vida de la VM o rotable}`.
- Se genera al lanzar (FASE 3), se guarda en `vm_tokens`, se inyecta en cloud-init (FASE 2).
- Rotación: `/heartbeat` devuelve un token nuevo, el viejo se invalida.
- Validación en `/save`/`/reset`/`/restore`: `sub==hostname` + IP origen == IP registrada en BD para esa instancia (no solo rango).

### 1.8 `.env.example`
```
# Proveedor SMTP (dev=mailtrap, prod=real)
SMTP_PROVIDER=mailtrap
MAILTRAP_HOST=smtp.mailtrap.io
MAILTRAP_PORT=587
MAILTRAP_USER=
MAILTRAP_PASS=
# JWT (navegador)
JWT_SECRET=
JWT_SECRET_PREV=
# Service token de VM (separado)
SERVICE_JWT_SECRET=
# Dominio público
PUBLIC_DOMAIN=lab.example.com
PROVISION_URL=http://127.0.0.1:8000
PROVISION_URL_VM=http://10.50.20.1:8000
```

**Validación FASE 1:**
- `curl -X POST /auth/request -d '{"email":"alumno@x"}'` → 200 `{"status":"enviado"}`.
- Mailtrap captura el enlace.
- `curl -X POST /auth/verify?token=<token>` → 302 + cookie `lab_token`.
- `curl /verify -H "Cookie: lab_token=..."` → 200 + headers `X-Lab-Alumno`/`X-Lab-Name`.
- Reusar el mismo token → 410 Gone.
- Rate-limit: 6 peticiones/min mismo IP → 429.

---

## FASE 2 — Cloud-init por alumno

**Objetivo:** `cloud-init-template.yml` con variables Jinja2, scripts `lab-save`/`lab-reset`/`lab-heartbeat`, identidad VM→API.

**Agentes:** `@cloud-init-author` + `@provision-api` (inyecta secrets); `@critic-security`, `@critic-idempotency`, `@critic-lxd-conventions` revisan.

### 2.1 `cloud-init-template.yml` (Modelo A — sin password RDP conocida)
```yaml
#cloud-config
users:
  - name: alumno
    lock_passwd: true
    sudo: ${SUDO_MODE}          # nopasswd|with-passwd|none (parametrizable por lab)
    shell: /bin/bash
    ssh_authorized_keys: ${SSH_AUTHORIZED_KEYS}  # opcional, vacío por defecto

hostname: ${ALUMNO}-${LAB}
manage_etc_hosts: true
fqdn: ${ALUMNO}-${LAB}

package_update: true
# NO package_upgrade (idempotencia: no cambiar versiones en re-aplicación)
packages:
  - python3
  - git
  # Delta del lab; MATE/xrdp/ssh ya están en lab-vm-base

write_files:
  - path: /usr/local/bin/lab-save
    permissions: '0755'
    owner: root:root
    append: false
    content: |
      #!/bin/bash
      TOKEN=$(sudo cat /etc/lab/identity)
      RESP=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
        "${PROVISION_URL_VM}/save" \
        -H "Authorization: Bearer ${TOKEN}" \
        -d "instancia=$(hostname -s)")
      case "$RESP" in
        200|202) echo "Snapshot guardado (tag kN)" ;;
        507) echo "No se pudo guardar: pool lleno" ;;
        409) echo "Conflicto: la instancia no está lista" ;;
        *)   echo "Error al guardar (HTTP $RESP)" ;;
      esac
      exit $([ "$RESP" = "200" -o "$RESP" = "202" ] && echo 0 || echo 1)
  - path: /usr/local/bin/lab-reset
    permissions: '0755'
    owner: root:root
    append: false
    content: |
      #!/bin/bash
      [ "${1:-}" != "--yes" ] && read -p "¿Restaurar al estado base? Se perderán los cambios no guardados [y/N]" -n1 -r && echo
      [[ ! $REPLY =~ ^[Yy]$ ]] && [ "${1:-}" != "--yes" ] && exit 1
      TOKEN=$(sudo cat /etc/lab/identity)
      curl -sS -X POST "${PROVISION_URL_VM}/reset" \
        -H "Authorization: Bearer ${TOKEN}" \
        -d "instancia=$(hostname -s)"
      echo "Reset solicitado. Tu escritorio se reiniciará; vuelve a entrar por el navegador."
  - path: /usr/local/bin/lab-heartbeat
    permissions: '0755'
    owner: root:root
    append: false
    content: |
      #!/bin/bash
      TOKEN=$(sudo cat /etc/lab/identity)
      curl -sS -X POST "${PROVISION_URL_VM}/heartbeat" \
        -H "Authorization: Bearer ${TOKEN}" \
        -d "instancia=$(hostname -s)" >/dev/null
  - path: /etc/lab/identity
    permissions: '0640'
    owner: root:root
    content: "${LAB_SERVICE_TOKEN}"
  - path: /etc/systemd/system/lab-heartbeat.timer
    content: |
      [Unit]
      Description=Lab heartbeat
      [Timer]
      OnBootSec=1min
      OnUnitActiveSec=5min
      [Install]
      WantedBy=timers.target
  - path: /etc/systemd/system/lab-heartbeat.service
    content: |
      [Unit]
      Description=Lab heartbeat
      [Service]
      Type=oneshot
      ExecStart=/usr/local/bin/lab-heartbeat

# NO chpasswd (Modelo A: autologin, sin password RDP conocida)
# NO ssh_pwauth: true (bloquear shell remoto más allá de RDP)
# NO final_modules: [] (desactiva módulos; mejor cloud-init clean selectivo)

runcmd:
  - [ sh, -c, "if [ ! -f /etc/lab/.provisioned ]; then systemctl enable --now xrdp ssh lab-heartbeat.timer; systemctl restart xrdp; echo \"$(sha256sum /etc/lab/identity)\" > /etc/lab/.provisioned; fi" ]

timezone: ${TIMEZONE}
```

### 2.2 Contrato de render (Jinja2)
- `provision-api` renderiza la plantilla al lanzar (FASE 3), interpolando:
  - `${ALUMNO}`, `${LAB}`: del JWT (validados con `^[a-z0-9][a-z0-9-]{1,30}$`).
  - `${PROVISION_URL_VM}`: `http://10.50.20.1:8000` (IP del host en bridge `lab-persistent`, **no** 127.0.0.1).
  - `${LAB_SERVICE_TOKEN}`: service token de VM (FASE 1.7).
  - `${SUDO_MODE}`, `${SSH_AUTHORIZED_KEYS}`, `${TIMEZONE}`: parametrizables por lab.
- Render con `autoescape` + whitelist estricta de valores (`SUDO_MODE ∈ {nopasswd,with-passwd,none}`).
- Pasar user-data vía stdin a `lxc launch ... -c user.user-data=-` (no como argumento shell — evita inyección de flags).
- Validar que el YAML renderizado es parseable antes de lanzar.
- El renderizado **no** se commitea jamás; se pasa in-memory.

### 2.3 `docs/cloud-init-render.md`
Documentar el contrato de renderización y los campos interpolables.

**Validación FASE 2:**
- Lanzar VM manual: `lxc launch local:lab-vm-base test-alumno-lab1 --vm -p persistent --project labs -c user.user-data=-` (stdin).
- `lxc exec test-alumno-lab1 -- cloud-init status --wait` → `status: done`.
- `lxc exec test-alumno-lab1 -- systemctl is-active xrdp` → `active`.
- `lxc exec test-alumno-lab1 -- cat /etc/lab/.provisioned` → existe.
- `lxc exec test-alumno-lab1 -- lab-save` → reach provision-api (mock).
- Limpiar: `lxc delete test-alumno-lab1 --force --project labs`.

---

## FASE 3 — Provision on-demand

**Objetivo:** FastAPI + SQLite + systemd, lanza/recupera VMs, orquesta snapshots/reset.

**Agentes:** `@provision-api` + `@policy-engine` (esqueleto); todos los críticos revisan.

### 3.1 Arquitectura
- **Host**, usuario `provision` en grupo `lxd`, `lxc` vía `asyncio.create_subprocess_exec` (no `subprocess.run` bloqueante — no anula el event loop).
- **Sin** REST LXD, **sin** `trust_password`.
- Siempre `--project labs` explícito.
- uvicorn `--workers 1` (SQLite single-writer); concurrencia vía `asyncio` + job queue.

### 3.2 Schema SQLite (ampliación FASE 1)
```sql
CREATE TABLE IF NOT EXISTS instancias(
  nombre      TEXT PRIMARY KEY,         -- '<lab>-<alumno>'
  alumno      TEXT NOT NULL,
  lab         TEXT NOT NULL REFERENCES labs(nombre),
  estado      TEXT NOT NULL CHECK (estado IN ('creando','lista','detenida','error','destruida')),
  ip_rdp      TEXT,
  creado      TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen   TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (alumno, lab)
);
CREATE INDEX IF NOT EXISTS idx_inst_last_seen ON instancias(last_seen);
CREATE INDEX IF NOT EXISTS idx_inst_estado ON instancias(estado);

CREATE TABLE IF NOT EXISTS heartbeats(
  instancia   TEXT PRIMARY KEY REFERENCES instancias(nombre),
  last_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots(
  instancia  TEXT NOT NULL REFERENCES instancias(nombre),
  tag        TEXT NOT NULL,
  creado     TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (instancia, tag)
);

CREATE TABLE IF NOT EXISTS vm_tokens(
  token      TEXT PRIMARY KEY,
  instancia  TEXT NOT NULL REFERENCES instancias(nombre),
  creado     TEXT NOT NULL DEFAULT (datetime('now')),
  revocado   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS jobs(
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo       TEXT NOT NULL,             -- 'launch', 'save', 'reset', 'destroy'
  instancia  TEXT,
  payload    TEXT,
  estado     TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|error
  creado     TEXT NOT NULL DEFAULT (datetime('now')),
  started_at TEXT,
  finished_at TEXT
);
```

### 3.3 Endpoints
| Método + path | Auth | Qué hace | Respuesta |
|---|---|---|---|
| `POST /auth/request` | ninguna | genera magic link | `202 {"status":"enviado"}` |
| `POST /auth/verify` | ninguna | valida token, emite JWT | `302` + cookie |
| `GET /verify` | cookie JWT | valida JWT para Nginx | `200` + headers `X-Lab-*` |
| `POST /logout` | cookie JWT | revoca jti | `204` |
| `POST /lab/start` | cookie JWT | lanza/recupera VM (idempotente) | `200` o `202 {estado:"creando"}` |
| `GET /lab/status` | cookie JWT | estado real | `200 {estado, ip_rdp}` |
| `POST /heartbeat` | VM-token | actualiza `heartbeats.last_seen` | `204` |
| `POST /save` | VM-token | snapshot k1..k5 (rotación) | `200 {tag}` |
| `POST /reset` | VM-token | restore base | `200` |
| `POST /restore?tag=` | VM-token | restore tag específico | `200` / `404` |
| `GET /snapshots` | VM-token | lista snapshots | `200 {snapshots}` |
| `POST /admin/destroy` | admin | destruye instancia | `200` |
| `POST /admin/reap` | admin | reaper (invocado por timer standalone) | `200 {destruidas}` |

### 3.4 Flujo de lanzamiento (`/lab/start`)
1. Resuelve `(alumno, lab)` del JWT. `instancia = f"{lab}-{alumno}"`. Valida `NAME_RE`.
2. `BEGIN IMMEDIATE`:
   - `INSERT INTO instancias ... ON CONFLICT(alumno,lab) DO UPDATE SET estado='creando', last_seen=now WHERE estado IN ('destruida','error')`.
   - Si `rowcount==0` y estado era `creando`/`lista` → devolver `202` sin relanzar (idempotente).
3. Encola job `tipo='launch'` en tabla `jobs`. Responde `202 {estado:"creando"}`.
4. Worker dedicado (en `lifespan`) reclama el job:
   - `lxc launch local:lab-vm-base <lab>-<alumno> --vm -p persistent --project labs -c user.user-data=-` (cloud-init renderizado vía stdin).
   - `timeout 300 lxc exec <instancia> -- cloud-init status --wait` → validar `status: done`.
   - `lxc snapshot <instancia> base --project labs` (precheck atómico: si existe, no recrea).
   - `healthcheck_rdp()` (retries 30×2s).
   - Resolver IP: `lxc list -c4 --format csv <instancia> --project labs`.
   - `UPDATE instancias SET estado='lista', ip_rdp=?`.
   - Escribir conexión Guacd DB (FASE 4) si adapter disponible.
5. Cliente sondea `/lab/status` (excluido del rate-limit global).

### 3.5 Concurrencia
- `BEGIN IMMEDIATE` + `estado='creando'` como mutex + `PRAGMA busy_timeout=5000`.
- Job queue persistente (tabla `jobs` + worker en `lifespan`) — sobrevive a reinicios (no `BackgroundTasks`).
- Semáforo async: `asyncio.Semaphore(min(4, ram_host_gb//4 - 2))` para lanzamientos concurrentes.

### 3.6 Reconciliación BD↔LXD en `ExecStartPre`
- **Dry-run por defecto**: loguea diff, marca `orphan` en tabla de cuarentena.
- Borrado solo con flag `--apply` + `SELECT count(*) FROM instancias > 0` + grace period 10min.
- **Nunca** `lxc delete` directo en arranque.

### 3.7 systemd
`/etc/systemd/system/provision.service`:
```ini
[Unit]
Description=LXD Lab Provision API
After=network-online.target snap.lxd.daemon.service
Wants=network-online.target
Requires=snap.lxd.daemon.service

[Service]
Type=simple
User=provision
Group=provision
SupplementaryGroups=lxd
WorkingDirectory=/opt/provision
EnvironmentFile=/etc/provision/provision.env
ExecStart=/opt/provision/.venv/bin/uvicorn provision.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/provision
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```
`/etc/systemd/system/provision-reap.timer`:
```ini
[Unit]
Description=Reap stale LXD lab instances

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true
RandomizedDelaySec=30s

[Install]
WantedBy=timers.target
```
`/etc/systemd/system/provision-reap.service`:
```ini
[Unit]
Description=Reap stale LXD lab instances (standalone)
After=provision.service

[Service]
Type=oneshot
User=provision
Group=provision
EnvironmentFile=/etc/provision/provision.env
ExecStart=/opt/provision/.venv/bin/python -m provision.reap
```

### 3.8 Usuario `provision` en el host
```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin provision
sudo usermod -aG lxd provision
sudo install -d -o provision -g provision -m 0750 /var/lib/provision
sudo install -d -o provision -g provision -m 0750 /etc/provision
# provision.env en /etc/provision/provision.env con permisos 0640
```

**Validación FASE 3:**
- `curl /lab/start` con cookie → VM en `lxc list --project labs`.
- `lxc exec <inst> -- cloud-init status` → done.
- `lxc info <instancia> --project labs` muestra snapshot `base`.
- Re-ejecutar `/lab/start` → misma instancia (idempotente).
- `systemctl stop provision` → reiniciar → reconciliación marca orphan (no destruye).
- Doble `/lab/start` simultáneo → una 202, la otra 202 sin relanzar.

---

## FASE 4 — Acceso web (Guacamole + guacd + Nginx)

**Objetivo:** acceso web seguro con guacd siempre intermedio.

**Agentes:** `@web-gateway`; `@critic-security`, `@critic-scalability`, `@critic-reliability` revisan.

### 4.1 Topología
- Nginx + provision-api nativos en host.
- Guacamole + guacd + mysql en Docker.
- **Opción A (dev/lab):** los tres en `network_mode: host`, bind estricto `127.0.0.1` (4822, 8080, 3306). guacd con `--cap-drop=ALL --security-opt no-new-privileges`.
- **Opción C (deuda prod):** guacd nativo socket Unix.
- No hace falta `admin-net` ni bridge extra.

### 4.2 `guacamole/docker-compose.yml`
```yaml
services:
  guacd:
    image: guacd:latest
    network_mode: host
    cap_drop: [ALL]
    security_opt: [no-new-privileges]
    restart: unless-stopped
  guacamole:
    image: guacamole:latest
    depends_on: [guacd, mysql]
    network_mode: host
    environment:
      GUACD_HOSTNAME: 127.0.0.1
      MYSQL_DRIVER: mysql
      MYSQL_HOSTNAME: 127.0.0.1
      MYSQL_PORT: 3306
      MYSQL_DATABASE: guacamole
      MYSQL_USER: guacamole
      MYSQL_PASSWORD: ${GUAC_MYSQL_PASS}
    restart: unless-stopped
  mysql:
    image: mysql:8
    network_mode: host
    volumes: ["mysql_data:/var/lib/mysql"]
    environment:
      MYSQL_ROOT_PASSWORD: ${GUAC_MYSQL_ROOT}
      MYSQL_DATABASE: guacamole
      MYSQL_USER: guacamole
      MYSQL_PASSWORD: ${GUAC_MYSQL_PASS}
    restart: unless-stopped

volumes:
  mysql_data:
```

### 4.3 Modelo de conexión (Modelo A — sin password RDP)
- Una conexión `<alumno>-<lab>` en DB JDBC escrita por provision-api tras `healthcheck_rdp` OK.
- Parámetros: `hostname=<vm-ip>`, `port=3389`, `username=alumno`, `ignore-cert=true`, `security=any`.
- **Sin password** (Modelo A: autologin configurado en imagen base).
- Header Auth Extension (dev) o JSON auth (prod) para SSO sin doble login.
- En destroy: `DELETE` conexión+usuario de Guacamole.
- IP dinámica: provision-api reescribe `hostname` tras cada healthcheck dentro de la tx de estado 'lista'.

### 4.4 Aislamiento inter-VM
```bash
sudo iptables -A FORWARD -i lab-persistent -o lab-persistent -j DROP
sudo iptables -I FORWARD -s 10.50.20.1 -d 10.50.20.0/24 -p tcp --dport 3389 -j ACCEPT
# Restringir al UID de guacd (defensa en profundidad)
sudo iptables -I OUTPUT -m owner --uid-owner <guacd_uid> -d 10.50.20.0/24 -p tcp --dport 3389 -j ACCEPT
```
- `ss -tlnp | grep 3389` en host → vacío (validación obligatoria).
- DROP inter-VM cubre todos los puertos (no solo 3389).

### 4.5 `nginx/lab.conf`
```nginx
server {
  listen 80;
  server_name lab.<dominio>;
  return 301 https://$host$request_uri;
}

server {
  listen 443 ssl http2;
  server_name lab.<dominio>;
  ssl_certificate /etc/letsencrypt/live/lab.<dominio>/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/lab.<dominio>/privkey.pem;

  add_header Strict-Transport-Security "max-age=31536000;includeSubDomains" always;
  add_header X-Content-Type-Options nosniff always;
  add_header Referrer-Policy no-referrer always;

  # auth_request a provision-api /verify
  location = /verify {
    internal;
    proxy_pass http://127.0.0.1:8000/verify;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header Cookie $http_cookie;
  }
  auth_request /verify;

  # Identidad SOLO desde el JWT (no del subdominio)
  auth_request_set $lab_alumno $upstream_http_x_lab_alumno;
  auth_request_set $lab_name   $upstream_http_x_lab_name;

  # Nginx SIEMPRE sobreescribe Remote-User (no reenvía la del cliente)
  proxy_set_header Remote-User   "$lab_alumno-$lab_name";
  proxy_set_header X-Lab-Alumno  $lab_alumno;
  proxy_set_header X-Lab-Name    $lab_name;
  proxy_set_header X-Forwarded-Proto https;

  # proxy a Guacamole Server (NUNCA a guacd:4822 ni a VM:3389)
  proxy_pass http://127.0.0.1:8080/guacamole/;
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection $http_connection;
  proxy_buffering off;
  proxy_read_timeout 1h;

  # log sin cookie
  log_format lab_safe '$remote_addr $lab_alumno/$lab_name - $request';
  access_log /var/log/nginx/lab.access.log lab_safe;
}

server {
  listen 443 ssl default_server;
  server_name _;
  ssl_certificate /etc/letsencrypt/live/lab.<dominio>/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/lab.<dominio>/privkey.pem;
  return 444;
}
```

### 4.6 certbot (dominio fijo, HTTP-01)
```bash
sudo certbot --nginx -d lab.<dominio> --non-interactive --agree-tos -m admin@example.com
# Hook de validación antes de reload
# /etc/letsencrypt/renewal-hooks/deploy/nginx-reload.sh:
#!/bin/bash
nginx -t && nginx -s reload
```

### 4.7 Logging seguro
- `log_format` sin `$http_cookie`.
- uvicorn log filter que redacte `Authorization` y `Cookie` (config `--log-config`).

**Validación FASE 4:**
- `https://lab.<dominio>` sin cookie → 401.
- Con cookie JWT válida → Guacamole web → escritorio MATE.
- `docker ps` muestra guacd sin puerto publicado.
- `iptables -L FORWARD` muestra DROP inter-VM + ACCEPT 10.50.20.1→3389.
- `ss -tlnp | grep 3389` en host → vacío.
- Guacd DB: `SELECT * FROM guacamole_connection` muestra filas `<alumno>-<lab>` con IP runtime.

---

## FASE 5 — Policy engine (snapshots + auto-destrucción)

**Objetivo:** snapshots nativos LXD solo VMs, reset vía restore, auto-destrucción por inactividad/fecha/curso.

**Agentes:** `@policy-engine`; `@critic-reliability`, `@critic-scalability`, `@critic-idempotency` revisan.

### 5.1 Esquema de snapshots
- Naming: `<alumno>-<lab>/base` (inviolable) + `k1..k5` (retención 5, FIFO).
- `base` se crea tras `cloud-init status --wait` + `status: done` + `healthcheck_rdp` OK (precheck atómico; si existe, no recrea).
- Rotación FIFO basada en `lxc snapshot list --format csv` ordenado (no contador interno): al crear k(n+1) purgar el más viejo **solo si** `count >= 5`.

### 5.2 `provision/policy.py`
```python
async def snapshot_save(instancia: str) -> str:
    """Crea snapshot k1..k5 con rotación. Source of truth = LXD."""
    if not pool_usage_ok():
        raise HTTPException(507, "persistent-pool > 90%")
    snapshots = list_snapshots_from_lxd(instancia)  # lxc info ... --format json
    k_snaps = [s for s in snapshots if TAG_RE.match(s) and s != "base"]
    if len(k_snaps) >= 5:
        oldest = sorted(k_snaps)[0]
        await lxc(["delete", f"{instancia}/{oldest}", "--project", "labs"])
    next_tag = next_free_k(k_snaps)
    await lxc(["snapshot", instancia, next_tag, "--project", "labs"])
    return next_tag

async def reset_to_base(instancia: str):
    """Restaura base sin recrear. Precheck base existe; si no, 409."""
    if "base" not in list_snapshots_from_lxd(instancia):
        raise HTTPException(409, "base snapshot no existe")
    await lxc(["stop", instancia, "--force", "--project", "labs"])
    await lxc(["restore", instancia, "base", "--project", "labs"])
    await lxc(["start", instancia, "--project", "labs"])
    await healthcheck_rdp(instancia)
```

### 5.3 Pool guard reactivo
```python
def pool_usage_pct() -> float:
    out = subprocess.run(["lxc","storage","info","persistent-pool","--format","json"],capture_output=True)
    data = json.loads(out.stdout)
    return data["space"]["used"] / data["space"]["total"] * 100

# En snapshot_save:
usage = pool_usage_pct()
if usage > 90:
    raise HTTPException(503, "persistent-pool > 90%")
if usage > 75:
    # purgar oldest antes de crear
    ...
if usage > 60:
    KEEP = 3  # reducir retención
```
Comprobar pool **antes** de `lxc launch` (no solo en `/save`).

### 5.4 Reaper (standalone)
- **Proceso standalone** (`provision-reap.service` invoca `python -m provision.reap`, no HTTP al worker).
- Criterios: inactividad (`last_seen < now - IDLE_MINUTES` **Y** no sesión RDP activa), deadline del lab, fin de curso.
- `last_seen` se actualiza por heartbeat (FASE 2) **y** por actividad RDP (guacd log).
- `BEGIN IMMEDIATE` + re-check `last_seen` dentro de tx.
- `datetime('now')` de SQLite (no `time.time()` de Python — consistencia ante saltos de reloj).
- Batch deletes `lxc delete --force` en lotes de 10 con sleep entre lotes.
- `CREATING_TIMEOUT` para limpiar `estado='creando'` estancadas.
- Locks anti-destruir VM con sesión activa.

### 5.5 `.env.example` (ampliación)
```
IDLE_MINUTES=60
COURSE_DEADLINE=
KEEP_SNAPSHOTS=5
CREATING_TIMEOUT=600
```

**Validación FASE 5:**
- VM viva → 5×`/save` → `lxc info` muestra `k1..k5`.
- 6º `/save` → purga oldest (FIFO basado en `lxc snapshot list`).
- `/reset` → `lxc info` restaura a `base`, xrdp up.
- `IDLE_MINUTES=1` → esperar +1 min → `systemctl start provision-reap.service` → instancia destruida.
- Pool guard: forzar pool > 90% → `/save` devuelve 503.

---

## Cotumbramiento con críticos (resumen)

| Fase | Críticos a invocar |
|---|---|
| 0 | security, idempotency, lxd-conventions, reliability |
| 1 | security, idempotency |
| 2 | security, idempotency, lxd-conventions |
| 3 | security, idempotency, reliability, scalability, lxd-conventions |
| 4 | security, scalability, reliability |
| 5 | reliability, scalability, idempotency |

Tras cada unidad significativa de cada fase, `lab-build` invoca a los críticos correspondientes y corrige lo que señalen antes de continuar.

---

## Riesgos transversales y mitigaciones

| Riesgo | Severidad | Mitigación | Fase |
|---|---|---|---|
| `persistent-pool` 40GB satura en 2-3 alumnos | CRÍTICA | Pool guard reactivo 60/75/90% + documentar cota + deuda ampliar pool | 0, 5 |
| `trust_password` + `https_address` TCP exponen LXD | CRÍTICA | `lxc config unset` + quitar del preseed | 0 |
| Service token comprometido en VM controlada por alumno | CRÍTICA | Scope por instancia + validación IP exacta + rotación por heartbeat | 1, 2 |
| Cross-tenant por identidad del URL | CRÍTICA | Identidad solo desde JWT vía `auth_request_set` | 4 |
| Reconciliación destruye VMs legítimas | CRÍTICA | Dry-run por defecto + `--apply` + grace period | 3 |
| `subprocess.run` sync bloquea event loop | CRÍTICA | `asyncio.create_subprocess_exec` + job queue | 3 |
| Rate-limit global vs polling de N alumnos | ALTA | Excluir `/lab/status` del global | 1 |
| guacd host network = superficie amplia | ALTA | `--cap-drop=ALL` + Opción C como deuda prod | 4 |
| `provision` en grupo lxd = root equivalente | MEDIA | Deuda: wrapper sudo whitelist de comandos `lxc` | 3 |
| `admin-net` sin NAT limita contenerización | MEDIA | Servicios nativos en host; `admin-net` solo gestión interna | 0 |

---

## Secuencia de ejecución recomendada

1. **FASE 0** (consolidación) → validar con `lxc storage/network/profile/project/image list` + `lxc config show` sin trust_password.
2. **FASE 1** (auth) → validar `/auth/request` + `/auth/verify` con Mailtrap.
3. **FASE 2** (cloud-init) → validar lanzando 1 VM de prueba y comprobando `/etc/lab/.provisioned` + `lab-save`/`lab-reset`.
4. **FASE 3** (provision-api) → validar `/lab/start` end-to-end con 1 alumno.
5. **FASE 4** (web-gateway) → validar flujo navegador→Nginx→Guacamole→guacd→VM:3389 con `ss -tlnp | grep 3389` vacío en host.
6. **FASE 5** (policy-engine) → validar snapshot `base`, reset, y reaper con `IDLE_MINUTES=5` en pruebas.

---

## Cotas de escalabilidad (documentar en `DOIN.md`)

| Recurso | Cota | Límite dominante |
|---|---|---|
| `persistent-pool` 40GB + k1..k5 | **≤2-3 alumnos** | Pool ZFS (cuello dominante actual) |
| SQLite single-writer | **≤50 alumnos** | Writer lock |
| uvicorn workers=1 + job queue | **≤4 lanzamientos concurrentes** | Event loop |
| guacd único | **≤100 conexiones RDP simultáneas** | RAM/puertos host |
| `lab-persistent` /24 | **≤250 VMs** | Subred |
| RAM host (4GB/VM) | **N ≤ RAM_host / 4** | RAM (cuello si pool se amplía) |

---

## Deudas explícitas (para producción)

- **`core.trust_password`**: purgar en producción (FASE 0 ya hace `lxc config unset`); provision-api usa socket Unix, no TCP.
- **`SMTP_PROVIDER=real`**: configurar SendGrid/SES + DKIM/SPF.
- **certbot wildcard** `*.lab.<dominio>` con DNS-01 si se requieren subdominios por alumno.
- **Migración SQLite→Postgres** si >50 alumnos concurrentes.
- **Ampliación `persistent-pool`** (recreación intencionada con `--force-preseed`) si >3 alumnos: pool 80-120GB o retención `k1..k3`.
- **guacd Opción C** (socket Unix nativo) para aislar del host network en prod.
- **Wrapper sudo whitelist** para restringir `provision` a subconjunto de comandos `lxc` (no grupo `lxd` pleno).
- **Sliding window JWT** (8h con hard cap 12h) como mejora UX sobre el TTL fijo 1h de v1.
- **Pool guacd** para N>100 conexiones RDP simultáneas.
- **`__Host-lab_token`** cookie prefix si se valida compatibilidad con todos los clientes.