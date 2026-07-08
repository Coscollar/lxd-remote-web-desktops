"""F2 — Backend de la consola admin: labs, matrículas e instancias.

Router incluido en main.py. Doble puerta: Nginx antepone auth_request
/verify_admin y aquí cada endpoint re-valida con is_admin() (cookie
admin_token O X-Admin-Token para automatización).

Reglas:
  - Toda mutación exige `X-Requested-With: XMLHttpRequest` (anti-CSRF,
    patrón de apps.py).
  - Nombres validados con instances.NAME_RE / APP_NAME_RE ANTES de que
    cualquier valor llegue a `lxc`.
  - Lanzamientos SIEMPRE vía job queue (jobs.start_launch), nunca síncronos.
  - Destroys con re-check anti-TOCTOU en BEGIN IMMEDIATE (patrón reap.py).
  - La gestión de admins (tabla `admins`) queda deliberadamente FUERA de la
    UI/API: alta solo vía SQL documentada en docs/USO.md (privilegio máximo).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from . import instances
from .auth import is_admin
from .config import Settings, get_settings
from .db import get_db, tx
from .jobs import start_launch

log = logging.getLogger("provision.admin")

router = APIRouter()


# --- Modelos ----------------------------------------------------------------
class LabCreate(BaseModel):
    nombre: str
    imagen: str = "local:lab-vm-base"
    deadline: Optional[str] = None  # ISO-8601 (YYYY-MM-DD[THH:MM:SS])


class LabPatch(BaseModel):
    imagen: Optional[str] = None
    deadline: Optional[str] = None
    activo: Optional[int] = None


class EnrollmentCreate(BaseModel):
    alumno_id: str
    email: EmailStr
    lab: str


class EnrollmentPatch(BaseModel):
    email: EmailStr
    lab: str
    active: int


class LaunchBody(BaseModel):
    alumno: str
    lab: str


# --- Helpers ----------------------------------------------------------------
def _require_admin(request: Request, settings: Settings) -> None:
    if not is_admin(request, settings):
        raise HTTPException(403, "admin required")


def _require_xrw(request: Request) -> None:
    """Anti-CSRF en mutaciones (patrón apps.py)."""
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(403, "X-Requested-With required")


def _check_name_or_422(name: str) -> str:
    """Valida NAME_RE y convierte el ValueError en 422 (nunca llega a lxc)."""
    try:
        return instances._check_name(name)
    except ValueError as e:
        raise HTTPException(422, str(e))


def _check_deadline_or_422(deadline: Optional[str]) -> Optional[str]:
    if deadline is None or deadline == "":
        return None
    try:
        datetime.fromisoformat(deadline)
    except ValueError:
        raise HTTPException(422, f"deadline no es ISO-8601: {deadline!r}")
    return deadline


async def _check_image_or_400(imagen: str) -> str:
    """Valida que la imagen exista en el proyecto labs (patrón apps.py)."""
    if not isinstance(imagen, str) or not imagen.strip() or any(
        c.isspace() for c in imagen
    ):
        raise HTTPException(422, "imagen inválida")
    rc, _, _ = await instances.lxc("image", "show", imagen)
    if rc != 0:
        raise HTTPException(400, f"imagen {imagen} no encontrada en labs")
    return imagen


# --- Labs -------------------------------------------------------------------
@router.get("/admin/labs")
async def admin_list_labs(
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Labs con nº de matriculados activos e instancias vivas."""
    _require_admin(request, settings)
    rows = get_db().execute(
        """SELECT l.nombre, l.imagen, l.deadline, l.activo,
                  (SELECT COUNT(*) FROM enrollments e
                    WHERE e.lab = l.nombre AND e.active = 1) AS matriculados,
                  (SELECT COUNT(*) FROM instancias i
                    WHERE i.lab = l.nombre
                      AND i.estado IN ('creando','lista','detenida')) AS instancias_vivas
             FROM labs l ORDER BY l.nombre"""
    ).fetchall()
    return {"labs": [dict(r) for r in rows]}


