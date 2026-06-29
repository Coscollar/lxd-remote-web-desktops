# FASE 6 — Portal web + apps stateless + consola admin

> Diseño detallado de la FASE 6. Generado por `lab-plan` tras analizar los
> subagentes de dominio (`@provision-api`, `@web-gateway`, `@auth-designer`,
> `@infra-lxd`, `@policy-engine`) y auditar los críticones
> (`@critic-security`, `@critic-idempotency`, `@critic-lxd-conventions`,
> `@critic-reliability`, `@critic-scalability`). Los 18 BLOQUEANTES detectados
> están integrados como decisiones firmes. Ejecutado por `lab-build`.

## 1. Objetivo

El usuario pide:
1. Pantalla de login para alumnos.
2. Dashboard del alumno: escoger entre máquinas de laboratorio y acceder vía
   navegador.
3. Apps stateless accesibles desde el navegador.
4. Pantalla de admin para gestionar apps stateless disponibles.
5. Pantalla de admin para gestionar máquinas de alumnos (crear, eliminar,
   resetear).

Las FASES 0–5 ya están consolidadas (infra LXD, imagen base VM, cloud-init,
provisión on-demand, acceso web Guacamole+Nginx, policy engine). La FASE 6
extiende lo existente; no lo reemplaza.

## 2. Decisiones firmes (tras críticos)

### Cambios de decisión tras críticas (revertir lo propuesto por subagentes)

| Decisión original | Crítica que la revierte | Decisión final |
|---|---|---|
| Lanzamiento apps **síncrono** 30s | `@critic-reliability` B2 (orphan LXD en 504), `@critic-idempotency` #3 | **Job queue** con `tipo='launch_app'` (reusar `jobs.py`). Endpoint responde 202 + polling. |
| `last_seen` apps vía **side-effect write** en `/verify/app` | `@critic-reliability` B1 (masacra apps tras reinicio), `@critic-scalability` 5/6/7 (cota cae a 20-30 alumnos) | `/verify/app` **READ-ONLY**. `last_seen` vía **heartbeat activo de la app** (POST /heartbeat con service token, como VMs) + grace period tras reinicio. |
| Auto-heal shared `always_on=1` **síncrono en lifespan** | `@critic-reliability` B3, `@critic-idempotency` #6, `@critic-scalability` #10 | Auto-heal **asíncrono vía job queue tras `yield`** (no bloquea arranque). |
| TTL admin **2h** | `@critic-security` #6 (invertido: admin dura más que alumno con más privilegio) | TTL admin **30min** sin sliding. |
| CSP `frame-src 'self'` (iframe same-origin) | `@critic-security` #16 (XSS escape same-origin) | iframe con **`sandbox="allow-scripts allow-forms"` sin `allow-same-origin`** (apps cross-origin efectivas). |
| Ampliar `stateless-pool` con `--force-preseed` | `@critic-scalability` #20 (destruye `persistent-pool`) | `lxc storage set stateless-pool size=80GB` (no destructivo). |
| `resolver 127.0.0.1` en Nginx | `@critic-scalability` #8 (no resuelve nombres LXD) | `resolver 10.50.10.1 valid=1s ipv6=off` o **IP literal** en `X-App-Target`. |

### Decisiones firmes consolidadas

- **Auth admin:** magic link por email (sin password), tabla `admins` separada,
  `ADMIN_JWT_SECRET` separado + `_PREV`, cookie `admin_token` Path=/admin,
  TTL **30min** sin sliding, `X-Admin-Token` conservado para scripts. TOTP
  opcional prod con **token opaco en BD** (no JWT pre-auth). Notificación email
  canje **sin enlaces accionables** + outbox persistente.
- **Multi-lab alumno:** JWT con `lab` **nullable** + claim `scope`
  (`dashboard`|`lab`|`admin`). `verify_jwt` relaja `require` a
  `["exp","sub","jti","scope"]`; `lab` exigido solo si `scope=lab` (validación
  en endpoint, no en decode). `/lab/select` reemite JWT: **emitir nuevo → set
  cookie → revocar viejo** (orden seguro). `/verify` **re-valida matrícula
  activa** (SELECT enrollments).
