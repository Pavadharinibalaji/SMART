"""Application configuration and environment variable loading for SMART.

Resolves the project root relative to this module and loads the root `.env`
using python-dotenv before other modules read from `os.environ`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# Stable project root path: backend/config.py -> parent is backend -> parent is root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = PROJECT_ROOT / ".env"

if load_dotenv and DOTENV_PATH.exists():
    # override=False preserves explicitly provided environment variables (e.g. CI or system env)
    load_dotenv(dotenv_path=DOTENV_PATH, override=False)


DEFAULT_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


def is_production() -> bool:
    """Check if the environment is configured as production."""
    return os.environ.get("SMART_ENV", "development").strip().lower() == "production"


def is_env_var_configured(name: str) -> bool:
    """Safely check if an environment variable exists and is non-empty without exposing value."""
    val = os.environ.get(name)
    return bool(val and val.strip())


def get_oauth_config_status() -> dict[str, bool]:
    """Report whether each required OAuth and encryption variable is configured."""
    return {
        "GOOGLE_CLIENT_ID": is_env_var_configured("GOOGLE_CLIENT_ID"),
        "GOOGLE_CLIENT_SECRET": is_env_var_configured("GOOGLE_CLIENT_SECRET"),
        "GOOGLE_REDIRECT_URI": is_env_var_configured("GOOGLE_REDIRECT_URI"),
        "SMART_TOKEN_ENCRYPTION_KEY": is_env_var_configured("SMART_TOKEN_ENCRYPTION_KEY"),
    }


def get_cors_origins() -> list[str]:
    """Retrieve allowed CORS origins from environment variable or development defaults.
    
    Reads CORS_ORIGINS as a comma-separated list of origins.
    In development, includes default localhost origins for seamless local dev.
    In production:
    - Prohibits wildcards '*'.
    - Requires non-empty CORS_ORIGINS.
    - Requires at least one valid HTTPS origin.
    - Does not silently substitute localhost defaults.
    """
    raw_env = os.environ.get("CORS_ORIGINS", "").strip()
    prod = is_production()

    configured: list[str] = []
    if raw_env:
        for part in raw_env.split(","):
            origin = part.strip()
            if origin:
                if origin == "*":
                    raise ValueError("Security violation: Wildcard '*' origin is prohibited with credentials enabled.")
                configured.append(origin.rstrip("/"))

    if prod:
        if not configured:
            raise ValueError("Production configuration error: CORS_ORIGINS is required and cannot be empty in production.")
        https_origins = [o for o in configured if o.startswith("https://")]
        if not https_origins:
            raise ValueError("Production configuration error: CORS_ORIGINS must contain at least one valid HTTPS production origin.")
        return list(dict.fromkeys(configured))

    combined = list(dict.fromkeys(configured + DEFAULT_DEV_ORIGINS))
    return combined


def get_cookie_settings() -> dict[str, Any]:
    """Retrieve secure session cookie configuration.
    
    Configurable via:
    - COOKIE_SAMESITE: 'none', 'lax', or 'strict' (default: 'none' in production, 'lax' in development)
    - COOKIE_SECURE: boolean (default: True in production or when SameSite=None, False in local development)
    """
    prod = is_production()

    samesite_raw = os.environ.get("COOKIE_SAMESITE", "").strip().lower()
    if samesite_raw in ("none", "lax", "strict"):
        samesite = samesite_raw
    else:
        samesite = "none" if prod else "lax"

    secure_raw = os.environ.get("COOKIE_SECURE", "").strip().lower()
    if secure_raw in ("1", "true", "yes"):
        secure = True
    elif secure_raw in ("0", "false", "no"):
        secure = False
    else:
        secure = True if (prod or samesite == "none") else False

    # RFC requirement: Browsers reject SameSite=None cookies unless Secure=True
    if samesite == "none" and not secure:
        secure = True

    return {
        "samesite": samesite,
        "secure": secure,
        "httponly": True,
        "path": "/",
    }


def is_demo_login_allowed() -> bool:
    """Check if demo account authentication is enabled.
    
    Defaults to True in development/test, and False in production unless ALLOW_DEMO_LOGINS=true.
    """
    raw = os.environ.get("ALLOW_DEMO_LOGINS", "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    return not is_production()


def validate_production_config() -> dict[str, Any]:
    """Validate that required production variables are set without leaking secrets."""
    if not is_production():
        return {"status": "valid", "environment": "development"}

    errors: list[str] = []

    # 1. Encryption key validation
    enc_key = os.environ.get("SMART_TOKEN_ENCRYPTION_KEY", "").strip()
    if not enc_key:
        errors.append("SMART_TOKEN_ENCRYPTION_KEY is required in production environments.")

    # 2. CORS origins validation
    cors_raw = os.environ.get("CORS_ORIGINS", "").strip()
    if not cors_raw:
        errors.append("CORS_ORIGINS is required in production environments.")
    else:
        try:
            origins = get_cors_origins()
            https_origins = [o for o in origins if o.startswith("https://")]
            if not https_origins:
                errors.append("CORS_ORIGINS must contain at least one valid HTTPS production origin.")
        except ValueError as cors_err:
            errors.append(str(cors_err))

    # 3. Google OAuth validation (if configured)
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    if client_id:
        redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
        if not redirect_uri:
            errors.append("GOOGLE_REDIRECT_URI is required in production when Google OAuth is enabled.")
        elif "localhost" in redirect_uri or "127.0.0.1" in redirect_uri:
            errors.append("GOOGLE_REDIRECT_URI must not point to localhost in production.")

    # 4. Database URL validation (if configured)
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        if not (db_url.startswith("postgresql://") or db_url.startswith("postgres://")):
            errors.append("DATABASE_URL must be a valid postgresql:// connection URI.")

    if errors:
        raise ValueError(f"Production configuration validation failed: {'; '.join(errors)}")

    return {"status": "valid", "environment": "production"}
