"""Auth: magic link por email + JWT HS256 en cookie httpOnly.

Endpoints:
  POST /auth/request   — pide magic link (email [+lab si varios])
  POST /auth/verify    — canjea token por cookie JWT (single-use atómico)
  GET  /verify         — validación para Nginx auth_request
  POST /logout         — revoca jti y borra cookie

Helpers:
  hash_token, issue_jwt, verify_jwt, get_current_alumno
  issue_vm_token, verify_vm_token   (service token de VM, FASE 1.7)
"""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
import uuid
from typing import Optional

import aiosmtplib
import jwt
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import Settings, get_settings
from .db import get_db, tx
from . import instances

router = APIRouter()


# --- Rate-limit -------------------------------------------------------------
# slowapi necesita un limiter global; se registra en main.py.
# Detrás de Nginx: usar X-Real-IP (seteado por Nginx) o X-Forwarded-For.
def _client_ip(request: Request) -> str:
    xrip = request.headers.get("x-real-ip")
    if xrip:
        return xrip
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip)


def _real_client_ip(request: Request) -> str:
    """FASE 6.0: IP real del cliente. Usa X-Real-IP solo si la conexión
    viene de 127.0.0.1 (Nginx proxya todo como loopback). En caso contrario
    usa request.client.host (conexión directa, ej. desde VM/app).
    """
    peer = request.client.host if request.client else ""
    if peer == "127.0.0.1":
        xrip = request.headers.get("x-real-ip", "")
        if xrip:
            return xrip
    return peer


# --- Modelos ----------------------------------------------------------------
class RequestBody(BaseModel):
    email: EmailStr
    lab: Optional[str] = None   # solo si el alumno tiene >1 matrícula


class VerifyBody(BaseModel):
    token: str


# --- Helpers ----------------------------------------------------------------
def hash_token(token: str) -> str:
    """sha256 hex del token. El token en claro NUNCA se almacena."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> int:
    return int(time.time())


def issue_jwt(
    *,
    alumno_id: str,
    lab: Optional[str],
    settings: Settings,
    scope: str = "lab",
) -> tuple[str, str]:
    """Emite JWT HS256. Devuelve (jwt, jti). Forzado a HS256.

    FASE 6.1: lab es nullable (scope=dashboard → lab=None; scope=lab → lab fijado).
    """
    jti = str(uuid.uuid4())
    now = _now()
    payload: dict = {
        "sub": alumno_id,
        "scope": scope,
        "iat": now,
        "exp": now + settings.jwt_ttl,
        "jti": jti,
        "iss": settings.jwt_iss,
        "aud": settings.jwt_aud,
    }
    if lab is not None:
        payload["lab"] = lab
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, jti


def verify_jwt(token: str, settings: Settings) -> dict:
    """Verifica JWT alumno. Acepta también JWT_SECRET_PREV (rotación).

    FASE 6.1: require relajado a ["exp","sub","jti","scope"]; lab exigido
    solo si scope=="lab" (validación en el endpoint, no en decode).
    """
    last_err: Exception | None = None
    for secret in (settings.jwt_secret, settings.jwt_secret_prev):
        if not secret:
            continue
        try:
            claims = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                issuer=settings.jwt_iss,
                audience=settings.jwt_aud,
                options={"require": ["exp", "sub", "jti", "scope"]},
            )
            # Si scope=lab, exigir lab presente
            if claims.get("scope") == "lab" and "lab" not in claims:
                raise jwt.InvalidTokenError("scope=lab requiere claim lab")
            return claims
        except jwt.PyJWTError as e:
            last_err = e
    raise last_err or jwt.InvalidTokenError("no secret configured")


# --- FASE 6.1: JWT admin (secreto + aud separados) ------------------------
def issue_admin_jwt(*, email: str, settings: Settings) -> tuple[str, str]:
    """Emite JWT admin HS256 con ADMIN_JWT_SECRET (separado del navegador)."""
    jti = str(uuid.uuid4())
    now = _now()
    payload = {
        "sub": email,
        "role": "admin",
        "iat": now,
        "exp": now + settings.admin_jwt_ttl,
        "jti": jti,
        "iss": settings.jwt_iss,
        "aud": settings.admin_jwt_aud,
    }
    token = jwt.encode(payload, settings.admin_jwt_secret, algorithm="HS256")
    return token, jti


def verify_admin_jwt(token: str, settings: Settings) -> dict:
    """Verifica JWT admin. Acepta ADMIN_JWT_SECRET_PREV (rotación)."""
    last_err: Exception | None = None
    for secret in (settings.admin_jwt_secret, settings.admin_jwt_secret_prev):
        if not secret:
            continue
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                issuer=settings.jwt_iss,
                audience=settings.admin_jwt_aud,
                options={"require": ["exp", "sub", "jti", "role"]},
            )
        except jwt.PyJWTError as e:
            last_err = e
    raise last_err or jwt.InvalidTokenError("no admin secret configured")


def get_current_alumno(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Dependency: extrae y valida el JWT de la cookie lab_token (cualquier scope).

    FASE 6.1: acepta scope=dashboard (lab null) y scope=lab (lab fijado).
    """
    token = request.cookies.get("lab_token")
    if not token:
        raise HTTPException(401, "no cookie")
    claims = verify_jwt(token, settings)
    # jti revocado?
    row = get_db().execute(
        "SELECT 1 FROM jwt_jti WHERE jti=?", (claims["jti"],)
    ).fetchone()
    if row is not None:
        raise HTTPException(401, "revoked")
    return claims


