"""SQLite schema + PRAGMAs y pool de conexiones mínimo.

Usamos un pool de conexiones por hilo/worker (threading.local) porque
uvicorn con sync endpoints corre en hilos; los endpoints async usan
run_in_threadpool para acceder a SQLite (no hay driver async estable
que valga la pena aquí).
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from .config import get_settings

log = logging.getLogger("provision.db")

_PRAGMAS = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA busy_timeout=5000;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA foreign_keys=ON;",
)

_SCHEMA = """
-- FASE 6: versionado de schema para migraciones idempotentes
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version(version) VALUES (0);

-- Magic-link tokens (almacenados como sha256, NUNCA en claro)
-- FASE 6.1: lab es NULLABLE (multi-lab: lab=null significa dashboard)
CREATE TABLE IF NOT EXISTS auth_tokens(
  token_hash   TEXT PRIMARY KEY,           -- sha256(token) hex
  email        TEXT NOT NULL,
  lab          TEXT,                        -- NULL = multi-lab (dashboard)
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
CREATE INDEX IF NOT EXISTS idx_enrollments_alumno_active ON enrollments(alumno_id, active);

-- Revocación de sesiones JWT (alumno)
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
  tipo        TEXT NOT NULL,              -- 'launch' | 'launch_app'
  instancia   TEXT,
  payload     TEXT,
  estado      TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|error
  creado      TEXT NOT NULL DEFAULT (datetime('now')),
  started_at  TEXT,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_estado ON jobs(estado);

-- FASE 6.1: Auth admin (magic link, separado del alumno)
CREATE TABLE IF NOT EXISTS admins(
  email         TEXT PRIMARY KEY,
  role          TEXT NOT NULL DEFAULT 'admin',
  active        INTEGER NOT NULL DEFAULT 1,
  totp_secret   TEXT,                     -- cifrado en reposo (Fernet)
  last_login_at INTEGER,
  created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_admins_email_active ON admins(email, active);

CREATE TABLE IF NOT EXISTS admin_auth_tokens(
  token_hash   TEXT PRIMARY KEY,
  email        TEXT NOT NULL,
  created_at   INTEGER NOT NULL,
  expires_at   INTEGER NOT NULL,
  used_at      INTEGER DEFAULT NULL,
  used_from_ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_admin_auth_tokens_email ON admin_auth_tokens(email);

CREATE TABLE IF NOT EXISTS admin_jwt_jti(
  jti        TEXT PRIMARY KEY,
  revoked_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_totp_pending(
  token_hash TEXT PRIMARY KEY,
  email      TEXT NOT NULL,
  expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_logins(
  email TEXT NOT NULL, ip TEXT, ua TEXT, at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS email_outbox(
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  to_email   TEXT NOT NULL,
  subject    TEXT NOT NULL,
  body       TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  sent_at    INTEGER,
  attempts   INTEGER NOT NULL DEFAULT 0
);

-- FASE 6.4: Catálogo de apps stateless
CREATE TABLE IF NOT EXISTS apps(
  id         TEXT PRIMARY KEY,            -- slug: 'jupyter'
  nombre     TEXT NOT NULL UNIQUE,        -- display
  imagen     TEXT NOT NULL,               -- 'local:app-jupyter'
  shared     INTEGER NOT NULL DEFAULT 1,  -- 1=shared, 0=per-alumno
  always_on  INTEGER NOT NULL DEFAULT 0,  -- 1=siempre viva (solo si shared=1)
  puerto_http INTEGER NOT NULL CHECK (puerto_http BETWEEN 3000 AND 9999),
  cpu        INTEGER NOT NULL DEFAULT 2,
  memory_mb  INTEGER NOT NULL DEFAULT 2048,
  cmd        TEXT,
  descripcion TEXT,
  activo     INTEGER NOT NULL DEFAULT 1,
  creado     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS app_lab(
  app_id TEXT NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
  lab    TEXT NOT NULL REFERENCES labs(nombre) ON DELETE CASCADE,
  PRIMARY KEY (app_id, lab)
);
CREATE INDEX IF NOT EXISTS idx_app_lab_lab ON app_lab(lab);

CREATE TABLE IF NOT EXISTS app_instances(
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  app_id          TEXT NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
  alumno          TEXT,                    -- NULL si shared
  nombre_lxd      TEXT NOT NULL UNIQUE,
  ip             TEXT,
  puerto_http     INTEGER NOT NULL,
  estado          TEXT NOT NULL CHECK (estado IN ('creando','lista','detenida','error','destruida','destruyendo')),
  last_seen       TEXT NOT NULL DEFAULT (datetime('now')),
  worker_heartbeat TEXT,                   -- actualizado por worker cada 10s
  reap_attempts   INTEGER NOT NULL DEFAULT 0,
  creado          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_app_inst_last_seen ON app_instances(last_seen);
CREATE INDEX IF NOT EXISTS idx_app_inst_estado    ON app_instances(estado);
CREATE INDEX IF NOT EXISTS idx_app_inst_alumno    ON app_instances(alumno);
-- Partial unique: una sola instancia shared por app (alumno IS NULL)
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_shared
  ON app_instances(app_id) WHERE alumno IS NULL;
-- Partial unique: una instancia por (app, alumno) per-alumno
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_peralumno
  ON app_instances(app_id, alumno) WHERE alumno IS NOT NULL;

-- FASE 6.4: Service token de app (análogo a vm_tokens)
CREATE TABLE IF NOT EXISTS app_tokens(
  instancia   TEXT PRIMARY KEY,
  token_hash  TEXT NOT NULL,
  app_ip      TEXT NOT NULL,
  issued_at   INTEGER NOT NULL,
  expires_at  INTEGER NOT NULL
);
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
    """Crea el schema si no existe + migraciones idempotentes. Idempotente.

    FASE 6.1: migración auth_tokens.lab nullable (lab era NOT NULL en FASE 1).
    Usa schema_version + detección de columna para no duplicar.
    Requiere SQLite >= 3.35 (partial index UPSERT con WHERE).
    """
    assert sqlite3.sqlite_version_info >= (3, 35, 0), (
        f"SQLite >= 3.35 requerido (partial index UPSERT); actual {sqlite3.sqlite_version}"
    )
    conn = _new_conn()
    try:
        conn.executescript(_SCHEMA)
        # Migración auth_tokens.lab nullable: si la columna lab tiene NOT NULL,
        # recrear la tabla con lab TEXT nullable. Idempotente: si ya es nullable, no hace nada.
        cols = conn.execute("PRAGMA table_info(auth_tokens)").fetchall()
        lab_col = next((c for c in cols if c["name"] == "lab"), None)
        if lab_col is not None and lab_col["notnull"] == 1:
            # lab es NOT NULL (schema viejo FASE 1) → migrar a nullable
            conn.executescript("""
                CREATE TABLE auth_tokens_new(
                  token_hash   TEXT PRIMARY KEY,
                  email        TEXT NOT NULL,
                  lab          TEXT,
                  created_at   INTEGER NOT NULL,
                  expires_at   INTEGER NOT NULL,
                  used_at      INTEGER DEFAULT NULL,
                  used_from_ip TEXT
                );
                INSERT INTO auth_tokens_new
                  SELECT token_hash, email, lab, created_at, expires_at, used_at, used_from_ip
                  FROM auth_tokens;
                DROP TABLE auth_tokens;
                ALTER TABLE auth_tokens_new RENAME TO auth_tokens;
                CREATE INDEX IF NOT EXISTS idx_auth_tokens_email   ON auth_tokens(email);
                CREATE INDEX IF NOT EXISTS idx_auth_tokens_expires ON auth_tokens(expires_at);
            """)
            conn.execute("INSERT OR REPLACE INTO schema_version(version) VALUES (1)")
            log.warning("migración auth_tokens.lab nullable aplicada (v0→v1)")
        else:
            # Ya es nullable (schema nuevo) → marcar versión 1 si no lo está
            conn.execute(
                "INSERT OR IGNORE INTO schema_version(version) VALUES (1)"
            )
    finally:
        conn.close()