- **Cross-tenant:** dos endpoints `/verify` separados (alumno aud `lab-gateway`
  / admin aud `lab-admin`), secretos disjuntos. Nginx **sobreescribe** headers
  desde `$upstream_http_*`. **Middleware en provision-api borra**
  `X-Lab-Role`/`X-Admin-Email`/`X-Lab-Alumno`/`X-Lab-Name`/`X-App-Target` de la
  request entrante. Header `X-Internal` compartido (env, len≥32, no loguear,
  rotación manual) en todas las llamadas Nginx→provision-api.
- **Apps stateless:** contenedores LXD perfil `stateless` (no `default`), red
  `lab-stateless`, pool `stateless-pool`. **Imagen preconstruida**
  `local:app-<id>` + cloud-init mínimo opcional (si la app lo usa,
  **`cloud-init status --wait`** obligatorio). **Shared por defecto**
  (`shared=1`), per-alumno opt-in (`shared=0`). `always_on` solo sentido si
  `shared=1`. **Job queue** para lanzar (no síncrono). **Hard cap inventario**
  por RAM/pool/subred.
- **Proxy apps:** Nginx `location ^~ /apps/(?<app_id>[a-z0-9-]+)/` con
  `auth_request /verify/app` (READ-ONLY, valida JWT + pertenencia app↔alumno +
  IP ∈ 10.50.10.0/23) → `X-App-Target: <ip>:<puerto>` →
  `proxy_pass http://$app_target`. Path prefix, `X-Forwarded-Prefix`, WebSocket
  reusa `map $http_upgrade`. iframe **sandbox sin allow-same-origin**.
- **Reaper apps:** función `reap_apps()` en `reap.py` (timer separado
  `provision-reap-apps.timer` OnUnitActiveSec=2min). `last_seen` vía heartbeat
  activo de la app. `BEGIN IMMEDIATE` + re-check + **delete LXD con retry
  3×5s** + UPDATE solo tras confirmar delete. Columna `reap_attempts` +
  backoff. **Grace period tras reinicio** (`GRACE_AFTER_RESTART=15min`).
- **Pool guard:** `pool_usage_pct(pool)` generalizado.
  `stateless_pool_usage_ok()` fail-closed con **cache 30s** (no 503 global por
  fallo transitorio). Umbrales 60/75/90%. **Budget preventivo** (sumar
  footprint running + queued) además del reactivo.
- **Builder apps:** `build-apps/` con `_common.sh` (centraliza `IMAGE_SOURCE`,
  helpers) + un script por app. **Espejo COMPLETO** de
  `build-lab-vm-base-mate.sh`: set -Eeuo pipefail, CRLF guard, trap cleanup,
  precheck alias, timeout agente, **`cloud-init status --wait` con timeout +
  validar status: done**, smoke test HTTP real (no TCP), limpieza completa
  (cloud-init clean, machine-id, ssh_host, journalctl vacuum, apt clean),
  validar STOPPED, publish alias dual, validar image show. `rm -f` (no `rm`).
  Purgar alias versionados previos.
- **Fix preexistente (FASE 6.0):** uvicorn `--host 0.0.0.0` + iptables
  allowlist (127.0.0.1, 10.50.10.0/24, 10.50.20.0/24 → 8000). Nginx
  `proxy_set_header X-Real-IP $remote_addr`. `lab_safe` usa `$uri` (no
  `$request_uri`). `/docs` y `/openapi.json` deshabilitados en prod. Auth por
  **token HMAC por instancia** en `/heartbeat` + rate-limit (iptables solo no
  basta).
- **Nombres:** `APP_NAME_RE=^app-[a-z0-9][a-z0-9-]{1,30}$`. **`NAME_RE`
  alumnos prohibe prefijo `app-`**: `^(?!app-)[a-z0-9][a-z0-9-]{1,30}$`. Si
  `len(app-<id>-<alumno>)>30`, sustituir `<alumno>` por `sha8(alumno)`.
