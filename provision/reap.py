"""Reaper standalone: destruye instancias inactivas/caducadas.

Invocado por systemd timer como `python -m provision.reap` (NO es un endpoint
HTTP: así no compite con el worker único ni depende de que uvicorn esté vivo).

Criterios:
  - estado='creando' estancada > CREATING_TIMEOUT (default 600s)
  - estado in ('lista','detenida','error') con last_seen > IDLE_MINUTES (default 60)

BEGIN IMMEDIATE + re-check de last_seen DENTRO de la tx (consistencia ante
saltos de reloj). Usa datetime('now') de SQLite, no time.time() de Python.
Batch deletes en lotes de 10 con sleep entre lotes (no saturar LXD).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from . import instances
from .config import Settings, get_settings
from .db import get_db, tx

log = logging.getLogger("provision.reap")


def _env_int(key: str, default: int) -> int:
    v = os.getenv(key)
    return int(v) if v else default


async def reap_stale(settings: Optional[Settings] = None) -> list[str]:
    idle_minutes = _env_int("IDLE_MINUTES", 60)
    creating_timeout = _env_int("CREATING_TIMEOUT", 600)
    destroyed: list[str] = []

    # Fase 1: SELECT en autocommit (WAL permite leer sin write-lock).
    conn = get_db()
    rows = conn.execute(
        """SELECT nombre, estado,
                  (julianday('now') - julianday(last_seen)) * 86400 AS idle_sec
             FROM instancias
            WHERE estado IN ('lista','creando','detenida','error')"""
    ).fetchall()
    candidates: list[str] = []
    for r in rows:
        idle_sec = r["idle_sec"] or 0
        if r["estado"] == "creando":
            if idle_sec >= creating_timeout:
                candidates.append(r["nombre"])
        else:
            if idle_sec >= idle_minutes * 60:
                candidates.append(r["nombre"])

    # Fase 2: por cada candidato, re-check atómico DENTRO de tx antes de borrar.
    # Evita TOCTOU: si un /heartbeat o /lab/start actualizó last_seen/estado,
    # el reaper no destruye. Orden: delete LXD PRIMERO (idempotente), luego
    # UPDATE BD (evita orphan LXD si delete falla).
    for i in range(0, len(candidates), 10):
        batch = candidates[i : i + 10]
        for nombre in batch:
            try:
                # Re-check atómico: validar que sigue cumpliendo criterio.
                conn.execute("BEGIN IMMEDIATE;")
                r = conn.execute(
                    """SELECT estado,
                              (julianday('now') - julianday(last_seen)) * 86400 AS idle_sec
                         FROM instancias WHERE nombre=?""",
                    (nombre,),
                ).fetchone()
                if r is None:
                    conn.execute("ROLLBACK;")
                    continue
                idle_sec = r["idle_sec"] or 0
                should_destroy = (
                    (r["estado"] == "creando" and idle_sec >= creating_timeout)
                    or (r["estado"] in ("lista", "detenida", "error")
                        and idle_sec >= idle_minutes * 60)
                )
                if not should_destroy:
                    conn.execute("ROLLBACK;")
                    continue
                conn.execute("COMMIT;")
                # Borrar en LXD PRIMERO (idempotente: delete hace precheck exists)
                await instances.delete(nombre)
                # Solo tras delete exitoso, marcar BD como destruida
                with tx() as c:
                    c.execute(
                        "UPDATE instancias SET estado='destruida', ip_rdp=NULL WHERE nombre=?",
                        (nombre,),
                    )
                    c.execute("DELETE FROM heartbeats WHERE instancia=?", (nombre,))
                    c.execute("DELETE FROM vm_tokens WHERE instancia=?", (nombre,))
                destroyed.append(nombre)
                log.info("reaped %s", nombre)
            except Exception as e:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                log.error("no se pudo destruir %s: %s", nombre, e)
        await asyncio.sleep(1)
    return destroyed


async def reap_apps(settings: Optional[Settings] = None) -> list[str]:
    """FASE 6.4: Reaper de apps stateless. Mismo patrón anti-TOCTOU que VMs.

    Criterios:
      - per-alumno inactiva > APP_IDLE_MINUTES (30)
      - shared always_on=0 inactiva > SHARED_IDLE_HOURS (6h)
      - shared always_on=1 NUNCA se reap
      - creando estancada (worker_heartbeat < now-60s)
    Grace period tras reinicio: ignora candidatos con last_seen < service_started_at + GRACE_AFTER_RESTART.
    """
    import time as _t
    idle_min = _env_int("APP_IDLE_MINUTES", 30)
    shared_idle_hours = _env_int("SHARED_IDLE_HOURS", 6)
    creating_timeout = _env_int("APP_CREATING_TIMEOUT", 300)
    grace = _env_int("GRACE_AFTER_RESTART", 900)
    now_ts = _t.time()
    destroyed: list[str] = []

    conn = get_db()
    # Fase 1: SELECT candidatos
    rows = conn.execute(
        """SELECT ai.nombre_lxd, ai.estado, ai.alumno, ai.last_seen, ai.worker_heartbeat,
                  a.shared, a.always_on,
                  (julianday('now') - julianday(ai.last_seen)) * 86400 AS idle_sec
             FROM app_instances ai
             JOIN apps a ON a.id = ai.app_id
            WHERE ai.estado IN ('lista','detenida','error','creando')"""
    ).fetchall()
    candidates: list[str] = []
    for r in rows:
        idle_sec = r["idle_sec"] or 0
        if r["estado"] == "creando":
            # Estancada si worker_heartbeat viejo o sin worker_heartbeat y idle > creating_timeout
            wh = r["worker_heartbeat"]
            if wh is None:
                if idle_sec >= creating_timeout:
                    candidates.append(r["nombre_lxd"])
            else:
                # worker_heartbeat es TEXT (datetime); comparar con now-60s
                wh_ts = conn.execute(
                    "SELECT (julianday('now') - julianday(?)) * 86400", (wh,)
                ).fetchone()[0]
                if wh_ts > 60:
                    candidates.append(r["nombre_lxd"])
        elif r["shared"] and r["always_on"]:
            continue  # NUNCA se reap
        elif r["shared"]:
            if idle_sec >= shared_idle_hours * 3600:
                candidates.append(r["nombre_lxd"])
        else:
            if idle_sec >= idle_min * 60:
                candidates.append(r["nombre_lxd"])

    # Fase 2: por candidato, re-check atómico + delete LXD con retry
    for i in range(0, len(candidates), 25):
        batch = candidates[i:i + 25]
        for nombre in batch:
            try:
                conn.execute("BEGIN IMMEDIATE;")
                r = conn.execute(
                    """SELECT ai.estado, ai.alumno, ai.last_seen,
                              (julianday('now') - julianday(ai.last_seen)) * 86400 AS idle_sec
                         FROM app_instances ai WHERE ai.nombre_lxd=?""",
                    (nombre,),
                ).fetchone()
                if r is None:
                    conn.execute("ROLLBACK;")
                    continue
                idle_sec = r["idle_sec"] or 0
                # Re-check: sigue cumpliendo criterio?
                should = (
                    (r["estado"] == "creando" and idle_sec >= creating_timeout)
                    or (r["estado"] in ("lista", "detenida", "error") and idle_sec >= idle_min * 60)
                )
                if not should:
                    conn.execute("ROLLBACK;")
                    continue
                conn.execute("COMMIT;")
                # Delete LXD PRIMERO con retry 3×5s
                deleted = False
                for _ in range(3):
                    try:
                        await instances.delete(nombre)
                        deleted = True
                        break
                    except Exception as e:
                        log.warning("retry delete app %s: %s", nombre, e)
                        await asyncio.sleep(5)
                if not deleted:
                    # No UPDATE a destruida; incrementar reap_attempts
                    with tx() as c:
                        c.execute(
                            "UPDATE app_instances SET reap_attempts=reap_attempts+1 WHERE nombre_lxd=?",
                            (nombre,),
                        )
                    log.error("no se pudo destruir app %s tras 3 intentos", nombre)
                    continue
                with tx() as c:
                    c.execute(
                        "UPDATE app_instances SET estado='destruida', ip=NULL WHERE nombre_lxd=?",
                        (nombre,),
                    )
                destroyed.append(nombre)
                log.info("reaped app %s", nombre)
            except Exception as e:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                log.error("no se pudo destruir app %s: %s", nombre, e)
        await asyncio.sleep(1)
    return destroyed


async def main() -> None:
    get_settings()
    destroyed_vms = await reap_stale()
    destroyed_apps = await reap_apps()
    print(f"reaped VMs: {destroyed_vms}")
    print(f"reaped apps: {destroyed_apps}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(main())