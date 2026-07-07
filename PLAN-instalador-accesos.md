# PLAN DE IMPLEMENTACIÓN — Instalador autocontenido, documentación y portales admin/alumno

**Revisión 2 (2026-07-07, rama `main-imeplementacion`).** Todas las afirmaciones del plan previo han sido re-verificadas contra el código actual; se añaden hallazgos nuevos (F3.0). Plan ejecutable por `lab-build`.

---

## 0. Verificación del plan previo contra el código actual

### 0.1 Afirmaciones del plan previo — estado tras re-verificación

| Afirmación del plan previo | Verificado | Estado |
|---|---|---|
| `install-all.sh` instala deps pero `DEBIAN_FRONTEND` solo en el retry | SÍ (`install-all.sh:95-100`) | **VIGENTE** (F1) |
| `server-setup-lxd.sh` hace `snap install lxd` sin verificar `snapd` | SÍ (`server-setup-lxd.sh:34-35`) | **VIGENTE** (F1) |
| No hay preflight de KVM/ZFS/puertos/DNS/ufw | SÍ (no existe en ningún script) | **VIGENTE** (F1) |
| `guacamole/install.sh` usa `curl` + `tar` sin garantizarlos | SÍ (`guacamole/install.sh:44-45`) | **VIGENTE** (F1) |
| `provision/install.sh` asume `python3` (`python3 -m venv`, línea 37) | SÍ | **VIGENTE** (F1) |
| Bug CSP: `script-src 'self'` sin nonce (`web.py:22-27`) vs JS inline y `onclick=` en `login.html`, `dashboard.html`, `console.html` | SÍ (verificadas las 3 plantillas) | **VIGENTE** (F3.1) |
| `console.html:42` llama a `POST /admin/instances/{n}/destroy?tipo=` inexistente | SÍ (solo existe `POST /admin/destroy`, `main.py:380`, y solo limpia tablas de VM) | **VIGENTE** (F2.3) |
| No existen `/admin/labs`, `/admin/enrollments`, `/admin/instances/launch`, `PATCH /admin/apps` | SÍ (grep exhaustivo de rutas en `provision/`) | **VIGENTE** (F2) |
| `DELETE /admin/apps/{id}` es soft y no destruye instancias vivas | SÍ (`apps.py:290-300`) | **VIGENTE** (F2.4) |
| Tablas `labs`/`enrollments`/`admins`/`apps`/`app_lab` ya existen (sin cambios de esquema) | SÍ (`db.py:47,66,126,172,187`) | **VIGENTE** |
| `docs/USO.md` documenta funciones inexistentes (CRUD labs/matrículas desde consola, `/admin/instances/{n}/destroy`, forzar VM) | SÍ (`docs/USO.md:69-77,99-102`) | **VIGENTE** (F4) |
| Consola: pestañas Labs/Matrículas = "pendiente de UI" | SÍ (`console.html:36`) | **VIGENTE** (F3.2) |
| Regla guacd respetada en `/desktop/` (proxy a :8080, nunca a 4822/3389) | SÍ (`nginx/lab.conf:110-137`) | Sin cambios |
| iframe `sandbox="allow-scripts allow-forms"` sin `allow-same-origin` | SÍ (`dashboard.html:81`) | Sin cambios |

**Nada del plan previo está ya resuelto en el código**: los tres requisitos siguen abiertos tal como se describieron. Las fases F1–F5 previas siguen vigentes íntegras; este plan las conserva y añade **F3.0** (nuevos bugs) y correcciones puntuales a F2/F3.

### 0.2 Hallazgos NUEVOS de esta verificación (no estaban en el plan previo)

1. **`nginx/lab.conf:140` — location de apps inválida.** `location ^~ /apps/(?<app_id>[a-z0-9-]+)/` mezcla el modificador de prefijo `^~` con sintaxis regex: Nginx trata `(?<app_id>...)` como **prefijo literal**, por lo que esa location **nunca casa** con `/apps/jupyter/...` y `$app_id` nunca se define. El acceso del alumno a apps vía navegador está roto a nivel Nginx.
2. **Faltan rutas Nginx para la API de apps del alumno y logout.** `GET /apps` (catálogo que consume `dashboard.html:14`), `POST /apps/{id}/start|status|reset` (`dashboard.html:59,69`) y `POST /logout` (`dashboard.html:3`) no casan con ninguna `location` → 404 en Nginx. Además, si se arregla la location del punto 1 tal cual, `/apps/{id}/start` sería tragado por el proxy hacia el contenedor (conflicto de rutas).
3. **Login admin roto detrás de Nginx.** `/admin/auth/request` y `/admin/auth/verify` (magic link admin, deben ser públicos) caen bajo `location /admin/` con `auth_request /verify_admin` → 401 sin cookie: imposible hacer login admin vía navegador. Solo `= /admin/login` es público (`lab.conf:163-179`).
4. **`GET /admin/instances` acepta `cursor` pero no lo usa** (`main.py:417-432`: `LIMIT ?` sin `WHERE nombre > cursor`) — la paginación keyset está rota a partir de la página 1.
5. **Detalles para F3.1**: `login.html:18` usa Jinja **dentro** del `<script>` (`{% if admin %}`) — al extraer el JS a estático hay que pasar el modo por atributo DOM (`data-admin`). Y `openApp` (`dashboard.html:59`) y `destroyInst` (`console.html:42`) no envían `X-Requested-With`, que los endpoints nuevos/futuros exigirán.