- **`instances.launch_container()` separada** de `launch()` (sin `--vm`,
  perfil `stateless`, imagen parametrizable). No reutilizar `launch()` con
  `--vm` hardcoded.
- **Regla dual fingerprints → triple:** centralizar `IMAGE_SOURCE` en
  `build-apps/_common.sh`. Actualizar `AGENTS.md` + skill `image-fingerprints`.
- **Migración BD:** tabla `schema_version(version PK)` + `BEGIN IMMEDIATE` +
  file lock (`fcntl.flock`). `assert sqlite3.sqlite_version_info >= (3,35,0)`
  en arranque.
- **`ON CONFLICT` partial index:** `ON CONFLICT(app_id, alumno) WHERE alumno
  IS NOT NULL DO UPDATE ...` (sintaxis correcta SQLite ≥3.35).
- **CASCADE:** `app_instances.app_id` con `ON DELETE CASCADE` (igual que
  `app_lab`).
- **`worker_heartbeat` en BD:** actualizado por el worker cada 10s mientras
  procesa un job. Reaper marca estancada si `worker_heartbeat < now - 60s`
  (elimina timeouts mágicos).
- **`/metrics`:** contadores `apps_launched_total`, `apps_reaped_total`,
  `reap_failures_total`, `pool_usage_pct`, `orphan_instances_detected`,
  `auto_heal_failures_total`.
- **Subred:** ampliar `lab-stateless` a `/23` (`10.50.10.0/23`) vía
  `lxc network set lab-stateless ipv4.address=10.50.10.1/23 --project labs`
  (no destructivo).
- **Commits:** `lab-build` no commitea; el usuario gestiona los commits.

## 3. Sub-fases

```
FASE 6.0 (fix preexistente: uvicorn --host, X-Real-IP, lab_safe, /docs, iptables) ──┐
   ├─ FASE 6.1 (auth admin + multi-lab: JWT scope, /lab/select, /admin/auth, cookies, X-Internal) ◀── depende de 6.0
   ├─ FASE 6.2 (UI: FastAPI Jinja2, login, dashboard, consola admin) ◀── depende de 6.1
   ├─ FASE 6.3 (apps stateless infra: builders, imágenes, launch_container, iptables-apps, /23) ◀── paralelo a 6.1
   ├─ FASE 6.4 (apps stateless API: schema, endpoints, job queue, reaper, pool guard) ◀── depende de 6.1, 6.3
   └─ FASE 6.5 (web-gateway multi-ruta: Nginx locations, /verify/app, proxy apps, Guacamole solo /desktop) ◀── depende de 6.1, 6.4
```

## 4. Schema BD nuevo (migración idempotente con schema_version + file lock)