@router.post("/admin/labs")
async def admin_create_lab(
    body: LabCreate,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    _require_admin(request, settings)
    _require_xrw(request)
    nombre = _check_name_or_422(body.nombre)
    deadline = _check_deadline_or_422(body.deadline)
    await _check_image_or_400(body.imagen)
    with tx() as c:
        c.execute(
            "INSERT OR IGNORE INTO labs(nombre, imagen, deadline, activo) VALUES(?,?,?,1)",
            (nombre, body.imagen, deadline),
        )
    return {"ok": True, "nombre": nombre}


@router.patch("/admin/labs/{nombre}")
async def admin_patch_lab(
    nombre: str,
    body: LabPatch,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Edita imagen/deadline/activo. Desactivar = soft (activo=0)."""
    _require_admin(request, settings)
    _require_xrw(request)
    nombre = _check_name_or_422(nombre)
    row = get_db().execute("SELECT 1 FROM labs WHERE nombre=?", (nombre,)).fetchone()
    if row is None:
        raise HTTPException(404, "lab no encontrado")
    sets: list[str] = []
    params: list = []
    if body.imagen is not None:
        await _check_image_or_400(body.imagen)
        sets.append("imagen=?")
        params.append(body.imagen)
    if body.deadline is not None:
        sets.append("deadline=?")
        params.append(_check_deadline_or_422(body.deadline))
    if body.activo is not None:
        if body.activo not in (0, 1):
            raise HTTPException(422, "activo debe ser 0 o 1")
        sets.append("activo=?")
        params.append(body.activo)
    if not sets:
        raise HTTPException(422, "nada que actualizar")
    params.append(nombre)
    with tx() as c:
        c.execute(f"UPDATE labs SET {', '.join(sets)} WHERE nombre=?", params)
    return {"ok": True, "nombre": nombre}


# --- Matrículas ---------------------------------------------------------------
@router.get("/admin/enrollments")
async def admin_list_enrollments(
    request: Request,
    settings: Settings = Depends(get_settings),
    lab: str = "",
    cursor: int = 0,
    limit: int = 50,
):
    """Matrículas con paginación keyset por rowid (+ filtro por lab)."""
    _require_admin(request, settings)
    limit = max(1, min(limit, 200))
    if lab:
        lab = _check_name_or_422(lab)
    params: list = [cursor]
    where = "e.rowid > ?"
    if lab:
        where += " AND e.lab = ?"
        params.append(lab)
    params.append(limit + 1)
    rows = get_db().execute(
        f"""SELECT e.rowid AS rid, e.alumno_id, e.email, e.lab, e.course,
                   e.active, e.created_at,
                   COALESCE(i.estado, 'inexistente') AS estado_instancia
              FROM enrollments e
              LEFT JOIN instancias i
                     ON i.alumno = e.alumno_id AND i.lab = e.lab
                    AND i.estado != 'destruida'
             WHERE {where}
             ORDER BY e.rowid LIMIT ?""",
        params,
    ).fetchall()
    items = [dict(r) for r in rows[:limit]]
    has_more = len(rows) > limit
    next_cursor = items[-1]["rid"] if (items and has_more) else None
    return {"enrollments": items, "has_more": has_more, "next_cursor": next_cursor}


@router.post("/admin/enrollments")
async def admin_create_enrollment(
    body: EnrollmentCreate,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Alta de matrícula. Idempotente: si (email, lab) ya existe, no duplica.

    UNIQUE(email, lab, course) no protege con course NULL (NULLs distintos
    en SQLite) → dedupe explícito dentro de BEGIN IMMEDIATE.
    """
    _require_admin(request, settings)
    _require_xrw(request)
    alumno_id = _check_name_or_422(body.alumno_id)
    lab = _check_name_or_422(body.lab)
    email = body.email.lower()
    # instancia_nombre valida también el nombre compuesto (<=30 chars)
    try:
        instances.instancia_nombre(alumno_id, lab)
    except ValueError as e:
        raise HTTPException(422, str(e))

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        lab_row = conn.execute(
            "SELECT 1 FROM labs WHERE nombre=? AND activo=1", (lab,)
        ).fetchone()
        if lab_row is None:
            conn.execute("ROLLBACK;")
            raise HTTPException(400, f"lab {lab} no existe o no está activo")
        # Coherencia: un email debe mapear siempre al mismo alumno_id
        # (auth y dashboard resuelven alumno_id por email).
        other = conn.execute(
            "SELECT DISTINCT alumno_id FROM enrollments WHERE email=? AND alumno_id != ?",
            (email, alumno_id),
        ).fetchone()
        if other is not None:
            conn.execute("ROLLBACK;")
            raise HTTPException(
                409, f"el email ya está asociado al alumno_id {other['alumno_id']!r}"
            )
        existing = conn.execute(
            "SELECT rowid, active FROM enrollments WHERE email=? AND lab=?",
            (email, lab),
        ).fetchone()
        if existing is None:
            conn.execute(
                """INSERT INTO enrollments(alumno_id, email, lab, active, created_at)
                   VALUES(?,?,?,1,?)""",
                (alumno_id, email, lab, int(time.time())),
            )
            created = True
        else:
            created = False
        conn.execute("COMMIT;")
    except HTTPException:
        raise
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    return {"ok": True, "created": created, "alumno_id": alumno_id, "lab": lab}


@router.patch("/admin/enrollments")
async def admin_patch_enrollment(
    body: EnrollmentPatch,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Baja/realta de matrícula (active=0|1). Soft: no borra filas."""
    _require_admin(request, settings)
    _require_xrw(request)
    lab = _check_name_or_422(body.lab)
    if body.active not in (0, 1):
        raise HTTPException(422, "active debe ser 0 o 1")
    email = body.email.lower()
    with tx() as c:
        cur = c.execute(
            "UPDATE enrollments SET active=? WHERE email=? AND lab=?",
            (body.active, email, lab),
        )
        changed = cur.rowcount
    if changed == 0:
        raise HTTPException(404, "matrícula no encontrada")
    return {"ok": True, "email": email, "lab": lab, "active": body.active}


# --- Instancias ---------------------------------------------------------------
async def destroy_vm(nombre: str) -> None:
    """Destruye una VM de alumno. Anti-TOCTOU: re-check en BEGIN IMMEDIATE;
    instances.delete es idempotente (tolerante a not-found, convive con el
    reaper sin doble-delete dañino)."""
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        row = conn.execute(
            "SELECT estado FROM instancias WHERE nombre=?", (nombre,)
        ).fetchone()
        if row is not None and row["estado"] == "destruida":
            conn.execute("COMMIT;")
            return
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    # LXD PRIMERO (idempotente); solo tras éxito, marcar BD (patrón reap.py).
    await instances.delete(nombre)
    with tx() as c:
        # Guard de estado: si otro camino la puso en 'creando' (relanzada)
        # durante el lxc delete, no pisar ni borrar sus tokens.
        cur = c.execute(
            "UPDATE instancias SET estado='destruida', ip_rdp=NULL "
            "WHERE nombre=? AND estado != 'creando'",
            (nombre,),
        )
        if cur.rowcount > 0:
            c.execute("DELETE FROM heartbeats WHERE instancia=?", (nombre,))
            c.execute("DELETE FROM vm_tokens WHERE instancia=?", (nombre,))
        else:
            log.warning(
                "destroy_vm %s: estado cambió durante el delete; no se marca destruida",
                nombre,
            )


async def destroy_app_instance(nombre: str) -> None:
    """Destruye una instancia de app. Marca 'destruyendo' en BEGIN IMMEDIATE
    (anti-TOCTOU con reaper/relaunch) antes de tocar LXD."""
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        row = conn.execute(
            "SELECT estado FROM app_instances WHERE nombre_lxd=?", (nombre,)
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK;")
            raise HTTPException(404, "instancia de app no encontrada")
        if row["estado"] == "destruida":
            conn.execute("COMMIT;")
            return
        conn.execute(
            "UPDATE app_instances SET estado='destruyendo' WHERE nombre_lxd=?",
            (nombre,),
        )
        conn.execute("COMMIT;")
    except HTTPException:
        raise
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    try:
        await instances.delete(nombre)  # idempotente
    except Exception:
        with tx() as c:
            c.execute(
                "UPDATE app_instances SET estado='error' WHERE nombre_lxd=? AND estado='destruyendo'",
                (nombre,),
            )
        raise
    with tx() as c:
        # Guard de estado: solo transiciona destruyendo→destruida (espejo
        # del error-path); no pisa una instancia relanzada entre medias.
        cur = c.execute(
            "UPDATE app_instances SET estado='destruida', ip=NULL "
            "WHERE nombre_lxd=? AND estado='destruyendo'",
            (nombre,),
        )
        if cur.rowcount > 0:
            c.execute("DELETE FROM app_tokens WHERE instancia=?", (nombre,))
        else:
            log.warning(
                "destroy_app_instance %s: estado cambió durante el delete; no se marca destruida",
                nombre,
            )


@router.post("/admin/instances/{nombre}/destroy")
async def admin_destroy_instance(
    nombre: str,
    tipo: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Destroy tipado (el endpoint que consume la consola admin).

    tipo=vm  → VM de alumno (instancias + heartbeats + vm_tokens).
    tipo=app → contenedor de app (app_instances + app_tokens).
    """
    _require_admin(request, settings)
    _require_xrw(request)
    if tipo == "vm":
        nombre = _check_name_or_422(nombre)
        await destroy_vm(nombre)
    elif tipo == "app":
        if not instances.APP_NAME_RE.match(nombre):
            raise HTTPException(422, f"nombre de app inválido: {nombre!r}")
        await destroy_app_instance(nombre)
    else:
        raise HTTPException(422, "tipo debe ser 'vm' o 'app'")
    return {"ok": True, "instancia": nombre, "tipo": tipo}


@router.post("/admin/instances/launch")
async def admin_launch_instance(
    body: LaunchBody,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Lanzamiento forzado por admin. MISMO camino que /lab/start
    (jobs.start_launch: upsert atómico + job queue). Nunca síncrono."""
    _require_admin(request, settings)
    _require_xrw(request)
    alumno = _check_name_or_422(body.alumno)
    lab = _check_name_or_422(body.lab)
    enr = get_db().execute(
        "SELECT 1 FROM enrollments WHERE alumno_id=? AND lab=? AND active=1",
        (alumno, lab),
    ).fetchone()
    if enr is None:
        raise HTTPException(400, f"{alumno} no tiene matrícula activa en {lab}")
    try:
        instancia, encolado, estado, ip = start_launch(alumno, lab)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not encolado and estado == "lista":
        return JSONResponse(
            {"estado": "lista", "instancia": instancia, "ip_rdp": ip}, status_code=200
        )
    return JSONResponse(
        {"estado": "creando" if encolado else estado, "instancia": instancia},
        status_code=202,
    )