---

## 1. Fases de implementación (orden para lab-build)

```
F1 (instalador) ────────────────────────────────┐
F2 (API admin) ──► F3.0 (Nginx) ──► F3.1 (CSP) ──► F3.2 (UI admin) ──► F4 (docs) ──► F5 (E2E)
     (F3.0 y F3.1 no dependen de F2 y pueden ir en paralelo con ella)
```

---

### FASE F1 — Instalador autocontenido (Requisito 1)

**Archivos**: `install-all.sh`, `server-setup-lxd.sh`.

**F1.1 — `install-all.sh`:**
- Exportar `DEBIAN_FRONTEND=noninteractive` justo tras el parse de args (hoy solo en el retry, línea 98) + preseed debconf:
  ```bash
  echo 'iptables-persistent iptables-persistent/autosave_v4 boolean true' | debconf-set-selections
  echo 'iptables-persistent iptables-persistent/autosave_v6 boolean true' | debconf-set-selections
  ```
- Ampliar `DEPS` (línea 95): añadir `python3 ca-certificates snapd zfsutils-linux tar gzip`.
- Nueva sección **`0b. Preflight`** antes de la desinstalación previa (fail-fast, mensajes accionables, flag `--skip-preflight` que degrada aborts a warnings):
  - SO: `. /etc/os-release` → abortar si no es Ubuntu 22.04/24.04.
  - **KVM (ABORT)**: `[ -e /dev/kvm ]`; si falta → "habilita VT-x/AMD-V o virtualización anidada". Sin esto el fallo aparece tardío y críptico en `build-lab-vm-base-mate.sh`.
  - **ZFS (ABORT)**: `modprobe zfs || { apt-get install -y zfsutils-linux "linux-modules-extra-$(uname -r)"; modprobe zfs; }` — el preseed usa `driver: zfs` en ambos pools.
  - **snapd**: `command -v snap || apt-get install -y snapd`; luego `snap wait system seed.loaded`.
  - Puertos 80/443 ocupados por algo distinto de nginx → ABORT.
  - DNS del `--domain` (`getent hosts`) → WARN (certbot dará el veredicto).
  - `ufw` activo → WARN (convivencia con iptables del proyecto).
  - RAM `<8GB` / disco `<100GB` → WARN (cotas de `docs/policy.md`).
- (Opcional, hardening menor) dejar de imprimir `ADMIN_TOKEN`/`JWT_SECRET` por stdout en el resumen final (líneas 349-352); indicar solo la ruta `/etc/provision/provision.env`.

**F1.2 — `server-setup-lxd.sh`:** guard defensivo antes de `snap install lxd` (línea 34): `command -v snap >/dev/null || { echo "ERROR: snapd no instalado (ejecuta install-all.sh)"; exit 1; }`. La instalación real de snapd la hace F1.1 (una responsabilidad por script).

**Criterios de aceptación**
```bash
bash -n install-all.sh server-setup-lxd.sh
# En VM limpia con nested KVM, sin ningún apt/snap manual previo:
sudo bash install-all.sh --domain=... --email=...
lxc storage list && lxc network list && lxc profile list && lxc project list && lxc image list local
systemctl is-active provision nginx docker snapd
sudo bash install-all.sh --domain=... --email=...   # re-ejecución idempotente
# En VM SIN KVM y en VM sin zfs.ko: el preflight aborta con mensaje claro ANTES de tocar nada.
```

**Críticos**: critic-idempotency (checks re-ejecutables), critic-reliability (KVM/ZFS = abort, no warn), critic-security (no repos externos: mantener `docker.io` de Ubuntu; secretos fuera de stdout). *Rechazado del plan previo (se mantiene el rechazo)*: `preflight.sh` separado — rompería el entrypoint único.

---

