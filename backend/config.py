"""Application configuration and environment variable loading for SMART.

Resolves the project root relative to this module and loads the root `.env`
using python-dotenv before other modules read from `os.environ`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

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