```sql
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version(version) VALUES (0);

-- Auth admin (FASE 6.1)
CREATE TABLE IF NOT EXISTS admins(
  email TEXT PRIMARY KEY, role TEXT NOT NULL DEFAULT 'admin',
  active INTEGER NOT NULL DEFAULT 1, totp_secret TEXT,
  last_login_at INTEGER, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_admins_email_active ON admins(email, active);

CREATE TABLE IF NOT EXISTS admin_auth_tokens(
  token_hash TEXT PRIMARY KEY, email TEXT NOT NULL,
  created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
  used_at INTEGER DEFAULT NULL, used_from_ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_admin_auth_tokens_email ON admin_auth_tokens(email);

CREATE TABLE IF NOT EXISTS admin_jwt_jti(jti TEXT PRIMARY KEY, revoked_at INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS admin_totp_pending(
  token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_logins(
  email TEXT NOT NULL, ip TEXT, ua TEXT, at INTEGER NOT NULL
);

-- Migración auth_tokens.lab nullable (sólo si version < 1):
-- Crear auth_tokens_new con lab TEXT nullable + multi INT, copiar, renombrar.

-- Apps stateless (FASE 6.4)
CREATE TABLE IF NOT EXISTS apps(
  id TEXT PRIMARY KEY,           -- slug: 'jupyter'
  nombre TEXT NOT NULL UNIQUE,   -- display
  imagen TEXT NOT NULL,          -- 'local:app-jupyter'
  shared INTEGER NOT NULL DEFAULT 1,
  always_on INTEGER NOT NULL DEFAULT 0,
  puerto_http INTEGER NOT NULL CHECK (puerto_http BETWEEN 3000 AND 9999),
  cpu INTEGER NOT NULL DEFAULT 2,
  memory_mb INTEGER NOT NULL DEFAULT 2048,
  cmd TEXT, descripcion TEXT,
  activo INTEGER NOT NULL DEFAULT 1,
  creado TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS app_lab(
  app_id TEXT NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
  lab TEXT NOT NULL REFERENCES labs(nombre) ON DELETE CASCADE,
  PRIMARY KEY (app_id, lab)
);
CREATE INDEX IF NOT EXISTS idx_app_lab_lab ON app_lab(lab);

CREATE TABLE IF NOT EXISTS app_instances(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  app_id TEXT NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
  alumno TEXT,                   -- NULL si shared
  nombre_lxd TEXT NOT NULL UNIQUE,
  ip TEXT, puerto_http INTEGER NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('creando','lista','detenida','error','destruida','destruyendo')),
  last_seen TEXT NOT NULL DEFAULT (datetime('now')),
  worker_heartbeat TEXT,         -- actualizado por worker cada 10s
  reap_attempts INTEGER NOT NULL DEFAULT 0,
  creado TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_app_inst_last_seen ON app_instances(last_seen);
CREATE INDEX IF NOT EXISTS idx_app_inst_estado ON app_instances(estado);
CREATE INDEX IF NOT EXISTS idx_app_inst_alumno ON app_instances(alumno);
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_shared ON app_instances(app_id) WHERE alumno IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_peralumno ON app_instances(app_id, alumno) WHERE alumno IS NOT NULL;

CREATE TABLE IF NOT EXISTS app_tokens(  -- service token de app (como vm_tokens)
  instancia TEXT PRIMARY KEY, token_hash TEXT NOT NULL, app_ip TEXT NOT NULL,
  issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS email_outbox(  -- notificaciones admin persistentes
  id INTEGER PRIMARY KEY AUTOINCREMENT, to_email TEXT NOT NULL, subject TEXT NOT NULL,
  body TEXT NOT NULL, created_at INTEGER NOT NULL, sent_at INTEGER, attempts INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_enrollments_alumno_active ON enrollments(alumno_id, active);
```

## 5. Endpoints

### Alumno
| Método | Path | Auth | Qué hace |
|---|---|---|---|
| GET | / | ninguna | Página login. Si cookie válida → 302 /dashboard. |
| GET | /dashboard | cookie lab_token | Tarjetas labs + apps. |
| POST | /auth/request | ninguna | Magic link. lab=null si >1 matrícula. |
| GET | /auth/verify?token | ninguna | Canje → JWT scope=lab o scope=dashboard. |
| POST | /lab/select {lab} | cookie lab_token | Reemite JWT scope=lab (emitir→cookie→revocar viejo). |
| GET | /api/my-labs | cookie lab_token | Labs del alumno + estado instancias. |
| GET | /apps | cookie lab_token | Apps disponibles (app_lab↔enrollments). |
| POST | /apps/{app_id}/start | cookie lab_token | Encola job launch_app. 202. |
| GET | /apps/{app_id}/status | cookie lab_token | Estado real. |
| POST | /apps/{app_id}/reset | cookie lab_token (per-alumno) / admin (shared) | destroy + launch. |
| POST | /heartbeat | app service token | Actualiza last_seen. Rota token. |
| POST | /logout | cookie lab_token | Revoca jti, borra cookie. |