### FASE F2 — Backend consola admin (Requisito 3, admin)

**Archivo nuevo `provision/admin.py`** (APIRouter incluido en `main.py`; queda tras `auth_request /verify_admin` de Nginx + `is_admin()` in-app). Toda mutación exige `X-Requested-With: XMLHttpRequest` (patrón de `apps.py:167`).

1. **Labs**: `GET /admin/labs` (con nº matriculados e instancias vivas) · `POST /admin/labs` (`{nombre, imagen='local:lab-vm-base', deadline?}`; validar nombre con `^(?!app-)[a-z0-9][a-z0-9-]{1,30}$` — reutilizar `instances.NAME_RE` — y existencia de imagen vía `instances.lxc("image","show",...)` como `apps.py:262`; `INSERT OR IGNORE`) · `PATCH /admin/labs/{nombre}` (imagen/deadline/activo; desactivar = soft).
2. **Matrículas**: `GET /admin/enrollments?lab=&cursor=` (keyset real) · `POST /admin/enrollments` (`{alumno_id, email, lab}`; validar regex, email, lab activo; `INSERT OR IGNORE`) · `PATCH /admin/enrollments` (`{email, lab, active}`).
3. **Instancias**:
   - `POST /admin/instances/{nombre}/destroy?tipo=vm|app` — el endpoint que `console.html:42` y USO.md ya esperan. `tipo=vm`: lógica de `admin_destroy` actual. `tipo=app`: validar con `instances.APP_NAME_RE`, `instances.delete()` + `app_instances→'destruida'` + limpiar `app_tokens`, con re-check de estado en `BEGIN IMMEDIATE` (anti-TOCTOU, patrón `reap.py`). Mantener `POST /admin/destroy` como alias deprecado.
   - `POST /admin/instances/launch` (`{alumno, lab}`): verificar matrícula activa, upsert `instancias` estado `creando` y **`enqueue_launch()`** — factorizar el bloque `BEGIN IMMEDIATE` de `lab_start` (`main.py:246-277`) en un helper compartido. Nunca síncrono.
   - **FIX nuevo**: implementar de verdad el `cursor` en `GET /admin/instances` (hoy se ignora, `main.py:417`): `WHERE nombre > ? ORDER BY nombre LIMIT ?` y devolver `next_cursor`.
4. **Apps** (en `provision/apps.py`): `PATCH /admin/apps/{app_id}` (editar campos + reactivar; si activa `always_on`, revalidar `ALWAYS_ON_BUDGET_MB` como el POST) · `DELETE /admin/apps/{app_id}`: además del soft-delete, **encolar** la destrucción de las `app_instances` vivas (vía job/reaper, no bucle síncrono).

**Archivos a modificar**: `provision/main.py` (include_router, helper de lanzamiento, fix cursor), `provision/apps.py`. **Sin cambios de esquema.**

**Criterios de aceptación**
```bash
curl -s -X POST http://127.0.0.1:8000/admin/labs -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -H 'X-Requested-With: XMLHttpRequest' \
  -d '{"nombre":"lab2","imagen":"local:lab-vm-base"}'
curl -s http://127.0.0.1:8000/admin/enrollments -H "X-Admin-Token: $ADMIN_TOKEN"
# Lanzamiento forzado → job en cola, respuesta 202 inmediata:
sudo sqlite3 /var/lib/provision/provision.db "SELECT tipo,instancia,estado FROM jobs ORDER BY id DESC LIMIT 3;"
lxc list --project labs   # VM con perfil persistent, nunca default
# Nombres inválidos (app-*, mayúsculas, >30 chars) → 422/400, nunca llegan a lxc
```

**Críticos**: critic-security (regex de oro, `X-Requested-With`, `_check_name` antes de todo `lxc`; gestión de admins queda fuera de la UI deliberadamente — vía SQL documentada), critic-reliability (TOCTOU en destroy, job queue obligatoria), critic-scalability (keyset en enrollments E instances), critic-lxd-conventions (launch forzado reutiliza el mismo camino que `/lab/start`: perfil `persistent`, proyecto `labs`, cloud-init por stdin — cero código de lanzamiento nuevo).

---

### FASE F3.0 — Reparar enrutado Nginx (NUEVA — bloqueante para ambos portales)

**Archivo**: `nginx/lab.conf` (y verificación de `nginx/install.sh` que lo instancia).

