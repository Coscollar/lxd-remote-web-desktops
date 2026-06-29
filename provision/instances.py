"""Funciones LXC async para instancias de laboratorio.

Todo `lxc` se invoca vía asyncio.create_subprocess_exec (NUNCA shell=True):
evita inyección de flags y no bloquea el event loop de uvicorn. Siempre se
añade `--project labs` como flag global (posición correcta: justo tras `lxc`).

Nombres de instancia y tags se validan contra NAME_RE / TAG_RE ANTES de
llegar a `lxc`, de modo que un valor malicioso nunca alcance el shell.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path
from typing import Optional

import yaml
from jinja2 import Environment, StrictUndefined, FileSystemLoader

from .config import Settings, get_settings

PROJECT = "labs"
PROFILE = "persistent"
BASE_IMAGE = "local:lab-vm-base"

# Whitelist estricta: un valor que no cashe NUNCA llega a `lxc`.
# FASE 6: NAME_RE de alumnos/labs PROHÍBE el prefijo `app-` (namespace de apps).
NAME_RE = re.compile(r"^(?!app-)[a-z0-9][a-z0-9-]{1,30}$")
TAG_RE = re.compile(r"^(base|k[1-5])$")
# FASE 6: apps usan prefijo `app-` obligatorio.
APP_NAME_RE = re.compile(r"^app-[a-z0-9][a-z0-9-]{1,30}$")

# Valores sudoers literales permitidos (coherente con cloud-init-template.yml)
_VALID_SUDO = {
    "ALL=(ALL) NOPASSWD:ALL",
    "ALL=(ALL) ALL",
    "",  # sin sudo
}


def _check_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ValueError(f"nombre inválido: {name!r}")
    return name


def _check_tag(tag: str) -> str:
    if not isinstance(tag, str) or not TAG_RE.match(tag):
        raise ValueError(f"tag inválido: {tag!r}")
    return tag


def instancia_nombre(alumno: str, lab: str) -> str:
    """Devuelve '<alumno>-<lab>' validado. Convención fijada en FASE 1."""
    _check_name(alumno)
    _check_name(lab)
    name = f"{alumno}-{lab}"
    _check_name(name)
    return name


# --- wrapper lxc ------------------------------------------------------------
async def lxc(*args: str, timeout: Optional[float] = None) -> tuple[int, bytes, bytes]:
    """Ejecuta `lxc --project labs <args>` sin shell. Devuelve (rc, out, err)."""
    cmd = ["lxc", "--project", PROJECT, *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode, out, err


async def _lxc_stdin(
    *args: str, stdin_data: bytes, timeout: Optional[float] = None
) -> tuple[int, bytes, bytes]:
    """lxc con stdin (para `-c user.user-data=-`)."""
    cmd = ["lxc", "--project", PROJECT, *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(input=stdin_data), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode, out, err


def _raise(rc: int, err: bytes, what: str) -> None:
    if rc != 0:
        raise RuntimeError(f"{what} falló (rc={rc}): {err.decode(errors='replace').strip()}")


# --- consultas --------------------------------------------------------------
async def exists(instancia: str) -> bool:
    _check_name(instancia)
    rc, out, _ = await lxc("list", f"^{instancia}$", "-c", "n", "--format", "csv")
    return any(line.strip() == instancia for line in out.decode().splitlines())


async def get_state(instancia: str) -> str:
    """Estado LXD: RUNNING/STOPPED/... Vacío si no existe."""
    _check_name(instancia)
    rc, out, _ = await lxc("list", f"^{instancia}$", "-c", "s", "--format", "csv")
    return out.decode().strip()


async def get_ip(instancia: str) -> str:
    _check_name(instancia)
    rc, out, _ = await lxc("list", f"^{instancia}$", "-c", "4", "--format", "csv")
    ip = out.decode().strip()
    if not ip:
        raise RuntimeError(f"sin IP para {instancia}")
    return ip.split(",")[0].strip()


async def list_snapshots(instancia: str) -> list[str]:
    _check_name(instancia)
    rc, out, _ = await lxc("snapshot", "list", instancia, "--format", "csv", "-c", "n")
    if rc != 0:
        return []
    return [line.strip() for line in out.decode().splitlines() if line.strip()]


# --- ciclo de vida ----------------------------------------------------------
async def launch(instancia: str, user_data: bytes) -> None:
    """lxc launch ... -c user.user-data=- (user-data vía stdin, no como arg)."""
    _check_name(instancia)
    rc, _, err = await _lxc_stdin(
        "launch", BASE_IMAGE, instancia, "--vm", "-p", PROFILE,
        "-c", "user.user-data=-",
        stdin_data=user_data,
        timeout=120,
    )
    _raise(rc, err, "lxc launch")


async def start(instancia: str) -> None:
    _check_name(instancia)
    rc, _, err = await lxc("start", instancia, timeout=60)
    _raise(rc, err, "lxc start")


async def start_if_stopped(instancia: str) -> None:
    if await get_state(instancia) == "STOPPED":
        await start(instancia)


async def stop(instancia: str, *, force: bool = False) -> None:
    """Idempotente: si ya STOPPED, no hace nada."""
    _check_name(instancia)
    if await get_state(instancia) == "STOPPED":
        return
    args = ["stop", instancia]
    if force:
        args.append("--force")
    rc, _, err = await lxc(*args, timeout=60)
    _raise(rc, err, "lxc stop")


async def delete(instancia: str) -> None:
    """Idempotente: si no existe, no hace nada."""
    _check_name(instancia)
    if not await exists(instancia):
        return
    rc, _, err = await lxc("delete", "-f", instancia, timeout=60)
    _raise(rc, err, "lxc delete")


# --- snapshots --------------------------------------------------------------
async def snapshot_create(instancia: str, tag: str) -> None:
    """Crea snapshot `tag`. Idempotente: precheck atómico (si existe, no recrea)."""
    _check_name(instancia)
    _check_tag(tag)
    if tag in await list_snapshots(instancia):
        return
    rc, _, err = await lxc("snapshot", instancia, tag, timeout=120)
    _raise(rc, err, f"lxc snapshot {tag}")


async def snapshot_delete(instancia: str, tag: str) -> None:
    """Idempotente: si el snapshot no existe, no hace nada."""
    _check_name(instancia)
    _check_tag(tag)
    snaps = await list_snapshots(instancia)
    if tag not in snaps:
        return
    rc, _, err = await lxc("delete", f"{instancia}/{tag}", timeout=60)
    _raise(rc, err, f"lxc delete snapshot {tag}")


async def snapshot_restore(instancia: str, tag: str) -> None:
    _check_name(instancia)
    _check_tag(tag)
    rc, _, err = await lxc("restore", instancia, tag, timeout=120)
    _raise(rc, err, f"lxc restore {tag}")


# --- cloud-init -------------------------------------------------------------
async def wait_cloud_init(instancia: str, timeout: int = 300) -> None:
    """Espera cloud-init con timeout y valida `status: done` literal."""
    _check_name(instancia)
    rc, _, err = await lxc(
        "exec", instancia, "--", "timeout", str(timeout),
        "cloud-init", "status", "--wait",
        timeout=timeout + 30,
    )
    if rc != 0:
        _, out2, _ = await lxc("exec", instancia, "--", "cloud-init", "status", "--long")
        raise RuntimeError(
            f"cloud-init status --wait falló: {err.decode(errors='replace').strip()}\n"
            f"{out2.decode(errors='replace')}"
        )
    _, out2, _ = await lxc("exec", instancia, "--", "cloud-init", "status", "--long")
    if "status: done" not in out2.decode(errors="replace"):
        raise RuntimeError(f"cloud-init no terminó en done: {out2.decode(errors='replace').strip()}")


async def _probe_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        fut = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


async def healthcheck_rdp(instancia: str, retries: int = 30, delay: float = 2.0) -> None:
    """Valida xrdp+xrdp-sesman activos y probe TCP 3389. 30×2s.

    Tolera IP transitoria (VM recién lanzada puede no tener IP en los primeros
    intentos): get_ip y _probe_tcp envueltos en try/except dentro del bucle.
    """
    _check_name(instancia)
    for _ in range(retries):
        try:
            rc, out, _ = await lxc(
                "exec", instancia, "--", "systemctl", "is-active", "xrdp", "xrdp-sesman"
            )
            states = [s.strip() for s in out.decode().splitlines() if s.strip()]
            if rc == 0 and states and all(s == "active" for s in states):
                ip = await get_ip(instancia)
                if await _probe_tcp(ip, 3389):
                    return
        except (RuntimeError, OSError, asyncio.TimeoutError):
            pass  # transitorio: reintentar
        await asyncio.sleep(delay)
    raise RuntimeError(f"xrdp no activo en {instancia} tras {retries} intentos")


# --- render cloud-init (Jinja2 estándar: {{ }} / {% %}) --------------------
def render_cloud_init(
    alumno: str,
    lab: str,
    token: str,
    *,
    settings: Settings | None = None,
    sudo_mode: str = "ALL=(ALL) NOPASSWD:ALL",
    ssh_keys: Optional[list[str]] = None,
    lab_packages: Optional[list[str]] = None,
    timezone: str = "Europe/Madrid",
) -> bytes:
    """Renderiza cloud-init-template.yml con Jinja2 y valida que el YAML parsea.

    El renderizado NUNCA se commitea: se pasa in-memory al `lxc launch`.
    user-data via stdin evita inyección de flags en la línea de comandos.
    Usa delimiters Jinja2 estándar ({{ }} / {% %}) coherentes con la plantilla.
    """
    _check_name(alumno)
    _check_name(lab)
    if sudo_mode not in _VALID_SUDO:
        raise ValueError(
            f"SUDO_MODE inválido: {sudo_mode!r} (esperado uno de {_VALID_SUDO})"
        )

    s = settings or get_settings()
    template_path = Path(__file__).resolve().parent.parent / "cloud-init-template.yml"
    if not template_path.is_file():
        raise FileNotFoundError(f"plantilla no encontrada: {template_path}")

    raw = template_path.read_text(encoding="utf-8")
    env = Environment(
        undefined=StrictUndefined,  # falla si falta una variable
        autoescape=False,
    )
    rendered = env.from_string(raw).render(
        ALUMNO=alumno,
        LAB=lab,
        PROVISION_URL_VM=s.provision_url_vm,
        LAB_SERVICE_TOKEN=token,
        SUDO_MODE=sudo_mode,
        SSH_AUTHORIZED_KEYS=ssh_keys or [],
        LAB_PACKAGES=lab_packages or [],
        TIMEZONE=timezone,
    )
    # Validar que el resultado es YAML parseable antes de lanzar la VM.
    yaml.safe_load(rendered)
    return rendered.encode("utf-8")


# --- FASE 6.3: Apps stateless (contenedores LXD, perfil stateless) --------
def app_instancia_nombre(app_id: str, alumno: Optional[str]) -> str:
    """Devuelve 'app-<id>' (shared) o 'app-<id>-<alumno>' (per-alumno).

    Si len > 30, sustituye <alumno> por sha8(alumno).
    """
    _check_name(app_id)
    if alumno is None:
        name = f"app-{app_id}"
    else:
        _check_name(alumno)
        full = f"app-{app_id}-{alumno}"
        if len(full) <= 30:
            name = full
        else:
            suffix = hashlib.sha256(alumno.encode()).hexdigest()[:8]
            name = f"app-{app_id}-{suffix}"
    if not APP_NAME_RE.match(name):
        raise ValueError(f"nombre de app inválido: {name!r}")
    return name


async def launch_container(
    instancia: str,
    image: str,
    *,
    cpu: Optional[int] = None,
    mem_mb: Optional[int] = None,
    user_data: Optional[bytes] = None,
    boot_autostart: bool = False,
    timeout: float = 120,
) -> None:
    """Lanza un contenedor LXD (NO VM) con perfil stateless. Sin --vm.

    FASE 6.3: separada de launch() (que tiene --vm hardcoded).
    """
    if not APP_NAME_RE.match(instancia):
        raise ValueError(f"nombre de app inválido: {instancia!r}")
    args = ["launch", image, instancia, "-p", "stateless"]
    if boot_autostart:
        args += ["-c", "boot.autostart=true"]
    if cpu is not None:
        args += ["-c", f"limits.cpu={cpu}"]
    if mem_mb is not None:
        args += ["-c", f"limits.memory={mem_mb}MB"]
    if user_data is not None:
        args += ["-c", "user.user-data=-"]
        rc, _, err = await _lxc_stdin(*args, stdin_data=user_data, timeout=timeout)
    else:
        rc, _, err = await lxc(*args, timeout=timeout)
    _raise(rc, err, "lxc launch container")


async def healthcheck_http(
    instancia: str, port: int, retries: int = 30, delay: float = 2.0
) -> None:
    """Healthcheck HTTP real (no solo TCP). Reusa _probe_tcp + valida HTTP.

    FASE 6.3: probe TCP al puerto de la app con retries. Tolera IP transitoria.
    """
    if not APP_NAME_RE.match(instancia):
        raise ValueError(f"nombre de app inválido: {instancia!r}")
    for _ in range(retries):
        try:
            ip = await get_ip(instancia)
            if await _probe_tcp(ip, port):
                return
        except (RuntimeError, OSError, asyncio.TimeoutError):
            pass  # transitorio: reintentar
        await asyncio.sleep(delay)
    raise RuntimeError(f"app {instancia} no responde en :{port} tras {retries} intentos")


async def wait_cloud_init_app(instancia: str, timeout: int = 120) -> None:
    """Espera cloud-init en contenedor de app (si la app usa cloud-init mínimo)."""
    if not APP_NAME_RE.match(instancia):
        raise ValueError(f"nombre de app inválido: {instancia!r}")
    rc, _, err = await lxc(
        "exec", instancia, "--", "timeout", str(timeout),
        "cloud-init", "status", "--wait",
        timeout=timeout + 30,
    )
    if rc != 0:
        _, out2, _ = await lxc("exec", instancia, "--", "cloud-init", "status", "--long")
        raise RuntimeError(
            f"cloud-init status --wait falló en app: {err.decode(errors='replace').strip()}\n"
            f"{out2.decode(errors='replace')}"
        )
    _, out2, _ = await lxc("exec", instancia, "--", "cloud-init", "status", "--long")
    if "status: done" not in out2.decode("replace"):
        raise RuntimeError(f"cloud-init no terminó en done en app: {out2.decode(errors='replace').strip()}")