### Admin
| Método | Path | Auth | Qué hace |
|---|---|---|---|
| GET | /admin/login | ninguna | Página login admin. |
| POST | /admin/auth/request | ninguna | Magic link admin (allowlist admins). |
| GET | /admin/auth/verify?token | ninguna | Canje → cookie admin_token → /admin. |
| GET | /admin | cookie admin_token | Consola admin HTML. |
| GET/POST/PATCH/DELETE | /admin/labs[/{nombre}] | admin | CRUD labs. |
| GET/POST/PATCH/DELETE | /admin/enrollments[/{id}] | admin | CRUD matrículas. |
| GET | /admin/instances | admin | UNION instancias + app_instances. Paginación keyset. |
| POST | /admin/instances/create | admin | Fuerza creación VM (encola job). |
| POST | /admin/instances/{nombre}/reset | admin | Reset VM o app (?tipo=vm|app). |
| POST | /admin/instances/{nombre}/destroy | admin | Destroy (?tipo=vm|app). |
| GET/POST/PATCH/DELETE | /admin/apps[/{app_id}] | admin | CRUD catálogo apps. |
| POST | /admin/apps/{app_id}/start|stop | admin | Lanzar/detener app shared. |
| POST | /admin/totp | admin pre-auth | Valida TOTP (opcional prod). |
| POST | /admin/logout | cookie admin_token | Revoca admin_jwt_jti, borra cookie. |

### Internos (Nginx auth_request)
| Método | Path | Qué hace |
|---|---|---|
| GET | /verify | Valida JWT alumno + matrícula activa. Devuelve X-Lab-Alumno, X-Lab-Name, X-Lab-Scope. |
| GET | /verify/app | READ-ONLY. Valida JWT + pertenencia app↔alumno + IP rango. Devuelve X-App-Target. |
| GET | /admin/verify | Valida cookie admin_token + role admin. Devuelve X-Lab-Role:admin, X-Admin-Email. |

## 6. Comandos LXD (apps stateless)

```bash
# Lanzar app shared (normalmente vía provision-api job queue)
lxc launch local:app-jupyter app-jupyter -p stateless --project labs -c boot.autostart=true

# Lanzar app per-alumno
lxc launch local:app-jupyter app-jupyter-alumno1 -p stateless --project labs

# Healthcheck HTTP (HTTP real, no TCP)
IP=$(lxc list app-jupyter -c4 --format csv --project labs | cut -d, -f1)
curl -sf "http://${IP}:8888/"

# Detener/eliminar (idempotente)
lxc stop app-jupyter --project labs --timeout=30 || lxc stop app-jupyter --project labs --force
lxc delete -f app-jupyter --project labs

# Ampliar pool (no destructivo, NO --force-preseed)
lxc storage set stateless-pool size=80GB

# Ampliar subred (no destructivo)
lxc network set lab-stateless ipv4.address=10.50.10.1/23 --project labs
lxc network set lab-stateless ipv4.address=10.50.10.1/23 --project default
```

## 7. Nginx multi-ruta (lab.conf)