1. **Location de apps**: sustituir `location ^~ /apps/(?<app_id>[a-z0-9-]+)/` (línea 140, sintaxis inválida) por `location ~ ^/apps/(?<app_id>[a-z0-9-]+)/`. Sin esto, `$app_id` nunca se define y el proxy a apps no funciona.
2. **API de apps del alumno**: para evitar que `start|status|reset` colisionen con el proxy al contenedor, **añadir alias FastAPI** `GET /api/apps`, `POST /api/apps/{id}/start`, `GET /api/apps/{id}/status`, `POST /api/apps/{id}/reset` en `provision/apps.py` (mismas funciones, rutas adicionales) — quedan cubiertas por la `location /api/` existente con `auth_request /verify`. Mantener las rutas antiguas para las llamadas internas/VM. `dashboard` (F3.1) pasa a llamar a `/api/apps/...`. *Alternativa rechazada*: ordenar regex en Nginx (`~ ^/apps/[a-z0-9-]+/(start|status|reset)$` antes del proxy) — frágil si una app sirve rutas homónimas.
3. **Logout alumno**: añadir `location = /logout { auth_request /verify; proxy_pass ... }` (o público: el endpoint ya exige `X-Requested-With` y borra cookie).
4. **Login admin**: añadir locations públicas exactas `= /admin/auth/request` y `= /admin/auth/verify` **antes** de `location /admin/` (el rate-limit lo aporta slowapi en la app). Sin esto el magic link admin devuelve 401 y el login por navegador es imposible.

**Criterios de aceptación**
```bash
nginx -t
curl -sk -X POST https://$DOM/admin/auth/request -H 'Content-Type: application/json' \
  -H 'X-Requested-With: XMLHttpRequest' -d '{"email":"admin@..."}'   # 200/202, NO 401
curl -sk https://$DOM/api/apps -b "lab_token=..."                    # catálogo, NO 404
sudo ss -tlnp | grep -E ':(3389|5900|3000|8888)'                     # vacío: guacd sigue siendo el único camino RDP
```

**Críticos**: critic-security (las nuevas locations públicas son `= exactas`, nada más se abre; `/verify_app` sigue READ-ONLY), critic-reliability (rutas API alumno nunca proxyadas al contenedor), critic-lxd-conventions (regla guacd intacta: `/desktop/` sigue yendo solo a :8080).

---

### FASE F3.1 — Fix CSP (bloqueante, ambos portales)

- Crear `provision/web/static/js/login.js`, `dashboard.js`, `admin.js` con el JS hoy inline; sustituir todo `onclick=` por `data-*` + `addEventListener` (la CSP también bloquea handlers inline).
- `login.html`: el condicional Jinja `{% if admin %}` de la línea 18 se traslada a un atributo (`<form id="login-form" data-admin="{{ 'true' if admin else 'false' }}">`); `login.js` elige endpoint según ese atributo.
- Añadir `X-Requested-With: XMLHttpRequest` a `openApp` y `destroyInst` (hoy no lo envían; los endpoints F2 lo exigen).
- Renderizar con `createElement`/`textContent`, **no** `innerHTML` interpolado (hoy `dashboard.html:21-41` y `console.html:22-34` interpolan datos de BD en template strings — XSS almacenado posible con datos creados por admin).
- `dashboard.js` llama a `/api/apps/...` (F3.0.2).
- **No relajar la CSP** de `web.py:22` (ni nonce ni `unsafe-inline`).
- Mantener iframe `sandbox="allow-scripts allow-forms"` sin `allow-same-origin`.

### FASE F3.2 — Completar consola admin (UI)

`console.html` + `admin.js`:
- **Labs**: tabla (nombre, imagen, deadline, activo, matriculados) + alta + toggle activo + edición.
- **Matrículas**: tabla filtrable por lab + alta (alumno_id, email, lab) + baja/realta + botón **"Lanzar VM"** (→ `POST /admin/instances/launch`).
- **Apps**: formulario de alta (id, nombre, imagen `local:app-*`, puerto, shared, always_on, cpu/mem, labs) + editar/desactivar/reactivar/start/stop/reset shared.
- **Instancias**: botón Destruir funcional (endpoint F2.3) + paginación con `next_cursor`.

**Criterios de aceptación F3 (conjunto)**
```bash
curl -skI https://$DOM/dashboard -b "lab_token=..." | grep -i content-security-policy  # sigue estricta
# DevTools sin errores CSP. Flujos completos en navegador:
#   admin: login (magic link) → crear lab → matricular → lanzar VM → ver estado → destruir
#   alumno: login → dashboard → abrir escritorio MATE (vía guacd) → abrir app (iframe sandbox)
```

**Críticos F3**: critic-security (DOM seguro, CSP intacta, sandbox intacto), critic-reliability (polling de status con timeout, ya existente).

---

### FASE F4 — Documentación (Requisito 2; tras F1–F3 para que describa la realidad)

