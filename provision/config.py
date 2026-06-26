"""Configuración central leída de .env con validación de obligatorios.

Cualquier variable obligatoria ausente aborta el arranque (fail-fast):
no queremos que provision-api arranque con secretos vacíos y firme JWTs
con un secreto por defecto.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

# Variables sin las cuales provision-api no puede arrancar de forma segura.
_REQUIRED = (
    "JWT_SECRET",
    "JWT_SECRET_PREV",
    "SERVICE_JWT_SECRET",
    "SMTP_PROVIDER",
    "PUBLIC_DOMAIN",
    "PROVISION_URL",
    "PROVISION_URL_VM",
)


@dataclass(frozen=True)
class Settings:
    # --- JWT navegador (HS256) ---
    jwt_secret: str
    jwt_secret_prev: str           # rotación: acepta tokens firmados con el previo
    jwt_ttl: int                   # segundos, 1h por defecto
    jwt_iss: str
    jwt_aud: str

    # --- Service token de VM (HS256, secreto separado) ---
    service_jwt_secret: str
    service_jwt_ttl: int           # segundos (rotable vía /heartbeat en FASE 3)

    # --- SMTP ---
    smtp_provider: str             # mailtrap | (otros en prod)
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    smtp_from: str

    # --- Dominio / URLs ---
    public_domain: str
    provision_url: str             # URL interna del navegador (Nginx → api)
    provision_url_vm: str          # URL que usan las VMs (red lab-persistent)

    # --- Magic link ---
    magic_link_ttl: int            # 900s
    magic_link_len: int            # 32 bytes -> token_urlsafe

    # --- Rate-limit (slowapi) ---
    rl_per_ip: str                 # "5/minute"
    rl_per_email: str              # "3/10minutes"
    rl_global: str                 # "60/minute"

    # --- DB ---
    db_path: str

    @classmethod
    def from_env(cls) -> "Settings":
        missing = [k for k in _REQUIRED if not os.getenv(k)]
        if missing:
            raise RuntimeError(
                f"Variables obligatorias ausentes en .env: {', '.join(missing)}"
            )

        # Validar fortaleza de secretos (HS256 requiere >=32 bytes)
        jwt_secret = os.environ["JWT_SECRET"]
        jwt_secret_prev = os.environ["JWT_SECRET_PREV"]
        service_jwt_secret = os.environ["SERVICE_JWT_SECRET"]
        for name, val in (
            ("JWT_SECRET", jwt_secret),
            ("SERVICE_JWT_SECRET", service_jwt_secret),
        ):
            if len(val) < 32:
                raise RuntimeError(
                    f"{name} debe tener >=32 bytes para HS256 (recibido {len(val)})"
                )
        if jwt_secret_prev and len(jwt_secret_prev) < 32:
            raise RuntimeError("JWT_SECRET_PREV (si se define) debe tener >=32 bytes")

        provider = os.environ["SMTP_PROVIDER"]
        host = os.getenv(f"{provider.upper()}_HOST", "")
        port = int(os.getenv(f"{provider.upper()}_PORT", "587"))
        user = os.getenv(f"{provider.upper()}_USER", "")
        pwd = os.getenv(f"{provider.upper()}_PASS", "")

        return cls(
            jwt_secret=jwt_secret,
            jwt_secret_prev=jwt_secret_prev,
            jwt_ttl=int(os.getenv("JWT_TTL", "3600")),
            jwt_iss=os.getenv("JWT_ISS", "provision-api"),
            jwt_aud=os.getenv("JWT_AUD", "lab-gateway"),
            service_jwt_secret=service_jwt_secret,
            service_jwt_ttl=int(os.getenv("SERVICE_JWT_TTL", "86400")),
            smtp_provider=provider,
            smtp_host=host,
            smtp_port=port,
            smtp_user=user,
            smtp_pass=pwd,
            smtp_from=os.getenv(
                "SMTP_FROM", f"no-reply@{os.environ['PUBLIC_DOMAIN']}"
            ),
            public_domain=os.environ["PUBLIC_DOMAIN"],
            provision_url=os.environ["PROVISION_URL"],
            provision_url_vm=os.environ["PROVISION_URL_VM"],
            magic_link_ttl=int(os.getenv("MAGIC_LINK_TTL", "900")),
            magic_link_len=int(os.getenv("MAGIC_LINK_LEN", "32")),
            rl_per_ip=os.getenv("RL_PER_IP", "5/minute"),
            rl_per_email=os.getenv("RL_PER_EMAIL", "3/10minutes"),
            rl_global=os.getenv("RL_GLOBAL", "60/minute"),
            db_path=os.getenv("DB_PATH", "provision.db"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Carga .env una sola vez y construye Settings inmutable."""
    load_dotenv()
    return Settings.from_env()