# Policy engine — snapshots, reset y auto-destrucción

Implementa la FASE 5 del PLAN: persistencia y ciclo de vida de las VMs de
alumno del proyecto `labs`. Módulo: `provision/policy.py`.

## 1. Esquema de snapshots

Solo las **VMs persistentes** (profile `persistent`, proyecto `labs`) reciben
snapshots nativos de LXD. Los contenedores `stateless` (apps stateless, FASE
6) son efímeros y **no se snapshotan**: reset = destroy + launch (recreate).

Naming canónico **en la instancia** (no en el alumno):

| Tag        | Cuándo se crea                                  | Inviolable |
|------------|-------------------------------------------------|------------|
| `base`     | Tras `cloud-init status --wait` + `status: done` + `healthcheck_rdp` OK | Sí |
| `k1..k5`   | Bajo demanda del alumno vía `POST /save`        | No (FIFO)  |

- `base` se crea una sola vez con precheck atómico (`instances.snapshot_create`
  es idempotente: si existe, no recrea).
- `k1..k5` son los estados intermedios del alumno. Retención máxima 5
  (`KEEP_SNAPSHOTS`), reducible a 3 por el pool guard.

## 2. Rotación FIFO

Source of truth = **LXD** (`instances.list_snapshots`), no un contador en BD.
Esto evita desincronización si el servicio reinicia, si un snapshot se borra
a mano, o si `lxc` falla a mitad de operación.

Al recibir `POST /save`:

1. Listar snapshots reales de la instancia.
2. Filtrar `k1..k5` (excluye `base`), ordenar ascendentemente.
3. Si `len(k_snaps) >= keep` → purgar el más viejo (`k_snaps[0]`).
4. Elegir el primer `kN` libre en `1..keep`.
5. `lxc snapshot <instancia> kN --project labs`.

No hay contador interno: el siguiente tag se deduce de los existentes. Así,
un `k3` borrado manualmente se reutiliza en el siguiente `/save`.

## 3. Pool guard reactivo

`persistent-pool` es ZFS sobre loop file de **40GB** → cota real ≤2-3 alumnos
con retención k1..k5. El pool guard reacciona al uso real antes de cada
operación que crece el pool:

| Uso del pool | Acción                                              |
|--------------|-----------------------------------------------------|
| > 90%        | `503` — no se crea snapshot (`pool_usage_ok()` = False) |
| > 75%        | Purgar el oldest **antes** de crear (despresurizar) |
| > 60%        | Reducir retención a `k1..k3` (`KEEP_LOW=3`)         |
| ≤ 60%        | Retención nominal `k1..k5`                          |

`pool_usage_pct()` lee `lxc storage info persistent-pool --format json` y
devuelve `used/total*100`. `pool_usage_ok()` es fail-closed: si no puede leer
el pool, devuelve `False` (no crea snapshots sobre un pool posiblemente lleno).

### Comprobación antes de `lxc launch`

El pool se comprueba **también antes de lanzar** una VM nueva (en `jobs.py`,
worker de lanzamiento), no solo en `/save`. Lanzar una VM adicional sobre un
pool > 90% se rechaza con 503. `policy.py` solo expone `pool_usage_pct()` y
`pool_usage_ok()`; la decisión de no lanzar vive en `jobs.py`.

## 4. Reset y restore

**Reset** = `lxc restore <instancia> base` (NO destroy + recreate). Una
instancia por (alumno, lab): se reutiliza el mismo contenedor de VM.

`reset_to_base(instancia)`:
1. Precheck: `base` existe en LXD → si no, `409`.
2. `stop --force` (idempotente si ya STOPPED).
3. `restore base`.
4. `start`.
5. `healthcheck_rdp` (30×2s: xrdp+xrdp-sesman activos + probe TCP 3389).

`restore_tag(instancia, tag)`:
1. Validar `tag` contra `TAG_RE` (`^(base|k[1-5])$`) → `ValueError` si no casa.
2. Precheck: `tag` existe en LXD → si no, `404`.
3. stop / restore / start / healthcheck (igual que reset).

Ambos centralizados en `policy.py` para reutilización desde los endpoints
`/reset` y `/restore` de `main.py`.

## 5. Auto-destrucción

Tres criterios configurables vía `.env`:

| Criterio              | Variable          | Comportamiento                                  |
|-----------------------|-------------------|-------------------------------------------------|
| Inactividad           | `IDLE_MINUTES=60` | `last_seen < now - IDLE_MINUTES` y sin sesión RDP activa |
| Deadline del lab      | `labs.deadline`   | Fecha límite por lab (en BD)                    |
| Fin de curso          | `COURSE_DEADLINE` | Fecha global `YYYY-MM-DD` (vacío = sin deadline) |

`last_seen` se actualiza por:
- `POST /heartbeat` (la VM llama cada 5 min vía `lab-heartbeat.timer`).
- Actividad RDP detectada en logs de guacd (deuda: integración FASE 4).

### Reaper standalone

`provision/reap.py` es un **proceso standalone** invocado por systemd timer
(`provision-reap.service` + `provision-reap.timer`), NO un endpoint HTTP al
worker único. Así no compite con uvicorn ni depende de que el worker esté vivo.

