"""provision-api: FastAPI app + lifespan + routers de FASE 3 + FASE 6.

CORS deshabilitado: Nginx es el único cliente HTTP del navegador (auth_request
y proxy). Las VMs/apps llaman directo a PROVISION_URL_VM/PROVISION_URL_APP
(red lab-persistent/lab-stateless) con su service token; esas llamadas NO
pasan por Nginx.
"""
from __future__ import annotations

import ipaddress
import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import instances
from .auth import (
    get_current_alumno,
    get_current_alumno_lab,
    is_admin,
    issue_vm_token,
    limiter,
    router as auth_router,
    verify_vm_token,
)
from .config import Settings, get_settings
from .db import get_db, init_db, tx
from .jobs import JobWorker, enqueue_launch
from .policy import reset_to_base, restore_tag, snapshot_save
from .apps import router as apps_router
from .web import router as web_router

log = logging.getLogger("provision")

router = APIRouter()

# --- FASE 6.0: headers forjados que el cliente NO puede inyectar ----------
# Nginx los sobreescribe desde $upstream_http_*; el backend los ignora siempre
# al entrypoint y los reinyecta solo internamente desde /verify*.
_FORGED_HEADERS = (
    "x-lab-role", "x-admin-email", "x-lab-alumno", "x-lab-name",
    "x-lab-scope", "x-app-target",
)

# Rutas de navegador: solo accesibles desde 127.0.0.1 (Nginx).
# Las VMs/apps (10.50.10.0/23, 10.50.20.0/24) solo pueden llamar a rutas de
# service token (/heartbeat, /save, /reset, /restore, /snapshots).
_BROWSER_PREFIXES = (
    "/auth", "/lab", "/admin", "/verify", "/api", "/dashboard",
    "/apps", "/logout", "/lab/select",
)
_VM_ALLOWED_PREFIXES = (
    "/heartbeat", "/save", "/reset", "/restore", "/snapshots", "/healthz",
    "/metrics",
)
_LAB_STATELESS = ipaddress.ip_network("10.50.10.0/23")
_LAB_PERSISTENT = ipaddress.ip_network("10.50.20.0/24")


