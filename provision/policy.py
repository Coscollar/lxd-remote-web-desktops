"""Policy engine: snapshots nativos LXD + pool guard reactivo + reset/restore.

Sustituye al placeholder `_snapshot_save` de main.py y centraliza reset/restore
para reutilización desde endpoints y jobs.

Esquema de snapshots (fijado en PLAN FASE 5):
  - <instancia>/base  : inviolable, creado tras cloud-init done + healthcheck.
  - <instancia>/k1..k5: retención FIFO, rotación basada en LXD (no contador).

Pool guard reactivo sobre persistent-pool (40GB):
  - >90% -> 503 (no se crea snapshot).
  - >75% -> purgar oldest antes de crear (despresurizar).
  - >60% -> reducir retención a k1..k3.

Source of truth = LXD (`instances.list_snapshots`), no contador interno:
evita desincronización BD<->LXD si el servicio reinicia o un snapshot se borra
a mano. Una instancia por (alumno, lab): reset = restore base, nunca recreate.
"""
from __future__ import annotations

import asyncio
import json
import subprocess

from fastapi import HTTPException

from . import instances

POOL = "persistent-pool"
KEEP_DEFAULT = 5
KEEP_LOW = 3            # retención reducida si pool > 60%
THRESHOLD_LOW = 60.0    # >60%  -> KEEP=3
THRESHOLD_PURGE = 75.0  # >75%  -> purgar oldest antes de crear
THRESHOLD_FULL = 90.0   # >90%  -> 503

# Locks por instancia para serializar snapshot_save (evita TOCTOU en rotación FIFO)
_inst_locks: dict[str, asyncio.Lock] = {}


def _lock_for(instancia: str) -> asyncio.Lock:
    lock = _inst_locks.get(instancia)
    if lock is None:
        lock = asyncio.Lock()
        _inst_locks[instancia] = lock
    return lock


# --- pool guard -------------------------------------------------------------
def _pool_usage_pct_sync() -> float:
    """% usado de persistent-pool (síncrono, para run_in_threadpool)."""
    proc = subprocess.run(
        ["lxc", "storage", "info", POOL, "--format", "json"],
        capture_output=True,
        timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"lxc storage info {POOL} falló (rc={proc.returncode}): "
            f"{proc.stderr.decode(errors='replace').strip()}"
        )
    data = json.loads(proc.stdout)
    space = data.get("space", {}) or {}
    total = float(space.get("total", 0) or 0)
    used = float(space.get("used", 0) or 0)
    if total <= 0:
        return 0.0
    return used / total * 100.0


async def pool_usage_pct() -> float:
    """% usado de persistent-pool (async, no bloquea el event loop)."""
    return await asyncio.to_thread(_pool_usage_pct_sync)


def pool_usage_ok() -> bool:
    """True si el pool admite más snapshots (< 90%).

    Fail-closed: si no podemos leer el pool, devolvemos False para no crear
    snapshots sobre un pool posiblemente lleno. Síncrono (uso desde jobs.py
    pre-launch, que ya corre en threadpool del worker).
    """
    try:
        return _pool_usage_pct_sync() < THRESHOLD_FULL
    except RuntimeError:
        return False


# --- helpers ----------------------------------------------------------------
def _k_snaps(snaps: list[str]) -> list[str]:
    """Filtra k1..k5 (excluye base) y los ordena ascendentemente por número."""
    return sorted(
        (s for s in snaps
         if s != "base" and instances.TAG_RE.match(s) is not None),
        key=lambda s: int(s[1:]),
    )


def _next_free_k(k_snaps: list[str], keep: int) -> str:
    """Primer kN libre en 1..keep según los existentes en LXD."""
    existing = {int(s[1:]) for s in k_snaps}
    for n in range(1, keep + 1):
        if n not in existing:
            return f"k{n}"
    raise RuntimeError("no hay kN libre tras rotación (invariante rota)")


# --- API --------------------------------------------------------------------
async def snapshot_save(instancia: str) -> str:
    """Crea snapshot k1..k5 con rotación FIFO. Devuelve el tag creado.

    Pool guard reactivo:
      >90% -> HTTPException 503
      >75% -> purgar oldest antes de crear
      >60% -> retención reducida a k1..k3

    Serializa por instancia (lock) para evitar TOCTOU en rotación FIFO.
    """
    instances._check_name(instancia)
    async with _lock_for(instancia):
        usage = await pool_usage_pct()
        if usage > THRESHOLD_FULL:
            raise HTTPException(
                503, f"{POOL} > {THRESHOLD_FULL:.0f}% (uso {usage:.1f}%)"
            )

        keep = KEEP_LOW if usage > THRESHOLD_LOW else KEEP_DEFAULT

        snaps = await instances.list_snapshots(instancia)
        k_snaps = _k_snaps(snaps)

        # Rotación FIFO que converge: purgar suficientes para que tras crear
        # el nuevo el total sea <= keep. max(1, ...) garantiza hueco.
        to_purge = max(1, len(k_snaps) - keep + 1) if len(k_snaps) >= keep else 0
        # Pool > 75%: purga extra del oldest antes de crear (despresurizar).
        if usage > THRESHOLD_PURGE and k_snaps:
            to_purge = max(to_purge, 1)
        for _ in range(to_purge):
            if k_snaps:
                await instances.snapshot_delete(instancia, k_snaps[0])
                k_snaps = k_snaps[1:]

        tag = _next_free_k(k_snaps, keep)
        await instances.snapshot_create(instancia, tag)
        return tag


async def reset_to_base(instancia: str) -> None:
    """Restaura `base` sin recrear la instancia. Precheck base existe (409).

    Secuencia: stop(force) -> restore base -> start_if_stopped -> healthcheck RDP.
    No destruye ni relanza: una instancia por (alumno, lab).
    """
    instances._check_name(instancia)
    snaps = await instances.list_snapshots(instancia)
    if "base" not in snaps:
        raise HTTPException(409, "base snapshot no existe")
    await instances.stop(instancia, force=True)
    await instances.snapshot_restore(instancia, "base")
    await instances.start_if_stopped(instancia)
    await instances.healthcheck_rdp(instancia)


async def restore_tag(instancia: str, tag: str) -> None:
    """Restaura un snapshot arbitrario. TAG_RE + precheck existencia (404).

    `tag` se valida contra instances.TAG_RE (^(base|k[1-5])$) antes de tocar
    LXD, de modo que un valor malicioso nunca alcanza el shell.
    """
    instances._check_name(instancia)
    instances._check_tag(tag)
    snaps = await instances.list_snapshots(instancia)
    if tag not in snaps:
        raise HTTPException(404, f"snapshot {tag} no existe")
    await instances.stop(instancia, force=True)
    await instances.snapshot_restore(instancia, tag)
    await instances.start_if_stopped(instancia)
    await instances.healthcheck_rdp(instancia)