```nginx
server {
    listen 443 ssl http2;
    server_name lab.<dominio>;
    # ssl, HSTS, X-Content-Type-Options, Referrer-Policy

    # --- Locations PÚBLICAS (sin auth_request) ---
    location = / { proxy_pass http://127.0.0.1:8000/; }
    location = /login { proxy_pass http://127.0.0.1:8000/login; }
    location /auth/ { proxy_pass http://127.0.0.1:8000; }
    location /static/ { root /opt/provision/web; expires 1d; add_header Cache-Control "public, immutable"; }
    location /.well-known/acme-challenge/ { root /var/www/certbot; }

    # --- Locations con auth_request /verify (alumno) ---
    location = /dashboard { auth_request /verify; proxy_pass http://127.0.0.1:8000/dashboard; }
    location /lab/ { auth_request /verify; proxy_pass http://127.0.0.1:8000; }
    location /api/ { auth_request /verify; proxy_pass http://127.0.0.1:8000; }

    # --- /desktop/{lab} → Guacamole (solo si scope=lab) ---
    location ~ ^/desktop/(?<lab>[a-z0-9-]+)(/.*)?$ {
        set $requested_lab $lab;
        auth_request /verify;
        auth_request_set $lab_alumno $upstream_http_x_lab_alumno;
        auth_request_set $lab_name   $upstream_http_x_lab_name;
        auth_request_set $lab_scope  $upstream_http_x_lab_scope;
        if ($lab_scope != "lab") { return 302 /dashboard; }
        if ($lab_name != $lab) { return 403; }
        proxy_set_header Remote-User "$lab_alumno-$lab_name";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Internal $internal_token;
        proxy_pass http://127.0.0.1:8080/guacamole/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_buffering off;
        proxy_read_timeout 1h;
    }

    # --- /apps/{app_id}/ → app stateless (auth_request /verify/app READ-ONLY) ---
    location ^~ /apps/(?<app_id>[a-z0-9-]+)/ {
        auth_request /verify_app;
        auth_request_set $app_target $upstream_http_x_app_target;
        if ($app_target = "") { return 503; }
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Prefix /apps/$app_id;
        proxy_set_header X-Internal $internal_token;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_buffering off;
        proxy_read_timeout 1h;
        resolver 10.50.10.1 valid=1s ipv6=off;
        rewrite ^/apps/([a-z0-9-]+)/(.*)$ /$2 break;
        proxy_pass http://$app_target;
        limit_req zone=appuser burst=20 nodelay;
    }

    # --- /admin/* → provision-api (auth_request /admin/verify) ---
    location /admin { auth_request /admin/verify; proxy_pass http://127.0.0.1:8000; }
    location /admin/ { auth_request /admin/verify; proxy_pass http://127.0.0.1:8000; }
}

# limit_req_zone (en http{} via conf.d):
# limit_req_zone $lab_alumno zone=appuser:10m rate=30r/s;
```

## 8. iptables-apps.sh

```bash
#!/usr/bin/env bash
# FASE 6 — Aislamiento de apps stateless en lab-stateless.
set -euo pipefail

BRIDGE_APP="lab-stateless"; BRIDGE_VM="lab-persistent"
APP_NET="10.50.10.0/23"; VM_NET="10.50.20.0/24"
HOST_APP_IP="10.50.10.1"; APP_PORT_RANGE="3000:9999"
PROVISION_UID=$(id -u provision)

# 1. DROP inter-app
iptables -A FORWARD -i "$BRIDGE_APP" -o "$BRIDGE_APP" -j DROP
# 2. DROP app↔VM bidireccional
iptables -A FORWARD -i "$BRIDGE_APP" -o "$BRIDGE_VM" -j DROP
iptables -A FORWARD -i "$BRIDGE_VM" -o "$BRIDGE_APP" -j DROP
# 3. ACCEPT host→app:HTTP (-I antes de DROP)
iptables -I FORWARD -s "$HOST_APP_IP" -d "$APP_NET" -p tcp --dport "$APP_PORT_RANGE" -j ACCEPT
# 4. ACCEPT app→host:8000 (heartbeat)
iptables -I FORWARD -s "$APP_NET" -d "$HOST_APP_IP" -p tcp --dport 8000 -j ACCEPT
# 5. Defensa en profundidad: solo UID provision alcanza apps
iptables -I OUTPUT -m owner --uid-owner "$PROVISION_UID" -d "$APP_NET" -p tcp --dport "$APP_PORT_RANGE" -j ACCEPT
netfilter-persistent save
# Validar: ss -tlnp | grep -E ':(3389|5900|3000|8888)' vacío en host
```

## 9. Reaper apps (reap_apps en reap.py, timer separado)

- Criterios: per-alumno inactiva > `APP_IDLE_MINUTES=30`; shared `always_on=0`
  inactiva > `SHARED_IDLE_HOURS=6`; shared `always_on=1` NUNCA; creando
  estancada (`worker_heartbeat < now-60s`).
- **Grace period tras reinicio**: ignorar candidatos con
  `last_seen < service_started_at + GRACE_AFTER_RESTART=15min`.