# --- lifespan ---------------------------------------------------------------
async def reconcile_dry_run() -> None:
    """Compara instancias en BD vs LXD. Dry-run: marca orphans, NO destruye.

    Borrado ciego en arranque está prohibido (destruiría VMs legítimas tras un
    reinicio del servicio). Solo marca `error` las `creando` huérfanas.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT nombre, estado FROM instancias WHERE estado != 'destruida'"
    ).fetchall()
    for r in rows:
        if not await instances.exists(r["nombre"]):
            log.warning(
                "orphan: %s en BD (estado=%s) pero ausente en LXD -- marcado error",
                r["nombre"], r["estado"],
            )
            conn.execute(
                "UPDATE instancias SET estado='error' WHERE nombre=? AND estado='creando'",
                (r["nombre"],),
            )
    conn.commit()


async def reconcile_apps_dry_run() -> None:
    """FASE 6.4: Reconcilia app_instances vs LXD. Dry-run (no delete ciego).

    - per-alumno ausente en LXD, estado IN (lista,detenida) → destruida.
    - shared always_on=0 ausente → destruida.
    - shared always_on=1 ausente → encolar job (auto-heal asíncrono).
    - creando huérfana (worker_heartbeat viejo) → error.
    """
    conn = get_db()
    rows = conn.execute(
        """SELECT ai.nombre_lxd, ai.estado, ai.app_id, ai.alumno, ai.worker_heartbeat,
                  a.shared, a.always_on
             FROM app_instances ai
             JOIN apps a ON a.id = ai.app_id
            WHERE ai.estado != 'destruida'"""
    ).fetchall()
    for r in rows:
        if not await instances.exists(r["nombre_lxd"]):
            if r["estado"] == "creando":
                conn.execute(
                    "UPDATE app_instances SET estado='error' WHERE nombre_lxd=? AND estado='creando'",
                    (r["nombre_lxd"],),
                )
                log.warning("orphan app: %s creando huérfana → error", r["nombre_lxd"])
            elif r["shared"] and r["always_on"]:
                # Auto-heal: encolar job (asíncrono, no bloquea arranque)
                conn.execute(
                    "UPDATE app_instances SET estado='creando' WHERE nombre_lxd=?",
                    (r["nombre_lxd"],),
                )
                from .jobs import enqueue_launch_app
                enqueue_launch_app(r["app_id"], None, r["nombre_lxd"])
                log.info("auto-heal: %s shared always_on=1 relanzada", r["nombre_lxd"])
            else:
                conn.execute(
                    "UPDATE app_instances SET estado='destruida' WHERE nombre_lxd=?",
                    (r["nombre_lxd"],),
                )
                log.info("orphan app: %s → destruida", r["nombre_lxd"])
    conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    app.state.settings = settings
    await reconcile_dry_run()
    worker = JobWorker(settings)
    app.state.worker = worker
    await worker.start()
    # FASE 6.4: reconcile apps asíncrono (no bloquea arranque)
    import asyncio as _aio
    _aio.create_task(reconcile_apps_dry_run())
    yield
    await worker.stop()


app = FastAPI(
    title="provision-api", version="0.4.0", lifespan=lifespan,
    docs_url=None, redoc_url=None, openapi_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def f6_hardening_middleware(request: Request, call_next):
    """FASE 6.0: borra headers forjados del cliente + aísla rutas navegador
    de las redes internas (VMs/apps solo pueden llamar a rutas de service
    token).
    """
    # 1. Borrar headers forjados que el cliente podría inyectar (defensa en
    #    profundidad: los endpoints además no los leen de la request).
    forged_lower = {h.encode() for h in _FORGED_HEADERS}
    scope = request.scope
    scope["headers"] = [
        (k, v) for (k, v) in scope.get("headers", []) if k not in forged_lower
    ]

    # 2. Aislamiento por red: VMs/apps no pueden llamar a rutas de navegador.
    peer = request.client.host if request.client else ""
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        peer_ip = None
    from_internal = (
        peer_ip is not None
        and (peer_ip in _LAB_STATELESS or peer_ip in _LAB_PERSISTENT)
    )
    path = request.url.path
    if from_internal and not any(path.startswith(p) for p in _VM_ALLOWED_PREFIXES):
        return JSONResponse({"detail": "forbidden from internal network"}, status_code=403)

    return await call_next(request)


app.include_router(auth_router)
app.include_router(router)
app.include_router(apps_router)
app.include_router(web_router)

# FASE 6.2: servir estáticos desde provision/web/static/
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _Path
_static_dir = _Path(__file__).resolve().parent / "web" / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


# --- helpers ----------------------------------------------------------------
def _bearer(request: Request) -> str:
    h = request.headers.get("authorization", "")
    if not h.startswith("Bearer "):
        raise HTTPException(401, "bearer required")
    return h[7:]


def _vm_remote_ip(request: Request) -> str:
    """IP de la VM tal como la ve el host (source de la conexión TCP directa)."""
    return request.client.host if request.client else ""


def _admin_ok(request: Request, settings: Settings) -> bool:
    """FASE 6.1: delega en auth.is_admin (cookie admin_token O X-Admin-Token)."""
    return is_admin(request, settings)


async def _snapshot_save(instancia: str) -> str:
    """Delega en policy.snapshot_save (pool guard reactivo + rotación FIFO)."""
    return await snapshot_save(instancia)


# --- /lab/* (auth cookie JWT) ----------------------------------------------
@router.post("/lab/start")
async def lab_start(
    request: Request,
    claims: dict = Depends(get_current_alumno_lab),
    settings: Settings = Depends(get_settings),
):
    """Lanza/recupera VM. Idempotente: una instancia por (alumno, lab).

    BEGIN IMMEDIATE + INSERT ON CONFLICT DO UPDATE SET estado='creando'
    WHERE estado IN ('destruida','error'). Si estado era creando/lista →
    202 sin relanzar. Encola job launch y responde 202.
    """
    alumno = claims["sub"]
    lab = claims["lab"]
    instancia = instances.instancia_nombre(alumno, lab)

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        cur = conn.execute(
            """INSERT INTO instancias(nombre, alumno, lab, estado)
               VALUES(?, ?, ?, 'creando')
               ON CONFLICT(alumno, lab) DO UPDATE SET
                 estado='creando', last_seen=datetime('now')
                 WHERE estado IN ('destruida','error')""",
            (instancia, alumno, lab),
        )
        relanzar = cur.rowcount > 0
        row = conn.execute(
            "SELECT estado, ip_rdp FROM instancias WHERE nombre=?", (instancia,)
        ).fetchone()
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise

    estado = row["estado"] if row else "creando"
    ip = row["ip_rdp"] if row else None

    if not relanzar:
        if estado == "lista":
            return JSONResponse(
                {"estado": "lista", "instancia": instancia, "ip_rdp": ip},
                status_code=200,
            )
        return JSONResponse({"estado": estado, "instancia": instancia}, status_code=202)

    enqueue_launch(alumno, lab)
    return JSONResponse({"estado": "creando", "instancia": instancia}, status_code=202)


@router.get("/lab/status")
async def lab_status(claims: dict = Depends(get_current_alumno_lab)):
    """Estado real de la instancia. Excluido del rate-limit global (polling)."""
    alumno = claims["sub"]
    lab = claims["lab"]
    instancia = instances.instancia_nombre(alumno, lab)
    row = get_db().execute(
        "SELECT estado, ip_rdp FROM instancias WHERE nombre=?", (instancia,)
    ).fetchone()
    if row is None:
        return {"estado": "inexistente", "instancia": instancia, "ip_rdp": None}
    return {"estado": row["estado"], "instancia": instancia, "ip_rdp": row["ip_rdp"]}


# --- VM endpoints (auth service token: scope + IP estricta) ----------------
@router.post("/heartbeat")
async def heartbeat(request: Request, settings: Settings = Depends(get_settings)):
    """Actualiza heartbeats.last_seen. Rota el service token (devuelve uno nuevo)."""
    token = _bearer(request)
    remote = _vm_remote_ip(request)
    claims = verify_vm_token(
        token, required_scope="heartbeat", remote_ip=remote, settings=settings
    )
    instancia = claims["sub"]
    with tx() as c:
        c.execute(
            "INSERT INTO heartbeats(instancia, last_seen) VALUES(?, datetime('now')) "
            "ON CONFLICT(instancia) DO UPDATE SET last_seen=datetime('now')",
            (instancia,),
        )
        c.execute(
            "UPDATE instancias SET last_seen=datetime('now') WHERE nombre=?",
            (instancia,),
        )
    new_token = issue_vm_token(instancia=instancia, vm_ip=remote, settings=settings)
    return JSONResponse({"token": new_token}, status_code=200)


@router.post("/save")
async def save(request: Request, settings: Settings = Depends(get_settings)):
    """Snapshot k1..k5 con rotación FIFO. instancia = sub del token (no del body)."""
    token = _bearer(request)
    remote = _vm_remote_ip(request)
    claims = verify_vm_token(
        token, required_scope="save", remote_ip=remote, settings=settings
    )
    instancia = claims["sub"]
    tag = await _snapshot_save(instancia)
    with tx() as c:
        c.execute(
            "INSERT INTO snapshots(instancia, tag) VALUES(?,?) ON CONFLICT DO NOTHING",
            (instancia, tag),
        )
    return {"tag": tag}


@router.post("/reset")
async def reset(request: Request, settings: Settings = Depends(get_settings)):
    """Restaura `base` sin recreate. Delega en policy.reset_to_base."""
    token = _bearer(request)
    remote = _vm_remote_ip(request)
    claims = verify_vm_token(
        token, required_scope="reset", remote_ip=remote, settings=settings
    )
    instancia = claims["sub"]
    await reset_to_base(instancia)
    return {"ok": True, "tag": "base"}


@router.post("/restore")
async def restore(
    request: Request,
    tag: str,
    settings: Settings = Depends(get_settings),
):
    """Restaura un snapshot arbitrario. Delega en policy.restore_tag."""
    token = _bearer(request)
    remote = _vm_remote_ip(request)
    claims = verify_vm_token(
        token, required_scope="reset", remote_ip=remote, settings=settings
    )
    instancia = claims["sub"]
    await restore_tag(instancia, tag)
    return {"ok": True, "tag": tag}


@router.get("/snapshots")
async def get_snapshots(request: Request, settings: Settings = Depends(get_settings)):
    token = _bearer(request)
    remote = _vm_remote_ip(request)
    claims = verify_vm_token(
        token, required_scope="save", remote_ip=remote, settings=settings
    )
    instancia = claims["sub"]
    snaps = await instances.list_snapshots(instancia)
    return {"snapshots": snaps}


# --- /admin/* (127.0.0.1 o X-Admin-Token) ---------------------------------
@router.post("/admin/destroy")
async def admin_destroy(
    request: Request,
    instancia: str,
    settings: Settings = Depends(get_settings),
):
    if not _admin_ok(request, settings):
        raise HTTPException(403, "admin required")
    instances._check_name(instancia)
    await instances.delete(instancia)
    with tx() as c:
        c.execute(
            "UPDATE instancias SET estado='destruida', ip_rdp=NULL WHERE nombre=?",
            (instancia,),
        )
        c.execute("DELETE FROM heartbeats WHERE instancia=?", (instancia,))
        c.execute("DELETE FROM vm_tokens WHERE instancia=?", (instancia,))
    return {"ok": True, "instancia": instancia}


@router.post("/admin/reap")
async def admin_reap(request: Request, settings: Settings = Depends(get_settings)):
    """Trigger HTTP del reaper (alternativa al timer systemd standalone)."""
    if not _admin_ok(request, settings):
        raise HTTPException(403, "admin required")
    from .reap import reap_stale, reap_apps
    destruidas_vms = await reap_stale(settings)
    destruidas_apps = await reap_apps(settings)
    return {"destruidas_vms": destruidas_vms, "destruidas_apps": destruidas_apps}


# --- FASE 6.4: /admin/instances + /metrics ---------------------------------
@router.get("/admin/instances")
async def admin_instances(
    request: Request,
    settings: Settings = Depends(get_settings),
    limit: int = 50,
    cursor: str = "",
):
    """Lista todas las instancias (VMs + apps). Paginación keyset."""
    if not _admin_ok(request, settings):
        raise HTTPException(403, "admin required")
    conn = get_db()
    vms = conn.execute(
        """SELECT 'vm' AS tipo, nombre, alumno, lab, estado, ip_rdp AS ip, last_seen
             FROM instancias WHERE estado != 'destruida'
            UNION ALL
           SELECT 'app' AS tipo, nombre_lxd AS nombre, alumno, app_id AS lab,
                  estado, ip, last_seen
             FROM app_instances WHERE estado != 'destruida'
            ORDER BY nombre LIMIT ?""",
        (limit + 1,),
    ).fetchall()
    items = [dict(r) for r in vms[:limit]]
    has_more = len(vms) > limit
    return {"instances": items, "has_more": has_more}


@router.get("/metrics")
async def metrics():
    """FASE 6.4: métricas básicas para Prometheus (formato texto)."""
    conn = get_db()
    apps_launched = conn.execute(
        "SELECT COUNT(*) FROM app_instances"
    ).fetchone()[0]
    apps_reaped = conn.execute(
        "SELECT COUNT(*) FROM app_instances WHERE estado='destruida'"
    ).fetchone()[0]
    apps_active = conn.execute(
        "SELECT COUNT(*) FROM app_instances WHERE estado IN ('creando','lista')"
    ).fetchone()[0]
    vms_active = conn.execute(
        "SELECT COUNT(*) FROM instancias WHERE estado IN ('creando','lista')"
    ).fetchone()[0]
    lines = [
        f"# TYPE apps_launched_total counter",
        f"apps_launched_total {apps_launched}",
        f"# TYPE apps_reaped_total counter",
        f"apps_reaped_total {apps_reaped}",
        f"# TYPE apps_active gauge",
        f"apps_active {apps_active}",
        f"# TYPE vms_active gauge",
        f"vms_active {vms_active}",
    ]
    return Response(content="\n".join(lines) + "\n", media_type="text/plain")