def get_current_alumno_lab(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Dependency: JWT con scope=lab (lab fijado). Para /lab/start, /lab/status."""
    claims = get_current_alumno(request, settings)
    if claims.get("scope") != "lab" or "lab" not in claims:
        raise HTTPException(401, "scope=lab required")
    return claims


# --- Service token de VM (FASE 1.7) ----------------------------------------
def issue_vm_token(
    *,
    instancia: str,
    vm_ip: str,
    scope: tuple[str, ...] = ("save", "reset", "heartbeat"),
    settings: Settings | None = None,
) -> str:
    """Token HS256 con SERVICE_JWT_SECRET (separado del navegador).

    Persiste sha256(token) + IP registrada en vm_tokens. La IP se valida
    en /save /reset /restore (no solo rango).
    """
    s = settings or get_settings()
    now = _now()
    exp = now + s.service_jwt_ttl
    payload = {
        "sub": instancia,
        "scope": list(scope),
        "iat": now,
        "exp": exp,
        "iss": s.jwt_iss,
        "aud": "vm-service",
    }
    token = jwt.encode(payload, s.service_jwt_secret, algorithm="HS256")
    th = hash_token(token)
    with tx() as conn:
        conn.execute(
            """INSERT INTO vm_tokens(instancia, token_hash, vm_ip, issued_at, expires_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(instancia) DO UPDATE SET
                 token_hash=excluded.token_hash,
                 vm_ip=excluded.vm_ip,
                 issued_at=excluded.issued_at,
                 expires_at=excluded.expires_at,
                 rotated_from=vm_tokens.token_hash""",
            (instancia, th, vm_ip, now, exp),
        )
    return token


def verify_vm_token(
    token: str,
    *,
    required_scope: str,
    remote_ip: str,
    settings: Settings | None = None,
) -> dict:
    """Valida service token: HS256 + scope + IP registrada en BD."""
    s = settings or get_settings()
    try:
        claims = jwt.decode(
            token,
            s.service_jwt_secret,
            algorithms=["HS256"],
            issuer=s.jwt_iss,
            audience="vm-service",
            options={"require": ["exp", "sub", "scope"]},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"service token inválido: {e}")

    if required_scope not in claims.get("scope", []):
        raise HTTPException(403, f"scope '{required_scope}' requerido")

    instancia = claims["sub"]
    th = hash_token(token)
    row = get_db().execute(
        "SELECT token_hash, vm_ip, expires_at FROM vm_tokens WHERE instancia=?",
        (instancia,),
    ).fetchone()
    if row is None:
        raise HTTPException(401, "instancia no registrada")
    # Validar que el token presentado es el ACTIVO (no uno rotado)
    if row["token_hash"] != th:
        raise HTTPException(401, "service token no es el activo (rotado)")
    # IP estricta (no solo rango): la VM debe llamar desde la IP registrada
    if row["vm_ip"] != remote_ip:
        raise HTTPException(403, "IP no coincide con la registrada")
    if row["expires_at"] < _now():
        raise HTTPException(401, "service token expirado")
    return claims


# --- Email ------------------------------------------------------------------
_EMAIL_HTML = """\
<html><body style="font-family:sans-serif">
<p>Hola,</p>
<p>Haz clic en el siguiente enlace para acceder a tu laboratorio.
El enlace caduca en 15 minutos y es de un solo uso.</p>
<p><a href="{{link}}">Acceder al laboratorio</a></p>
<p>Si no solicitaste este acceso, ignora este correo.</p>
</body></html>
"""

_EMAIL_TEXT = (
    "Accede a tu laboratorio con el siguiente enlace (caduca en 15 min, "
    "un solo uso):\n{link}\n\nSi no lo solicitaste, ignora este correo.\n"
)


async def _send_email(to: str, link: str, settings: Settings) -> None:
    msg = MIMEMultipart("alternative")
    msg["From"] = settings.smtp_from
    msg["To"] = to
    # Asunto neutro: NO contiene el token ni el lab (anti-fuga)
    msg["Subject"] = "Acceso a tu laboratorio"
    msg.attach(MIMEText(_EMAIL_TEXT.format(link=link), "plain", "utf-8"))
    msg.attach(MIMEText(_EMAIL_HTML.replace("{{link}}", link), "html", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_pass,
        start_tls=True,
    )


def _enqueue_email(to: str, link: str, settings: Settings) -> None:
    """Fire-and-forget: no bloquea la respuesta HTTP."""
    loop = asyncio.get_event_loop()
    loop.create_task(_send_email(to, link, settings))


# --- Endpoints --------------------------------------------------------------
_NEUTRAL = JSONResponse({"status": "enviado"}, status_code=200)


@router.post("/auth/request")
@limiter.limit("5/minute")
async def auth_request(
    request: Request,
    body: RequestBody,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Pide magic link. Respuesta SIEMPRE neutra (anti-enumeración).

    FASE 6.1: elimina el flujo `choose`. Si el email tiene >1 matrícula,
    el token se guarda con lab=null (multi-lab → dashboard). Si tiene 1,
    lab fijado. Si 0, neutro sin envío.
    """
    # Rate-limit por email (además del por IP del decorador)
    key = f"rl:email:{body.email.lower()}"
    if not _email_rate_allow(key, settings):
        raise HTTPException(429, "demasiadas peticiones")

    conn = get_db()
    rows = conn.execute(
        "SELECT alumno_id, lab FROM enrollments WHERE email=? AND active=1",
        (body.email.lower(),),
    ).fetchall()

    if not rows:
        # No existe matrícula: respuesta neutra, no enviamos nada.
        # Igualar trabajo (anti-timing): hash aleatorio + sleep pequeño.
        import hashlib, os as _os, asyncio as _aio
        _ = hashlib.sha256(_os.urandom(32)).hexdigest()
        return _NEUTRAL

    if len(rows) == 1:
        lab = rows[0]["lab"]
    else:
        # Multi-lab: lab=null (dashboard decidirá)
        lab = None

    # Generar token de un solo uso
    token = secrets.token_urlsafe(settings.magic_link_len)
    th = hash_token(token)
    now = _now()
    conn.execute(
        """INSERT INTO auth_tokens(token_hash, email, lab, created_at, expires_at)
           VALUES(?,?,?,?,?)""",
        (th, body.email.lower(), lab, now, now + settings.magic_link_ttl),
    )
    conn.commit()

    link = f"https://{settings.public_domain}/auth/verify?token={token}"
    _enqueue_email(body.email, link, settings)
    return _NEUTRAL


@router.get("/auth/verify")
@limiter.limit("30/minute")
async def auth_verify(
    request: Request,
    token: str,
    settings: Settings = Depends(get_settings),
) -> Response:
    """Canjea token por cookie JWT. Single-use atómico (BEGIN IMMEDIATE).

    FASE 6.1: si el token tenía lab fijado → JWT scope=lab → /lab/start.
    Si lab=null (multi-lab) → re-cuenta matrículas:
      0 → 410, 1 → auto-select scope=lab → /lab/start, >1 → scope=dashboard → /dashboard.
    """
    th = hash_token(token)
    now = _now()
    ip = _real_client_ip(request)

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        cur = conn.execute(
            """UPDATE auth_tokens
                  SET used_at=?, used_from_ip=?
                WHERE token_hash=? AND used_at IS NULL AND expires_at>?
                RETURNING email, lab""",
            (now, ip, th, now),
        )
        row = cur.fetchone()
        if row is None:
            conn.execute("ROLLBACK;")
            raise HTTPException(410, "gone")
        email, lab = row["email"], row["lab"]

        if lab is not None:
            # Lab fijado en el token → JWT scope=lab
            enr = conn.execute(
                "SELECT alumno_id FROM enrollments WHERE email=? AND lab=? AND active=1",
                (email, lab),
            ).fetchone()
            if enr is None:
                conn.execute("ROLLBACK;")
                raise HTTPException(410, "gone")
            conn.execute("COMMIT;")
            alumno_id = enr["alumno_id"]
            jwt_token, _jti = issue_jwt(alumno_id=alumno_id, lab=lab, settings=settings, scope="lab")
            redirect_url = f"https://{settings.public_domain}/lab/start"
        else:
            # Multi-lab (lab=null) → re-cuenta matrículas activas
            enrs = conn.execute(
                "SELECT alumno_id, lab FROM enrollments WHERE email=? AND active=1",
                (email,),
            ).fetchall()
            if len(enrs) == 0:
                conn.execute("ROLLBACK;")
                raise HTTPException(410, "gone")
            elif len(enrs) == 1:
                # Auto-select: una sola matrícula → scope=lab directo
                conn.execute("COMMIT;")
                alumno_id = enrs[0]["alumno_id"]
                jwt_token, _jti = issue_jwt(alumno_id=alumno_id, lab=enrs[0]["lab"], settings=settings, scope="lab")
                redirect_url = f"https://{settings.public_domain}/lab/start"
            else:
                # >1 matrícula → scope=dashboard, lab=null
                conn.execute("COMMIT;")
                alumno_id = enrs[0]["alumno_id"]  # sub opaco; el dashboard lista por alumno_id
                jwt_token, _jti = issue_jwt(alumno_id=alumno_id, lab=None, settings=settings, scope="dashboard")
                redirect_url = f"https://{settings.public_domain}/dashboard"
    except HTTPException:
        raise
    except Exception:
        conn.execute("ROLLBACK;")
        raise

    resp = RedirectResponse(url=redirect_url, status_code=302)
    resp.set_cookie(
        key="lab_token",
        value=jwt_token,
        max_age=settings.jwt_ttl,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@router.get("/verify")
async def nginx_auth_request(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    """Endpoint para `auth_request` de Nginx. 200 + headers o 401.

    FASE 6.1: re-valida matrícula activa (SELECT enrollments) para que
    desactivar una matrícula revoque el acceso efectivo en el siguiente
    auth_request. Devuelve X-Lab-Scope para que Nginx decida enrutar a
    Guacamole (solo si scope=lab) o rechazar /desktop.
    """
    token = request.cookies.get("lab_token")
    if not token:
        return Response(status_code=401)
    try:
        claims = verify_jwt(token, settings)
    except jwt.PyJWTError:
        return Response(status_code=401)
    # jti revocado?
    row = get_db().execute(
        "SELECT 1 FROM jwt_jti WHERE jti=?", (claims["jti"],)
    ).fetchone()
    if row is not None:
        return Response(status_code=401)
    # Re-validar matrícula activa si scope=lab
    scope = claims.get("scope", "lab")
    lab = claims.get("lab", "")
    if scope == "lab" and lab:
        enr = get_db().execute(
            "SELECT 1 FROM enrollments WHERE alumno_id=? AND lab=? AND active=1",
            (claims["sub"], lab),
        ).fetchone()
        if enr is None:
            return Response(status_code=401)
    headers = {
        "X-Lab-Alumno": claims["sub"],
        "X-Lab-Name": lab if scope == "lab" else "",
        "X-Lab-Scope": scope,
        "X-Lab-Role": "alumno",
    }
    return Response(status_code=200, headers=headers)


# --- FASE 6.1: /lab/select (multi-lab) -------------------------------------
class SelectBody(BaseModel):
    lab: str


@router.post("/lab/select")
async def lab_select(
    request: Request,
    body: SelectBody,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Reemite JWT con lab seleccionado. Valida matrícula.

    FASE 6.1: orden seguro = emitir nuevo → set cookie → revocar viejo.
    Acepta scope=lab o dashboard (saltar entre labs sin re-login).
    BEGIN IMMEDIATE para race de dos pestañas.
    """
    # CSRF: exigir X-Requested-With
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(403, "X-Requested-With required")
    token = request.cookies.get("lab_token")
    if not token:
        raise HTTPException(401, "no cookie")
    claims = verify_jwt(token, settings)
    # jti revocado?
    row = get_db().execute(
        "SELECT 1 FROM jwt_jti WHERE jti=?", (claims["jti"],)
    ).fetchone()
    if row is not None:
        raise HTTPException(401, "revoked")

    alumno_id = claims["sub"]
    lab = body.lab
    # Validar NAME_RE
    instances._check_name(lab)
    # Validar matrícula activa
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        enr = conn.execute(
            "SELECT 1 FROM enrollments WHERE alumno_id=? AND lab=? AND active=1",
            (alumno_id, lab),
        ).fetchone()
        if enr is None:
            conn.execute("ROLLBACK;")
            raise HTTPException(403, "no matriculado")
        conn.execute("COMMIT;")
    except HTTPException:
        raise
    except Exception:
        conn.execute("ROLLBACK;")
        raise

    # Orden seguro: emitir nuevo → set cookie → revocar viejo
    new_token, new_jti = issue_jwt(alumno_id=alumno_id, lab=lab, settings=settings, scope="lab")
    resp = JSONResponse({"redirect": "/lab/start"}, status_code=200)
    resp.set_cookie(
        key="lab_token", value=new_token, max_age=settings.jwt_ttl,
        path="/", secure=True, httponly=True, samesite="lax",
    )
    # Revocar viejo (best-effort: si falla, el viejo sigue válido hasta exp)
    try:
        get_db().execute(
            "INSERT INTO jwt_jti(jti, revoked_at) VALUES(?,?) ON CONFLICT DO NOTHING",
            (claims["jti"], _now()),
        )
        get_db().commit()
    except Exception:
        pass
    return resp


# --- FASE 6.1: /api/my-labs (dashboard) -------------------------------------
@router.get("/api/my-labs")
async def my_labs(claims: dict = Depends(get_current_alumno)):
    """Lista labs del alumno + estado instancias. Para el dashboard."""
    alumno_id = claims["sub"]
    conn = get_db()
    rows = conn.execute(
        """SELECT e.lab, e.course, l.imagen, l.deadline,
                  COALESCE(i.estado, 'inexistente') AS estado_instancia
             FROM enrollments e
             JOIN labs l ON e.lab = l.nombre
             LEFT JOIN instancias i ON i.alumno = e.alumno_id AND i.lab = e.lab
            WHERE e.alumno_id=? AND e.active=1""",
        (alumno_id,),
    ).fetchall()
    labs = [dict(r) for r in rows]
    return {"labs": labs, "current": claims.get("lab")}


@router.post("/logout")
async def logout(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    token = request.cookies.get("lab_token")
    resp = Response(status_code=204)
    resp.delete_cookie(
        key="lab_token", path="/", secure=True, samesite="lax"
    )
    if not token:
        return resp
    try:
        claims = verify_jwt(token, settings)
    except jwt.PyJWTError:
        return resp
    # Idempotente: ON CONFLICT no duplica
    get_db().execute(
        "INSERT INTO jwt_jti(jti, revoked_at) VALUES(?,?) "
        "ON CONFLICT(jti) DO NOTHING",
        (claims["jti"], _now()),
    )
    get_db().commit()
    return resp


# --- Rate-limit por email (en memoria, suficiente para dev) -----------------
_email_hits: dict[str, list[int]] = {}


def _email_rate_allow(key: str, settings: Settings) -> bool:
    """3 por 10 minutos por email. Ventana deslizante en memoria."""
    now = _now()
    window = 600
    hits = [t for t in _email_hits.get(key, []) if t > now - window]
    if len(hits) >= 3:
        _email_hits[key] = hits
        return False
    hits.append(now)
    _email_hits[key] = hits
    return True


# --- FASE 6.1: Admin auth (magic link, secreto + aud separados) ------------
class AdminRequestBody(BaseModel):
    email: EmailStr


_ADMIN_NEUTRAL = JSONResponse({"status": "enviado"}, status_code=200)
_admin_email_hits: dict[str, list[int]] = {}


def _admin_email_rate_allow(key: str) -> bool:
    """2 por 15 minutos por email admin. Más estricto que alumno."""
    now = _now()
    window = 900
    hits = [t for t in _admin_email_hits.get(key, []) if t > now - window]
    if len(hits) >= 2:
        _admin_email_hits[key] = hits
        return False
    hits.append(now)
    _admin_email_hits[key] = hits
    return True


@router.post("/admin/auth/request")
@limiter.limit("3/minute")
async def admin_auth_request(
    request: Request,
    body: AdminRequestBody,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Magic link admin. Allowlist admins.active=1. Respuesta SIEMPRE neutra."""
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(403, "X-Requested-With required")
    key = f"rl:admin:{body.email.lower()}"
    if not _admin_email_rate_allow(key):
        raise HTTPException(429, "demasiadas peticiones")

    conn = get_db()
    admin = conn.execute(
        "SELECT 1 FROM admins WHERE email=? AND active=1",
        (body.email.lower(),),
    ).fetchone()
    if admin is None:
        # Neutro: no enviamos nada (anti-enumeración)
        import hashlib, os as _os
        _ = hashlib.sha256(_os.urandom(32)).hexdigest()
        return _ADMIN_NEUTRAL

    token = secrets.token_urlsafe(settings.magic_link_len)
    th = hash_token(token)
    now = _now()
    conn.execute(
        """INSERT INTO admin_auth_tokens(token_hash, email, created_at, expires_at)
           VALUES(?,?,?,?)""",
        (th, body.email.lower(), now, now + settings.admin_magic_link_ttl),
    )
    conn.commit()

    link = f"https://{settings.public_domain}/admin/auth/verify?token={token}"
    _enqueue_email(body.email, link, settings)
    return _ADMIN_NEUTRAL


@router.get("/admin/auth/verify")
@limiter.limit("10/minute")
async def admin_auth_verify(
    request: Request,
    token: str,
    settings: Settings = Depends(get_settings),
) -> Response:
    """Canjea token admin por cookie admin_token. Single-use atómico."""
    th = hash_token(token)
    now = _now()
    ip = _real_client_ip(request)

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        cur = conn.execute(
            """UPDATE admin_auth_tokens
                  SET used_at=?, used_from_ip=?
                WHERE token_hash=? AND used_at IS NULL AND expires_at>?
                RETURNING email""",
            (now, ip, th, now),
        )
        row = cur.fetchone()
        if row is None:
            conn.execute("ROLLBACK;")
            raise HTTPException(410, "gone")
        email = row["email"]
        # Verificar que sigue activo
        admin = conn.execute(
            "SELECT 1 FROM admins WHERE email=? AND active=1", (email,)
        ).fetchone()
        if admin is None:
            conn.execute("ROLLBACK;")
            raise HTTPException(410, "gone")
        conn.execute("COMMIT;")
    except HTTPException:
        raise
    except Exception:
        conn.execute("ROLLBACK;")
        raise

    # Registrar login (auditoría)
    conn = get_db()
    conn.execute(
        "INSERT INTO admin_logins(email, ip, ua, at) VALUES(?,?,?,?)",
        (email, ip, request.headers.get("user-agent", ""), now),
    )
    conn.execute(
        "UPDATE admins SET last_login_at=? WHERE email=?", (now, email)
    )
    conn.commit()

    # Notificación email (outbox persistente, sin enlaces accionables)
    conn.execute(
        "INSERT INTO email_outbox(to_email, subject, body, created_at) VALUES(?,?,?,?)",
        (email, "Acceso admin canjeado",
         f"Se canjeó un acceso admin desde IP {ip} a las {now}. "
         "Si no fuiste tú, contacta con soporte. No respondas a este email.",
         now),
    )
    conn.commit()

    jwt_token, _jti = issue_admin_jwt(email=email, settings=settings)
    redirect_url = f"https://{settings.public_domain}/admin"
    resp = RedirectResponse(url=redirect_url, status_code=302)
    resp.set_cookie(
        key="admin_token", value=jwt_token, max_age=settings.admin_jwt_ttl,
        path="/admin", secure=True, httponly=True, samesite="lax",
    )
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@router.get("/admin/verify")
async def admin_nginx_auth_request(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    """Endpoint para `auth_request` de Nginx en /admin/*. 200 + headers o 401."""
    token = request.cookies.get("admin_token")
    if not token:
        return Response(status_code=401)
    try:
        claims = verify_admin_jwt(token, settings)
    except jwt.PyJWTError:
        return Response(status_code=401)
    row = get_db().execute(
        "SELECT 1 FROM admin_jwt_jti WHERE jti=?", (claims["jti"],)
    ).fetchone()
    if row is not None:
        return Response(status_code=401)
    return Response(
        status_code=200,
        headers={
            "X-Lab-Role": "admin",
            "X-Admin-Email": claims["sub"],
        },
    )


@router.post("/admin/logout")
async def admin_logout(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(403, "X-Requested-With required")
    token = request.cookies.get("admin_token")
    resp = Response(status_code=204)
    resp.delete_cookie(key="admin_token", path="/admin", secure=True, samesite="lax")
    if not token:
        return resp
    try:
        claims = verify_admin_jwt(token, settings)
    except jwt.PyJWTError:
        return resp
    get_db().execute(
        "INSERT INTO admin_jwt_jti(jti, revoked_at) VALUES(?,?) ON CONFLICT DO NOTHING",
        (claims["jti"], _now()),
    )
    get_db().commit()
    return resp


# --- FASE 6.1: is_admin (reemplaza _admin_ok en main.py) -------------------
def is_admin(request: Request, settings: Settings) -> bool:
    """True si la request viene de un admin (cookie admin_token O X-Admin-Token).

    X-Admin-Token se conserva para automatización (curl/systemd).
    Cookie admin_token para la consola navegador (FASE 6).
    """
    import secrets as _s
    # 1) X-Admin-Token (scripts)
    tok = request.headers.get("x-admin-token", "")
    if tok and settings.admin_token and _s.compare_digest(tok, settings.admin_token):
        return True
    # 2) Cookie admin_token (navegador)
    token = request.cookies.get("admin_token")
    if not token:
        return False
    try:
        claims = verify_admin_jwt(token, settings)
    except jwt.PyJWTError:
        return False
    row = get_db().execute(
        "SELECT 1 FROM admin_jwt_jti WHERE jti=?", (claims["jti"],)
    ).fetchone()
    if row is not None:
        return False
    return True