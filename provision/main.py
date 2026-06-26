"""provision-api: FastAPI app + lifespan + routers de FASE 3.

CORS deshabilitado: Nginx es el único cliente HTTP del navegador (auth_request
y proxy). Las VMs llaman directo a PROVISION_URL_VM (red lab-persistent) con
su service token; esas llamadas NO pasan por Nginx.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import instances
from .auth import (
    get_current_alumno,
    issue_vm_token,
    limiter,
    router as auth_router,
    verify_vm_token,
)
from .config import Settings, get_settings
from .db import get_db, init_db, tx
from .jobs import JobWorker, enqueue_launch
from .policy import reset_to_base, restore_tag, snapshot_save

log = logging.getLogger("provision")

router = APIRouter()


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    app.state.settings = settings
    await reconcile_dry_run()
    worker = JobWorker(settings)
    app.state.worker = worker
    await worker.start()
    yield
    await worker.stop()


app = FastAPI(title="provision-api", version="0.3.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(auth_router)
app.include_router(router)


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
    """Admin vía X-Admin-Token (ADMIN_TOKEN en env). Comparación constante-tiempo.

    No basta con 127.0.0.1: Nginx proxya todo el tráfico al backend como
    127.0.0.1, así que cualquier alumno autenticado llegaría como localhost.
    Se exige token admin siempre.
    """
    import secrets as _s
    tok = request.headers.get("x-admin-token", "")
    expected = os.getenv("ADMIN_TOKEN", "")
    return bool(expected) and _s.compare_digest(tok, expected)


async def _snapshot_save(instancia: str) -> str:
    """Delega en policy.snapshot_save (pool guard reactivo + rotación FIFO)."""
    return await snapshot_save(instancia)


# --- /lab/* (auth cookie JWT) ----------------------------------------------
@router.post("/lab/start")
async def lab_start(
    request: Request,
    claims: dict = Depends(get_current_alumno),
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
async def lab_status(claims: dict = Depends(get_current_alumno)):
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
    from .reap import reap_stale
    destruidas = await reap_stale(settings)
    return {"destruidas": destruidas}