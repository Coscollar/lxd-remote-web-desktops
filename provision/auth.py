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
    lab: str,
    settings: Settings,
) -> tuple[str, str]:
    """Emite JWT HS256. Devuelve (jwt, jti). Forzado a HS256."""
    jti = str(uuid.uuid4())
    now = _now()
    payload = {
        "sub": alumno_id,
        "lab": lab,
        "iat": now,
        "exp": now + settings.jwt_ttl,
        "jti": jti,
        "iss": settings.jwt_iss,
        "aud": settings.jwt_aud,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, jti


def verify_jwt(token: str, settings: Settings) -> dict:
    """Verifica JWT. Acepta también JWT_SECRET_PREV (rotación)."""
    last_err: Exception | None = None
    for secret in (settings.jwt_secret, settings.jwt_secret_prev):
        if not secret:
            continue
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                issuer=settings.jwt_iss,
                audience=settings.jwt_aud,
                options={"require": ["exp", "sub", "jti", "lab"]},
            )
        except jwt.PyJWTError as e:
            last_err = e
    raise last_err or jwt.InvalidTokenError("no secret configured")


def get_current_alumno(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Dependency: extrae y valida el JWT de la cookie lab_token."""
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
    """Pide magic link. Respuesta SIEMPRE neutra (anti-enumeración)."""
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
        return _NEUTRAL

    if len(rows) > 1 and not body.lab:
        labs = [r["lab"] for r in rows]
        return JSONResponse({"status": "choose", "labs": labs}, status_code=200)

    if len(rows) > 1 and body.lab:
        if not any(r["lab"] == body.lab for r in rows):
            # lab no válido: neutro (no revelar)
            return _NEUTRAL
        lab = body.lab
        alumno_id = next(r["alumno_id"] for r in rows if r["lab"] == body.lab)
    else:
        lab = rows[0]["lab"]
        alumno_id = rows[0]["alumno_id"]

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

    El token viaja en query string del magic link (un solo uso, TTL 15min).
    Nginx debe configurarse para NO loguear la query string de /auth/verify.
    """
    th = hash_token(token)
    now = _now()
    ip = _client_ip(request)

    conn = get_db()
    # BEGIN IMMEDIATE serializa el canje: dos peticiones simultáneas con el
    # mismo token no pueden ambas ver used_at IS NULL. La validación de
    # matrícula va DENTRO de la tx para no consumir el token si falla.
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
            # 410 Gone: token ya usado, expirado o inexistente (indistinguible)
            raise HTTPException(410, "gone")
        email, lab = row["email"], row["lab"]
        # Resolver alumno_id opaco DENTRO de la tx (atomicidad con el canje)
        enr = conn.execute(
            "SELECT alumno_id FROM enrollments WHERE email=? AND lab=? AND active=1",
            (email, lab),
        ).fetchone()
        if enr is None:
            # Matrícula desactivada: revertir el canje para no consumir el token
            conn.execute("ROLLBACK;")
            raise HTTPException(410, "gone")
        conn.execute("COMMIT;")
    except HTTPException:
        raise
    except Exception:
        conn.execute("ROLLBACK;")
        raise

    alumno_id = enr["alumno_id"]
    jwt_token, _jti = issue_jwt(alumno_id=alumno_id, lab=lab, settings=settings)
    resp = RedirectResponse(
        url=f"https://{settings.public_domain}/lab/start",
        status_code=302,
    )
    resp.set_cookie(
        key="lab_token",
        value=jwt_token,
        max_age=settings.jwt_ttl,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    # Evitar cache del token en el navegador/proxies
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@router.get("/verify")
async def nginx_auth_request(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    """Endpoint para `auth_request` de Nginx. 200 + headers o 401."""
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
    # Nginx reenvía estos headers al upstream (Guacamole/provision-api)
    return Response(
        status_code=200,
        headers={
            "X-Lab-Alumno": claims["sub"],
            "X-Lab-Name": claims["lab"],
        },
    )


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