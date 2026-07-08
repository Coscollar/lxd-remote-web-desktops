"""FASE 6.4 — Apps stateless: catálogo + endpoints + /verify/app.

Apps stateless = contenedores LXD (perfil stateless, red lab-stateless).
Lanzamiento vía job queue (no síncrono). /verify/app es READ-ONLY.
"""
from __future__ import annotations

import ipaddress
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import instances
from .auth import get_current_alumno, is_admin
from .config import Settings, get_settings
from .db import get_db, tx

log = logging.getLogger("provision.apps")

router = APIRouter()

_LAB_STATELESS = ipaddress.ip_network("10.50.10.0/23")


# --- Modelos ----------------------------------------------------------------
class AppCreate(BaseModel):
    id: str
    nombre: str
    imagen: str
    shared: int = 1
    always_on: int = 0
    puerto_http: int
    cpu: int = 2
    memory_mb: int = 2048
    cmd: Optional[str] = None
    descripcion: Optional[str] = None
    labs: list[str] = []


class AppPatch(BaseModel):
    """F2.4: edición parcial del catálogo (incluye reactivar con activo=1)."""
    nombre: Optional[str] = None
    imagen: Optional[str] = None
    shared: Optional[int] = None
    always_on: Optional[int] = None
    puerto_http: Optional[int] = None
    cpu: Optional[int] = None
    memory_mb: Optional[int] = None
    cmd: Optional[str] = None
    descripcion: Optional[str] = None
    activo: Optional[int] = None
    labs: Optional[list[str]] = None


# --- Helpers ----------------------------------------------------------------
def _app_exists(app_id: str) -> bool:
    row = get_db().execute("SELECT 1 FROM apps WHERE id=? AND activo=1", (app_id,)).fetchone()
    return row is not None


