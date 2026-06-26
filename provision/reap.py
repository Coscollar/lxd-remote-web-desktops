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


async def main() -> None:
    get_settings()
    destroyed = await reap_stale()
    print(f"reaped: {destroyed}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(main())