- `OnBootSec=2min`, `OnUnitActiveSec=5min`, `Persistent=true`,
  `RandomizedDelaySec=30s`.
- Ejecución: `python -m provision.reap`.

Algoritmo (anti-TOCTOU):

1. **Fase 1 (autocommit, WAL):** `SELECT` candidatos con
   `(julianday('now') - julianday(last_seen)) * 86400` como `idle_sec`.
   - `estado='creando'` + `idle_sec >= CREATING_TIMEOUT` → candidato.
   - `estado IN ('lista','detenida','error')` + `idle_sec >= IDLE_MINUTES*60`
     → candidato.
2. **Fase 2 (por candidato, dentro de tx):** `BEGIN IMMEDIATE` + re-check
   de `estado` e `idle_sec` **dentro** de la transacción. Si ya no cumple
   (un `/heartbeat` o `/lab/start` lo actualizó), `ROLLBACK` y se salta.
   Si sigue cumpliendo: `UPDATE estado='destruida'`, `DELETE` de heartbeats
   y vm_tokens, `COMMIT`, y **fuera** de la tx `instances.delete` (idempotente).
3. **Batch deletes** en lotes de 10 con `sleep(1)` entre lotes (no saturar LXD).

`datetime('now')` de SQLite (no `time.time()` de Python) para consistencia
ante saltos de reloj. `PRAGMA busy_timeout=5000` + `BEGIN IMMEDIATE` como mutex.

### `CREATING_TIMEOUT`

Segundos máximos que una instancia puede permanecer en `estado='creando'`
antes de que el reaper la considere estancada (p. ej. `lxc launch` colgado,
cloud-init que no termina). Default `600` (10 min). Al caducar, el reaper la
marca `destruida` y borra la VM en LXD. El alumno puede relanzar vía
`/lab/start` (el `ON CONFLICT DO UPDATE` reactiva una `destruida`).

### Locks anti-destrucción con sesión activa

El reaper no destruye VMs con sesión RDP activa. La detección de sesión vive
en `last_seen` actualizado por actividad guacd (deuda FASE 4); mientras tanto,
el heartbeat de la VM (cada 5 min) mantiene `last_seen` fresco y evita el
reaper aunque el alumno esté inactivo en el escritorio.

## 6. Reconciliación al arranque

`main.py` `reconcile_dry_run()` (en `lifespan`) compara BD vs LXD:
- Instancias en BD ausentes en LXD → marcan `error` (si estaban `creando`).
- **Nunca** `lxc delete` ciego en arranque (destruiría VMs legítimas tras un
  reinicio del servicio). Borrado solo vía `--apply` + grace period (deuda).

## 7. Cotas de escalabilidad

| Recurso                          | Cota              | Límite dominante       |
|----------------------------------|-------------------|------------------------|
| `persistent-pool` 40GB + k1..k5  | ≤2-3 alumnos      | Pool ZFS (cuello actual) |
| Retención reducida k1..k3 (>60%) | ~más alumnos      | Pool guard             |
| SQLite single-writer            | ≤50 alumnos       | Writer lock            |
| uvicorn workers=1 + job queue   | ≤4 lanzamientos  | Event loop             |
| `lab-persistent` /24            | ≤250 VMs          | Subred                 |
| RAM host (4GB/VM)               | N ≤ RAM_host / 4  | RAM                    |
| `stateless-pool` 80GB (FASE 6)  | ~60-80 contenedores | Pool ZFS             |
| RAM host (2GB/app, FASE 6)      | `min((RAM−VMs)/2GB, MAX_APP_INSTANCES)` | RAM |
| `lab-stateless` /23 (FASE 6)    | ~510 IPs          | Subred                 |
| `/verify/app` read-only (FASE 6)| ~200-500 req/s    | JWT decode             |
| Apps shared `always_on=1` (FASE 6) | `sum(memory_mb) ≤ ALWAYS_ON_BUDGET_MB` | RAM |

Deuda: ampliar `persistent-pool` a 80-120GB (recreación con `--force-preseed`)
si >3 alumnos, o mantener retención `k1..k3` por defecto. Para apps:
ampliar `stateless-pool` con `lxc storage set size=` (no destructivo).

## 8. Endpoints expuestos (delegados a `policy.py`)

| Endpoint                  | Delega en                | Respuesta         |
|---------------------------|--------------------------|-------------------|
| `POST /save`              | `policy.snapshot_save`   | `200 {tag}` / `503` |
| `POST /reset`             | `policy.reset_to_base`   | `200` / `409`     |
| `POST /restore?tag=k2`    | `policy.restore_tag`     | `200` / `404`     |
| `GET /snapshots`          | `instances.list_snapshots` | `200 {snapshots}` |
| `POST /admin/reap`        | `reap.reap_stale`        | `200 {destruidas}` |
| `POST /apps/{id}/reset` (FASE 6) | destroy + launch (recreate) | `200` / `403` (shared no admin) |