1. `docs/DEPLOY.md`: §0 pre-requisitos → "Ubuntu Server 22.04/24.04 limpio + root + DNS + 80/443 + SMTP"; documentar el preflight y sus errores (KVM, zfs.ko, snapd, puertos); troubleshooting (exit 100 re-login, certbot/DNS, SMTP vacío).
2. `docs/USO.md`: reescribir §"Consola admin" con los flujos web reales (ahora sí existirán); dejar `sqlite3`/`curl` como "Operación avanzada / fallback"; documentar que el alta de admins es solo-SQL por diseño; corregir los `curl` de `/admin/instances/{n}/destroy` (que pasarán a ser reales).
3. `README.md`: quickstart "host limpio, sin dependencias previas".
4. `CLAUDE.md`: nota de `provision/admin.py`, del preflight y de los alias `/api/apps/*`.

**Criterio de aceptación**: revisión cruzada — cada comando/endpoint citado en docs existe en código (grep de rutas vs docs). Sin críticos obligatorios (revisión editorial), pero critic-security repasa que ningún ejemplo de doc exponga secretos.

---

### FASE F5 — Validación end-to-end

```bash
# Host limpio (VM nested-KVM): instalación sin intervención manual
sudo bash install-all.sh --domain=... --email=... --smtp-user=... --smtp-pass=...
# Reglas de oro:
sudo ss -tlnp | grep -E ':(3389|5900|3000|8888)'          # vacío
lxc list --project labs -c np | grep -v default           # perfiles restringidos
docker ps --format '{{.Names}} {{.Ports}}' | grep guacd   # sin puertos publicados
# Flujo admin y alumno completos por navegador (F2+F3.0-F3.2)
sudo bash uninstall-all.sh --yes --domain=...             # desinstalación limpia
```

**Críticos**: los 5, sobre el resultado integrado.

---

## 2. Críticas integradas (resumen de resoluciones)

| Crítico | Hallazgo | Resolución |
|---|---|---|
| security | No añadir Docker CE de docker.com | Aceptado: `docker.io` de Ubuntu |
| security | XSS almacenado vía innerHTML interpolado | Aceptado: render con nodos DOM (F3.1) |
| security | Locations públicas nuevas en Nginx | Aceptado: solo `= exactas` para `/admin/auth/*` y `/logout` |
| security | Gestión de admins vía UI | Rechazado deliberadamente: privilegio máximo queda solo-SQL, documentado |
| idempotency | Preflight re-ejecutable | Aceptado: patrón "verificar → instalar solo si falta" |
| reliability | KVM/ZFS deben abortar, no avisar | Aceptado |
| reliability | Destroy admin vs reaper (doble delete) | Aceptado: re-check en `BEGIN IMMEDIATE` + delete tolerante a not-found |
| scalability | Keyset pagination día 1 | Aceptado, y **ampliado**: arreglar el `cursor` ignorado de `/admin/instances` |
| lxd-conventions | Launch forzado = mismo camino que `/lab/start` | Aceptado: helper factorizado, cero lógica de lanzamiento nueva |
| (previo) | `preflight.sh` separado | Rechazado: rompe el entrypoint único |
| (nuevo) | Ordenar regex Nginx para API de apps | Rechazado por frágil; se usan alias `/api/apps/*` |

## 3. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Preflight demasiado estricto | `--skip-preflight` (aborts → warnings, "bajo tu responsabilidad") |
| Fix Nginx rompe el proxy de apps existente | F3.0 se valida aislada con `nginx -t` + curl antes de F3.1/F3.2 |
| Alias `/api/apps/*` divergen de `/apps/*` | Alias = mismas funciones registradas dos veces, no copias |
| Docs vuelven a divergir | F4 al final + verificación docs↔rutas en F5 |

## 4. Bugs que lab-build debe corregir sí o sí (verificados hoy)

1. CSP `provision/web.py:22` vs JS inline en las 3 plantillas (portal roto bajo CSP).
2. `nginx/lab.conf:140`: `^~` + regex inválido — apps inaccesibles y `$app_id` indefinido.
3. Nginx sin rutas para `/apps` (catálogo), `/apps/{id}/start|status|reset` y `/logout` — dashboard alumno roto.
4. Nginx bloquea `/admin/auth/request|verify` tras `auth_request` — login admin por navegador imposible.
5. `console.html:42` → endpoint `POST /admin/instances/{n}/destroy` inexistente.
6. `main.py:417`: parámetro `cursor` de `/admin/instances` ignorado.
7. `docs/USO.md:69-77,99-102` documenta funcionalidad admin inexistente.