- Por candidato: `BEGIN IMMEDIATE` + re-check → **delete LXD con retry 3×5s**
  (clasificar error: not found=éxito, timeout=no UPDATE + `reap_attempts++` +
  backoff) → UPDATE `estado='destruida'` solo tras confirmar delete.
- Batch 25-50 + `asyncio.gather` (4 concurrentes).

## 10. Pool guard stateless (generalizado)

- `pool_usage_pct(pool="persistent-pool")` generalizado. Cache 30s.
  Fail-closed con cache.
- >90% → 503; >75% → purgar apps inactivas oldest (per-alumno primero, nunca
  shared `always_on=1`); >60% → reaper agresivo.
- **Budget preventivo**: `sum(memory_mb running + queued) < RAM_host -
  RAM_VMs - margen`.
- Hard cap inventario: `count(estado IN creando,lista) < MAX_APP_INSTANCES`.

## 11. Builder de apps (build-apps/)

`_common.sh` centraliza `IMAGE_SOURCE` + helpers. Cada
`build-app-<nombre>.sh` espeja `build-lab-vm-base-mate.sh`:
- set -Eeuo pipefail + CRLF guard.
- Pre-borrado contenedor huérfano + trap cleanup.
- Precheck alias `lxc image show` → SKIP rc=10, --force reconstruir.
- `lxc launch $IMAGE_SOURCE <temp> -p stateless --project labs` (sin --vm).
- `timeout 120 bash -c "until lxc exec ... true; do sleep 2; done"`.
- **`timeout 300 lxc exec ... cloud-init status --wait`** + validar
  `status: done`.
- Instalar app (pasos bespoke).
- **Smoke test HTTP real**: `curl -sf http://localhost:${PUERTO}/`.
- Limpieza completa: `cloud-init clean --logs --machine-id` + `rm -f
  /var/lib/cloud/instances/*` + `truncate -s 0 /etc/machine-id` + `rm -f
  /etc/cloud/cloud.cfg.d/99-installer.cfg` + `rm -f /etc/ssh/ssh_host_*` +
  `journalctl --rotate` + `journalctl --vacuum-time=1s` + `apt-get clean` +
  `rm -rf /var/lib/apt/lists/*`.
- `lxc stop --timeout=30 || lxc stop --force` + validar STOPPED.
- Purgar alias versionados previos del mismo prefijo.
- `lxc publish --alias estable --alias versionado --force`.
- `lxc image set <alias> --project labs auto_update=false`.
- Validar `lxc image show` de ambos alias.

## 12. Instalación y desinstalación

### install-all.sh (cambios)
- dos2unix añade `build-apps/*.sh` al glob.
- Tras FASE 0: ampliar `stateless-pool` a 80GB + `lab-stateless` a /23.
- Tras FASE 0: bucle `for app_script in build-apps/build-app-*.sh`.
- Tras provision/install.sh: generar secretos extra (`ADMIN_JWT_SECRET`,
  `ADMIN_JWT_SECRET_PREV`, `ADMIN_TOKEN`, `INTERNAL_TOKEN`, `ADMIN_TOTP_KEY`)
  en `/etc/provision/provision.env`.
- Tras nginx/install.sh: ejecutar `nginx/iptables-apps.sh`.
- Habilitar `provision-reap-apps.{service,timer}`.

### uninstall-all.sh (cambios)
- Servicios systemd: añadir `provision-reap-apps.{service,timer}`.
- Reglas iptables: borrar reglas de `iptables-apps.sh` (DROP inter-app,
  app↔VM, ACCEPT host→app, app→host:8000, UID provision) + allowlist 8000.
- NO revierte pool/subred (ZFS shrink peligroso; /23 no perjudica). `--purge-lxd`
  elimina pools completamente.

## 13. Cotas de escalabilidad