La VM invoca estos endpoints vía `curl` desde `lab-save` / `lab-reset` con su
service token (HS256, `scope=save|reset|heartbeat`, IP origen validada). Nunca
ejecuta `lxc` directamente. Las apps invocan `/heartbeat` con su service token
de app.

## 9. Validación (VMs)

- VM viva → 5× `POST /save` → `lxc info <inst> --project labs` muestra `k1..k5`.
- 6º `/save` → purga `k1` (FIFO basado en `lxc snapshot list`).
- `POST /reset` → `lxc info` restaura a `base`, xrdp up.
- `IDLE_MINUTES=1` → esperar +1 min → `systemctl start provision-reap.service`
  → instancia destruida, BD `estado='destruida'`.
- Pool guard: forzar pool > 90% (llenar ZFS) → `/save` devuelve `503`.
- Pool > 75% → `/save` purga oldest antes de crear.
- Pool > 60% → retención efectiva `k1..k3` (6º `/save` purga a los 3).

## 10. Apps stateless — lifecycle (FASE 6)

### Shared vs per-alumno
- `shared=1` (default): 1 instancia LXD para todos los alumnos del lab.
  `always_on=1`: siempre viva (no se reap). `always_on=0`: on-demand, se reap
  tras `SHARED_IDLE_HOURS=6`.
- `shared=0` (per-alumno): 1 instancia por alumno. On-demand, se reap tras
  `APP_IDLE_MINUTES=30`.

### Lanzamiento (job queue, no síncrono)
- `POST /apps/{app_id}/start` encola job `launch_app` (reusa `jobs.py`).
- Worker: `launch_container()` (sin `--vm`, perfil `stateless`) →
  `healthcheck_http` (HTTP real, no TCP) → `get_ip` (retry 10×1s) →
  `issue_app_token` → UPDATE `estado='lista'`, `ip=?`.
- `worker_heartbeat` cada 10s (reaper distingue `creando` activo de
  estancado: `worker_heartbeat < now-60s` → estancada, no timeout mágico).
- Semáforo `APP_LAUNCH_SEM=min(6, ram_gb//2)`.
- En fallo: `instances.delete` (cleanup) + UPDATE `estado='error'`.

### Reaper apps (`reap_apps()` en `reap.py`, timer separado
`provision-reap-apps.timer` OnUnitActiveSec=2min)
- Criterios: per-alumno inactiva > `APP_IDLE_MINUTES=30`; shared `always_on=0`
  inactiva > `SHARED_IDLE_HOURS=6`; shared `always_on=1` NUNCA; creando
  estancada (`worker_heartbeat < now-60s`).
- **Grace period tras reinicio**: ignorar candidatos con
  `last_seen < service_started_at + GRACE_AFTER_RESTART=15min` (evita
  masacrar apps legítimas tras reinicio de provision-api).
- `last_seen` vía **heartbeat activo de la app** (POST /heartbeat con service
  token, como las VMs). `/verify/app` es READ-ONLY (no escribe `last_seen`).
- Por candidato: `BEGIN IMMEDIATE` + re-check → **delete LXD con retry 3×5s**
  (clasificar error: not found=éxito, timeout=no UPDATE + `reap_attempts++` +
  backoff) → UPDATE `estado='destruida'` solo tras confirmar delete.
- Batch 25-50 + `asyncio.gather` (4 concurrentes).

### Pool guard stateless-pool (80GB, generalizado)
- `pool_usage_pct(pool)` generalizado. Cache 30s. Fail-closed con cache
  (no 503 global por fallo transitorio de `lxc storage info`).
- >90% → 503; >75% → purgar apps inactivas oldest (per-alumno primero,
  nunca shared `always_on=1`); >60% → reaper agresivo.
- **Budget preventivo**: `sum(memory_mb running + queued) < RAM_host -
  RAM_VMs - margen`. Hard cap: `count(estado IN creando,lista) <
  MAX_APP_INSTANCES`.

### Reset app
- destroy + launch (recreate). Sin snapshots (stateless).
- Per-alumno: alumno propietario (`claims["sub"] == app_instances.alumno`).
- Shared: **solo admin** (afecta a todos los alumnos).

### Reconciliación apps al arranque (asíncrona tras yield)
- per-alumno ausente en LXD, estado IN (lista,detenida) → `destruida`.
- shared `always_on=0` ausente → `destruida`.
- shared `always_on=1` ausente → **encolar job** (auto-heal asíncrono,
  respeta `ALWAYS_ON_BUDGET_MB`).
- creando huérfana (`worker_heartbeat < now-60s`) → `error`.
- NUNCA delete ciego.

### Validación (apps)
- App per-alumno viva → esperar `APP_IDLE_MINUTES+1` →
  `systemctl start provision-reap-apps.service` → instancia destruida.
- App shared `always_on=1` → reiniciar provision-api → auto-heal la relanza
  (asíncrono, no bloquea arranque).
- Pool guard: forzar `stateless-pool` > 90% → `/apps/.../start` devuelve 503.
- Reset app per-alumno → `lxc list` muestra destroy + launch.
- Reset app shared sin admin → 403.