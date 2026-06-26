"""Job queue persistente + worker dedicado.

Sobrevive a reinicios: el estado vive en SQLite (tabla `jobs`), no en
BackgroundTasks (que se pierden al parar uvicorn). El worker reclama jobs
`pending` con BEGIN IMMEDIATE (mutex), los ejecuta bajo un semáforo async
(cota RAM) y los marca done/error.

Aquí solo procesamos jobs `launch` (lento: ~minutos). save/reset/destroy son
rápidos y se sirven síncrono desde los endpoints; el reaper va standalone.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from typing import Optional

from . import instances
from .auth import issue_vm_token
from .config import Settings, get_settings
from .db import get_db, tx

log = logging.getLogger("provision.jobs")


def _ram_gb() -> int:
    """Lee MemTotal de /proc/meminfo. Default 8 si no se puede leer."""
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb // (1024 * 1024)
    except OSError:
        pass
    return 8


def _sem_limit() -> int:
    """min(4, ram//4 - 2), mínimo 1."""
    return max(1, min(4, _ram_gb() // 4 - 2))


def enqueue_launch(alumno: str, lab: str, **extra) -> int:
    """Encola un job `launch`. Devuelve el id del job."""
    payload = json.dumps({"alumno": alumno, "lab": lab, **extra})
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO jobs(tipo, payload, estado) VALUES ('launch', ?, 'pending')",
        (payload,),
    )
    conn.commit()
    return cur.lastrowid


class JobWorker:
    """Worker único (uvicorn --workers 1). Reclama y ejecuta jobs pendientes."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._sem = asyncio.Semaphore(_sem_limit())
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        # Reclamar jobs running huérfanos (worker murió a mitad): marcar error
        # para que /lab/start pueda relanzar (estado entra en WHERE de ON CONFLICT).
        self._reclaim_stale_running()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task

    def _reclaim_stale_running(self) -> None:
        """Marca `error` los jobs `running` al arrancar (el worker previo murió)."""
        conn = get_db()
        conn.execute(
            "UPDATE jobs SET estado='error', finished_at=datetime('now') "
            "WHERE estado='running'"
        )
        conn.commit()
        n = conn.execute("SELECT changes()").fetchone()[0]
        if n:
            log.warning("reclamados %d jobs running huérfanos -> error", n)

    async def _loop(self) -> None:
        """Despacha jobs con concurrencia real (create_task + semáforo)."""
        tasks: set[asyncio.Task] = set()
        while not self._stop.is_set():
            # limpiar tasks terminadas
            done = {t for t in tasks if t.done()}
            tasks -= done
            for t in done:
                # propagar excepciones no capturadas (log)
                exc = t.exception()
                if exc:
                    log.error("job task crashed: %s", exc)
            job = self._claim()
            if job is None:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
                continue
            t = asyncio.create_task(self._run_guarded(job))
            tasks.add(t)

    async def _run_guarded(self, job: sqlite3.Row) -> None:
        """Envuelve _run con el semáforo y captura excepciones."""
        async with self._sem:
            try:
                await self._run(job)
            except Exception as e:
                log.error("job %s falló: %s", job["id"], e)
                self._mark_error(job["id"], str(e))

    def _claim(self) -> Optional[sqlite3.Row]:
        """Reclama atómicamente el job `pending` más viejo (BEGIN IMMEDIATE)."""
        conn = get_db()
        conn.execute("BEGIN IMMEDIATE;")
        try:
            row = conn.execute(
                """SELECT id, tipo, instancia, payload FROM jobs
                    WHERE estado='pending'
                    ORDER BY id ASC LIMIT 1"""
            ).fetchone()
            if row is None:
                conn.execute("COMMIT;")
                return None
            conn.execute(
                "UPDATE jobs SET estado='running', started_at=datetime('now') WHERE id=?",
                (row["id"],),
            )
            conn.execute("COMMIT;")
            return row
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    async def _run(self, job: sqlite3.Row) -> None:
        if job["tipo"] == "launch":
            await self._run_launch(job)
        else:
            self._mark_error(job["id"], f"tipo no soportado por el worker: {job['tipo']}")

    async def _run_launch(self, job: sqlite3.Row) -> None:
        jid = job["id"]
        payload = json.loads(job["payload"] or "{}")
        alumno = payload["alumno"]
        lab = payload["lab"]
        instancia = instances.instancia_nombre(alumno, lab)
        try:
            # Token de VM provisional (IP 0.0.0.0); se rota con IP real tras healthcheck.
            token = issue_vm_token(
                instancia=instancia, vm_ip="0.0.0.0", settings=self.settings
            )
            user_data = instances.render_cloud_init(
                alumno, lab, token, settings=self.settings,
                sudo_mode=payload.get("sudo_mode", "ALL=(ALL) NOPASSWD:ALL"),
                ssh_keys=payload.get("ssh_keys"),
                lab_packages=payload.get("lab_packages"),
                timezone=payload.get("timezone", "Europe/Madrid"),
            )
            await instances.launch(instancia, user_data)
            await instances.wait_cloud_init(instancia, timeout=300)
            await instances.snapshot_create(instancia, "base")  # precheck atómico
            await instances.healthcheck_rdp(instancia)
            ip = await instances.get_ip(instancia)
            # Rotación del token con IP real (la IP registrada se valida en /save etc.)
            issue_vm_token(instancia=instancia, vm_ip=ip, settings=self.settings)
            with tx() as conn:
                conn.execute(
                    """UPDATE instancias
                          SET estado='lista', ip_rdp=?, last_seen=datetime('now')
                        WHERE nombre=?""",
                    (ip, instancia),
                )
            self._mark_done(jid)
            log.info("launch OK %s ip=%s", instancia, ip)
        except Exception as e:
            log.exception("launch falló %s", instancia)
            with tx() as conn:
                conn.execute(
                    "UPDATE instancias SET estado='error' WHERE nombre=?",
                    (instancia,),
                )
            self._mark_error(jid, str(e))

    def _mark_done(self, jid: int) -> None:
        conn = get_db()
        conn.execute(
            "UPDATE jobs SET estado='done', finished_at=datetime('now') WHERE id=?",
            (jid,),
        )
        conn.commit()

    def _mark_error(self, jid: int, msg: str) -> None:
        conn = get_db()
        conn.execute(
            "UPDATE jobs SET estado='error', finished_at=datetime('now'), "
            "payload=COALESCE(payload,'') || ? WHERE id=?",
            (f"\n[error] {msg}", jid),
        )
        conn.commit()