| Recurso | Cota | Límite dominante |
|---|---|---|
| `stateless-pool` 80GB | ~60-80 contenedores concurrentes | Pool ZFS |
| RAM host (2GB/app) | `min((RAM_host−RAM_VMs)/2GB, MAX_APP_INSTANCES)` | RAM |
| `lab-stateless` /23 | ~510 IPs | Subred |
| `/verify/app` read-only | ~200-500 req/s | JWT decode |
| SQLite single-writer (sin write per-request) | ≤50 alumnos | Writer lock |
| Apps shared `always_on=1` | `sum(memory_mb) ≤ ALWAYS_ON_BUDGET_MB` | RAM |
| Guacd (sin cambio, apps HTTP no usan guacd) | ≤100 RDP simultáneos | RAM/puertos host |

**Cota realista FASE 6 con fixes:** ~30-50 alumnos con apps (shared por
defecto) + ≤10-12 contenedores app concurrentes pool-wide en host 32GB. Para
más: ampliar RAM + pool + subred.

## 14. Deudas explícitas (para producción)

- **Egress allowlist** para apps (squid + whitelist de dominios) en prod.
- **Subdominio por app** (`apps.lab.<dominio>`) con wildcard DNS-01 si se
  quiere aislar apps cross-origin sin sandbox.
- **Migración SQLite→Postgres** si >50 alumnos con uso activo de apps.
- **`X-Internal` HMAC por-request** si el threat model lo justifica (rotación
  sin reinicio).
- **Wrapper sudo whitelist** para restringir `provision` a subconjunto de `lxc`.
- **cgroups v2 quotas por alumno** dentro de apps shared (requiere app
  multi-tenant).
- **Persistent apps** (con volúmenes ZFS) como FASE separada.
- **`/metrics` → Prometheus + alertas** (reap_failures_total, pool_usage_pct
  > 80%).

## 15. Críticas integradas (resumen de BLOQUEANTES)

| BLOQUEANTE | Crítico | Resolución |
|---|---|---|
| `last_seen` pasivo masacra apps tras reinicio | reliability B1 | Heartbeat activo + grace period 15min |
| Lanzamiento síncrono deja orphan LXD en 504 | reliability B2, idempotency #3 | Job queue (no síncrono) + cleanup en fallo |
| Auto-heal síncrono bloquea arranque | reliability B3, idempotency #6, scalability #10 | Auto-heal asíncrono vía job queue tras yield |
| `/verify/app` write per-request satura SQLite | reliability B1, scalability 5/6/7 | `/verify/app` READ-ONLY + last_seen vía heartbeat |
| 50 alumnos × 5 apps per-alumno imposible | scalability 2/3/12 | Hard cap inventario + shared por defecto + ampliar pool/subred |
| `--force-preseed` destruye persistent-pool | scalability #20 | `lxc storage set size=` (no destructivo) |
| Prefijo `app-` colisiona con nombres de alumno | idempotency #10, lxd-conventions #13 | NAME_RE alumnos prohibir `app-` + tipo explícito en destroy |
| `instances.launch` con `--vm` hardcoded | lxd-conventions #4 | `launch_container()` separada |
| Regla dual fingerprints se vuelve triple | lxd-conventions #8 | `_common.sh` centraliza IMAGE_SOURCE |
| CSP iframe same-origin XSS escape | security #16 | iframe sandbox sin allow-same-origin |
| TTL admin 2h > alumno 1h (invertido) | security #6 | TTL admin 30min |
| `lab_safe` loguea query /auth/verify (token) | security #17 | `map` redacta + `$loggable_request` |
| IP binding admin no funciona sin X-Real-IP | security #7 | Nginx setea X-Real-IP + helper `_real_client_ip` |
| `stateless-pool` 20GB sin pool guard | lxd-conventions #16, scalability #2 | pool_usage_pct(pool) generalizado + cache + budget |
| `lab-stateless /24` agota IPs | scalability #12 | Ampliar a /23 |
| `ON CONFLICT` partial index sin WHERE | idempotency #2 | Sintaxis correcta SQLite ≥3.35 |
| Migración BD sin lock ni schema_version | idempotency #1 | schema_version + file lock + assert SQLite≥3.35 |
| `/verify` no re-valida matrícula activa | idempotency #15 | SELECT enrollments en /verify |
