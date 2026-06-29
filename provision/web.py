"""FASE 6.2 — Rutas HTML del alumno y admin (Jinja2 + StaticFiles).

FastAPI sirve las páginas y los estáticos. Nginx es el edge TLS.
CSP estricta en las páginas HTML (no en la API JSON).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .auth import get_current_alumno, is_admin
from .config import Settings, get_settings

router = APIRouter()

_WEB_DIR = Path(__file__).resolve().parent / "web"
templates = Jinja2Templates(directory=str(_WEB_DIR / "templates"))

_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; "
    "frame-src 'self'; frame-ancestors 'self'; "
    "base-uri 'self'; form-action 'self'"
)


def _html(template: str, request: Request, **ctx) -> HTMLResponse:
    resp = templates.TemplateResponse(template, {"request": request, **ctx})
    resp.headers["Content-Security-Policy"] = _CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


# --- Alumno -----------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Login alumno. Si ya hay cookie válida → redirect /dashboard."""
    token = request.cookies.get("lab_token")
    if token:
        try:
            from .auth import verify_jwt
            verify_jwt(token, get_settings())
            return RedirectResponse(url="/dashboard", status_code=302)
        except Exception:
            pass
    return _html("login.html", request, title="Login", admin=False)


@router.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return _html("login.html", request, title="Login", admin=False)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, claims: dict = Depends(get_current_alumno)):
    """Dashboard alumno: lista labs + apps. Multi-lab si scope=dashboard."""
    return _html(
        "dashboard.html", request,
        title="Dashboard",
        alumno=claims["sub"],
        lab=claims.get("lab", ""),
        scope=claims.get("scope", "lab"),
    )


# --- Admin ------------------------------------------------------------------
@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login(request: Request):
    return _html("login.html", request, title="Login Admin", admin=True)


@router.get("/admin", response_class=HTMLResponse)
async def admin_console(
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Consola admin. Requiere cookie admin_token."""
    if not is_admin(request, settings):
        return RedirectResponse(url="/admin/login", status_code=302)
    return _html("admin/console.html", request, title="Consola Admin")