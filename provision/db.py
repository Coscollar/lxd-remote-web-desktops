"""SQLite schema + PRAGMAs y pool de conexiones mínimo.

Usamos un pool de conexiones por hilo/worker (threading.local) porque
uvicorn con sync endpoints corre en hilos; los endpoints async usan
run_in_threadpool para acceder a SQLite (no hay driver async estable
que valga la pena aquí).
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from .config import get_settings

_PRAGMAS = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA busy_timeout=5000;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA foreign_keys=ON;",
)

_SCHEMA = """
-- Magic-link tokens (almacenados como sha256, NUNCA en claro)
CREATE TABLE IF NOT EXISTS auth_tokens(
  token_hash   TEXT PRIMARY KEY,           -- sha256(token) hex
  email        TEXT NOT NULL,
  lab          TEXT NOT NULL,
  created_at   INTEGER NOT NULL,
  expires_at   INTEGER NOT NULL,           -- now + 900
  used_at      INTEGER DEFAULT NULL,
  used_from_ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_email   ON auth_tokens(email);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_expires ON auth_tokens(expires_at);

-- Matrícula: el lab se DEDUCE, no lo elige el alumno
CREATE TABLE IF NOT EXISTS enrollments(
  alumno_id  TEXT NOT NULL,               -- id opaco (sub del JWT)
  email      TEXT NOT NULL,
  lab        TEXT NOT NULL,
  course     TEXT,
  active     INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  UNIQUE(email, lab, course)
);
CREATE INDEX IF NOT EXISTS idx_enrollments_email_active ON enrollments(email, active);

-- Revocación de sesiones JWT
CREATE TABLE IF NOT EXISTS jwt_jti(
  jti        TEXT PRIMARY KEY,
  revoked_at INTEGER NOT NULL
);

-- Catálogo de labs
CREATE TABLE IF NOT EXISTS labs(
  nombre   TEXT PRIMARY KEY,
  imagen   TEXT NOT NULL DEFAULT 'local:lab-vm-base',
  deadline TEXT,
  activo   INTEGER NOT NULL DEFAULT 1
);

-- Tokens de servicio de VM (FASE 1.7 / FASE 3)
CREATE TABLE IF NOT EXISTS vm_tokens(
  instancia    TEXT PRIMARY KEY,           -- "<alumno>-<lab>"
  token_hash   TEXT NOT NULL,              -- sha256(service_token) hex
  vm_ip        TEXT NOT NULL,              -- IP registrada de la VM
  issued_at    INTEGER NOT NULL,
  expires_at   INTEGER NOT NULL,
  rotated_from TEXT
);
CREATE INDEX IF NOT EXISTS idx_vm_tokens_hash ON vm_tokens(token_hash);

-- FASE 3: instancias de laboratorio (una por alumno/lab)
CREATE TABLE IF NOT EXISTS instancias(
  nombre      TEXT PRIMARY KEY,           -- '<alumno>-<lab>'
  alumno      TEXT NOT NULL,
  lab         TEXT NOT NULL REFERENCES labs(nombre),
  estado      TEXT NOT NULL CHECK (estado IN ('creando','lista','detenida','error','destruida')),
  ip_rdp      TEXT,
  creado      TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen   TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (alumno, lab)
);
CREATE INDEX IF NOT EXISTS idx_inst_last_seen ON instancias(last_seen);
CREATE INDEX IF NOT EXISTS idx_inst_estado   ON instancias(estado);

-- FASE 3: heartbeats de VM (separado de instancias.last_seen para no competir)
CREATE TABLE IF NOT EXISTS heartbeats(
  instancia   TEXT PRIMARY KEY REFERENCES instancias(nombre),
  last_seen   TEXT NOT NULL
);

-- FASE 3: inventario de snapshots (source of truth = LXD; esto es caché)
CREATE TABLE IF NOT EXISTS snapshots(
  instancia  TEXT NOT NULL REFERENCES instancias(nombre),
  tag        TEXT NOT NULL,
  creado     TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (instancia, tag)
);

-- FASE 3: job queue persistente (sobrevive a reinicios)
CREATE TABLE IF NOT EXISTS jobs(
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo        TEXT NOT NULL,              -- 'launch' (otros se sirven síncrono)
  instancia   TEXT,
  payload     TEXT,
  estado      TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|error
  creado      TEXT NOT NULL DEFAULT (datetime('now')),
  started_at  TEXT,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_estado ON jobs(estado);
"""

_local = threading.local()


def _new_conn() -> sqlite3.Connection:
    cfg = get_settings()
    conn = sqlite3.connect(cfg.db_path, isolation_level=None, timeout=5.0)
    conn.row_factory = sqlite3.Row
    for p in _PRAGMAS:
        conn.execute(p)
    return conn


def get_db() -> sqlite3.Connection:
    """Devuelve una conexión reutilizada por hilo (pool implícito)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _new_conn()
        _local.conn = conn
    return conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """Transacción explícita BEGIN/COMMIT/ROLLBACK (autocommit desactivado)."""
    conn = get_db()
    conn.execute("BEGIN;")
    try:
        yield conn
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise


def init_db() -> None:
    """Crea el schema si no existe. Idempotente."""
    conn = _new_conn()
    try:
        conn.executescript(_SCHEMA)
    finally:
        conn.close()