def _apps_for_alumno(alumno_id: str) -> list[dict]:
    """Apps disponibles para el alumno (app_lab↔enrollments)."""
    conn = get_db()
    rows = conn.execute(
        """SELECT DISTINCT a.id, a.nombre, a.shared, a.always_on, a.puerto_http,
                  a.descripcion
             FROM apps a
             JOIN app_lab al ON al.app_id = a.id
             JOIN enrollments e ON e.lab = al.lab
            WHERE e.alumno_id=? AND e.active=1 AND a.activo=1""",
        (alumno_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _resolve_app_instance(app_id: str, alumno_id: str) -> Optional[dict]:
    """Resuelve la instancia de app para el alumno (shared o per-alumno)."""
    conn = get_db()
    app = conn.execute("SELECT * FROM apps WHERE id=? AND activo=1", (app_id,)).fetchone()
    if app is None:
        return None
    if app["shared"]:
        row = conn.execute(
            "SELECT * FROM app_instances WHERE app_id=? AND alumno IS NULL",
            (app_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM app_instances WHERE app_id=? AND alumno=?",
            (app_id, alumno_id),
        ).fetchone()
    return dict(row) if row else None


# --- Endpoints alumno -------------------------------------------------------
# F3.0: cada endpoint se registra TAMBIÉN bajo /api/apps/* (alias, misma
# función). Motivo: en Nginx, /apps/{id}/... proxya al contenedor de la app;
# la API del alumno viaja por `location /api/` (auth_request /verify) sin
# colisionar con ese proxy. Las rutas /apps/* se conservan para llamadas
# internas ya existentes.
@router.get("/api/apps")
@router.get("/apps")
async def list_apps(claims: dict = Depends(get_current_alumno)):
    """Apps stateless disponibles para el alumno."""
    return {"apps": _apps_for_alumno(claims["sub"])}


@router.post("/api/apps/{app_id}/start")
@router.post("/apps/{app_id}/start")
async def start_app(
    app_id: str,
    claims: dict = Depends(get_current_alumno),
    settings: Settings = Depends(get_settings),
):
    """Encola job launch_app. Idempotente (ON CONFLICT partial index). 202."""
    alumno_id = claims["sub"]
    # Validar acceso
    apps = _apps_for_alumno(alumno_id)
    if not any(a["id"] == app_id for a in apps):
        raise HTTPException(403, "no tienes acceso a esta app")
    app = next(a for a in apps if a["id"] == app_id)

    from .jobs import enqueue_launch_app
    nombre_lxd = instances.app_instancia_nombre(app_id, None if app["shared"] else alumno_id)

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        if app["shared"]:
            cur = conn.execute(
                """INSERT INTO app_instances(app_id, alumno, nombre_lxd, puerto_http, estado)
                   VALUES(?, NULL, ?, ?, 'creando')
                   ON CONFLICT(app_id) WHERE alumno IS NULL DO UPDATE SET
                     estado='creando', last_seen=datetime('now')
                     WHERE estado IN ('destruida','error')""",
                (app_id, nombre_lxd, app["puerto_http"]),
            )
        else:
            cur = conn.execute(
                """INSERT INTO app_instances(app_id, alumno, nombre_lxd, puerto_http, estado)
                   VALUES(?, ?, ?, ?, 'creando')
                   ON CONFLICT(app_id, alumno) WHERE alumno IS NOT NULL DO UPDATE SET
                     estado='creando', last_seen=datetime('now')
                     WHERE estado IN ('destruida','error')""",
                (app_id, alumno_id, nombre_lxd, app["puerto_http"]),
            )
        relanzar = cur.rowcount > 0
        row = conn.execute(
            "SELECT estado, ip FROM app_instances WHERE nombre_lxd=?", (nombre_lxd,)
        ).fetchone()
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise

    if not relanzar:
        estado = row["estado"] if row else "creando"
        if estado == "lista":
            return {"estado": "lista", "nombre_lxd": nombre_lxd, "url": f"/apps/{app_id}/"}
        return JSONResponse({"estado": estado, "nombre_lxd": nombre_lxd}, status_code=202)

    enqueue_launch_app(app_id, alumno_id if not app["shared"] else None, nombre_lxd)
    return JSONResponse({"estado": "creando", "nombre_lxd": nombre_lxd}, status_code=202)


@router.get("/api/apps/{app_id}/status")
@router.get("/apps/{app_id}/status")
async def app_status(
    app_id: str,
    claims: dict = Depends(get_current_alumno),
):
    """Estado real de la instancia de app del alumno (o shared)."""
    row = _resolve_app_instance(app_id, claims["sub"])
    if row is None:
        return {"estado": "inexistente", "url": None}
    return {"estado": row["estado"], "url": f"/apps/{app_id}/" if row["estado"] == "lista" else None}


@router.post("/api/apps/{app_id}/reset")
@router.post("/apps/{app_id}/reset")
async def reset_app(
    app_id: str,
    request: Request,
    claims: dict = Depends(get_current_alumno),
    settings: Settings = Depends(get_settings),
):
    """Reset app = destroy + launch (recreate). Sin snapshots."""
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(403, "X-Requested-With required")
    alumno_id = claims["sub"]
    apps = _apps_for_alumno(alumno_id)
    app = next((a for a in apps if a["id"] == app_id), None)
    if app is None:
        raise HTTPException(403, "no tienes acceso a esta app")
    # Shared: solo admin puede resetear
    if app["shared"] and not is_admin(request, settings):
        raise HTTPException(403, "reset de app shared requiere admin")
    # Per-alumno: validar ownership
    if not app["shared"]:
        row = _resolve_app_instance(app_id, alumno_id)
        if row and row["alumno"] != alumno_id:
            raise HTTPException(403, "no eres el propietario")

    nombre_lxd = instances.app_instancia_nombre(app_id, None if app["shared"] else alumno_id)
    # destroy + launch (recreate)
    await instances.delete(nombre_lxd)
    from .jobs import enqueue_launch_app
    with tx() as c:
        # Guard: no resucitar una instancia en destrucción administrativa.
        cur = c.execute(
            "UPDATE app_instances SET estado='creando', ip=NULL, last_seen=datetime('now') "
            "WHERE nombre_lxd=? AND estado != 'destruyendo'",
            (nombre_lxd,),
        )
        resucitable = cur.rowcount > 0
    if not resucitable:
        raise HTTPException(409, "la app está en proceso de destrucción")
    enqueue_launch_app(app_id, None if app["shared"] else alumno_id, nombre_lxd)
    return {"ok": True, "nombre_lxd": nombre_lxd}


# --- /verify/app (READ-ONLY, para Nginx auth_request) ----------------------
@router.get("/verify/app")
async def verify_app(
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """READ-ONLY: valida JWT + pertenencia app↔alumno + IP rango.
    Devuelve X-App-Target: <ip>:<puerto>. No escribe last_seen.
    """
    from .auth import verify_jwt
    token = request.cookies.get("lab_token")
    if not token:
        return Response(status_code=401)
    try:
        claims = verify_jwt(token, settings)
    except Exception:
        return Response(status_code=401)
    # jti revocado?
    row = get_db().execute(
        "SELECT 1 FROM jwt_jti WHERE jti=?", (claims["jti"],)
    ).fetchone()
    if row is not None:
        return Response(status_code=401)

    app_id = request.headers.get("x-requested-app", "")
    if not app_id:
        return Response(status_code=400)

    alumno_id = claims["sub"]
    inst = _resolve_app_instance(app_id, alumno_id)
    if inst is None or inst["estado"] != "lista" or not inst["ip"]:
        return Response(status_code=503)

    # Validar IP ∈ 10.50.10.0/23 (anti-SSRF)
    try:
        ip = ipaddress.ip_address(inst["ip"])
        if ip not in _LAB_STATELESS:
            return Response(status_code=403)
    except ValueError:
        return Response(status_code=403)

    target = f"{inst['ip']}:{inst['puerto_http']}"
    return Response(status_code=200, headers={"X-App-Target": target})


# --- Endpoints admin (catálogo) --------------------------------------------
@router.get("/admin/apps")
async def admin_list_apps(
    request: Request,
    settings: Settings = Depends(get_settings),
):
    if not is_admin(request, settings):
        raise HTTPException(403, "admin required")
    rows = get_db().execute("SELECT * FROM apps ORDER BY id").fetchall()
    return {"apps": [dict(r) for r in rows]}


@router.post("/admin/apps")
async def admin_create_app(
    body: AppCreate,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    if not is_admin(request, settings):
        raise HTTPException(403, "admin required")
    # Validar imagen existe en LXD
    rc, _, _ = await instances.lxc("image", "show", body.imagen)
    if rc != 0:
        raise HTTPException(400, f"imagen {body.imagen} no encontrada en labs")
    # Validar ALWAYS_ON_BUDGET_MB
    if body.always_on:
        total = get_db().execute(
            "SELECT COALESCE(SUM(memory_mb),0) FROM apps WHERE always_on=1 AND activo=1"
        ).fetchone()[0]
        if total + body.memory_mb > settings.always_on_budget_mb:
            raise HTTPException(409, f"ALWAYS_ON_BUDGET_MB excedido ({total + body.memory_mb} > {settings.always_on_budget_mb})")
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        conn.execute(
            """INSERT OR IGNORE INTO apps(id, nombre, imagen, shared, always_on, puerto_http, cpu, memory_mb, cmd, descripcion)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (body.id, body.nombre, body.imagen, body.shared, body.always_on,
             body.puerto_http, body.cpu, body.memory_mb, body.cmd, body.descripcion),
        )
        for lab in body.labs:
            conn.execute("INSERT OR IGNORE INTO app_lab(app_id, lab) VALUES(?,?)", (body.id, lab))
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    return {"ok": True, "id": body.id}


@router.patch("/admin/apps/{app_id}")
async def admin_patch_app(
    app_id: str,
    body: AppPatch,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """F2.4: edita campos del catálogo y/o reactiva (activo=1).

    Si el resultado deja la app con always_on=1 y activa, re-valida
    ALWAYS_ON_BUDGET_MB igual que el POST de alta.
    """
    if not is_admin(request, settings):
        raise HTTPException(403, "admin required")
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(403, "X-Requested-With required")
    conn = get_db()
    app = conn.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    if app is None:
        raise HTTPException(404, "app no encontrada")

    if body.imagen is not None:
        rc, _, _ = await instances.lxc("image", "show", body.imagen)
        if rc != 0:
            raise HTTPException(400, f"imagen {body.imagen} no encontrada en labs")
    if body.puerto_http is not None and not (3000 <= body.puerto_http <= 9999):
        raise HTTPException(422, "puerto_http debe estar entre 3000 y 9999")
    for campo in ("shared", "always_on", "activo"):
        v = getattr(body, campo)
        if v is not None and v not in (0, 1):
            raise HTTPException(422, f"{campo} debe ser 0 o 1")
    if body.labs is not None:
        for lab in body.labs:
            try:
                instances._check_name(lab)
            except ValueError as e:
                raise HTTPException(422, str(e))

    # Valores efectivos tras el patch (para revalidar el budget always_on)
    eff = {k: app[k] for k in app.keys()}
    for campo in ("nombre", "imagen", "shared", "always_on", "puerto_http",
                  "cpu", "memory_mb", "cmd", "descripcion", "activo"):
        v = getattr(body, campo)
        if v is not None:
            eff[campo] = v
    if eff["always_on"] and eff["activo"]:
        total = conn.execute(
            "SELECT COALESCE(SUM(memory_mb),0) FROM apps WHERE always_on=1 AND activo=1 AND id != ?",
            (app_id,),
        ).fetchone()[0]
        if total + eff["memory_mb"] > settings.always_on_budget_mb:
            raise HTTPException(
                409,
                f"ALWAYS_ON_BUDGET_MB excedido ({total + eff['memory_mb']} > {settings.always_on_budget_mb})",
            )

    conn.execute("BEGIN IMMEDIATE;")
    try:
        conn.execute(
            """UPDATE apps SET nombre=?, imagen=?, shared=?, always_on=?,
                    puerto_http=?, cpu=?, memory_mb=?, cmd=?, descripcion=?, activo=?
               WHERE id=?""",
            (eff["nombre"], eff["imagen"], eff["shared"], eff["always_on"],
             eff["puerto_http"], eff["cpu"], eff["memory_mb"], eff["cmd"],
             eff["descripcion"], eff["activo"], app_id),
        )
        if body.labs is not None:
            conn.execute("DELETE FROM app_lab WHERE app_id=?", (app_id,))
            for lab in body.labs:
                conn.execute(
                    "INSERT OR IGNORE INTO app_lab(app_id, lab) VALUES(?,?)",
                    (app_id, lab),
                )
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    return {"ok": True, "id": app_id}


@router.delete("/admin/apps/{app_id}")
async def admin_delete_app(
    app_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """F2.4: soft-delete del catálogo + destrucción ENCOLADA de las
    instancias vivas (job destroy_app; nunca bucle síncrono en el handler).
    Las filas pasan a 'destruyendo' en la misma tx (anti-TOCTOU con reaper).
    """
    if not is_admin(request, settings):
        raise HTTPException(403, "admin required")
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(403, "X-Requested-With required")
    conn = get_db()
    app = conn.execute("SELECT 1 FROM apps WHERE id=?", (app_id,)).fetchone()
    if app is None:
        raise HTTPException(404, "app no encontrada")
    conn.execute("BEGIN IMMEDIATE;")
    try:
        conn.execute("UPDATE apps SET activo=0 WHERE id=?", (app_id,))
        # Incluye 'destruyendo': re-ejecutar el DELETE re-encola las que un
        # job fallido dejó a medias (el job destroy_app es idempotente).
        vivas = conn.execute(
            """SELECT nombre_lxd FROM app_instances
                WHERE app_id=? AND estado IN ('creando','lista','detenida','error','destruyendo')""",
            (app_id,),
        ).fetchall()
        nombres = [r["nombre_lxd"] for r in vivas]
        for n in nombres:
            conn.execute(
                "UPDATE app_instances SET estado='destruyendo' WHERE nombre_lxd=?",
                (n,),
            )
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    # Encolar FUERA de la tx (enqueue hace su propio commit en la misma conexión).
    from .jobs import enqueue_destroy_app
    for n in nombres:
        enqueue_destroy_app(n)
    return {"ok": True, "id": app_id, "instancias_encoladas": len(nombres)}


@router.post("/admin/apps/{app_id}/start")
async def admin_start_app(
    app_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Lanza app shared global (admin)."""
    if not is_admin(request, settings):
        raise HTTPException(403, "admin required")
    app = get_db().execute("SELECT * FROM apps WHERE id=? AND activo=1", (app_id,)).fetchone()
    if app is None:
        raise HTTPException(404, "app no encontrada")
    if not app["shared"]:
        raise HTTPException(409, "app per-alumno no se lanza global")
    nombre_lxd = instances.app_instancia_nombre(app_id, None)
    from .jobs import enqueue_launch_app
    enqueue_launch_app(app_id, None, nombre_lxd)
    return JSONResponse({"estado": "creando", "nombre_lxd": nombre_lxd}, status_code=202)


@router.post("/admin/apps/{app_id}/stop")
async def admin_stop_app(
    app_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    if not is_admin(request, settings):
        raise HTTPException(403, "admin required")
    nombre_lxd = instances.app_instancia_nombre(app_id, None)
    await instances.stop(nombre_lxd)
    with tx() as c:
        c.execute(
            "UPDATE app_instances SET estado='detenida' WHERE nombre_lxd=?",
            (nombre_lxd,),
        )
    return {"ok": True}