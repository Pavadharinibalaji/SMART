"""Security and Cryptographic Protection Layer for SMART 2.1.

Implements:
1. Reversible authenticated encryption for Google OAuth access/refresh tokens.
2. Cryptographic CSRF state token generation and verification for OAuth 2.0.
3. Token sanitization for client API responses.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import secrets
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

_RUNTIME_ENCRYPTION_KEY: Optional[bytes] = None


def get_token_encryption_key() -> tuple[bytes, bool]:
    """Retrieve or generate the symmetric encryption key for OAuth tokens.

    Returns:
        (key_bytes, is_persistent)
    """
    global _RUNTIME_ENCRYPTION_KEY

    # Check environment variable
    env_key = os.environ.get("SMART_TOKEN_ENCRYPTION_KEY", "").strip()
    if env_key:
        try:
            # Validate Fernet key format (32 urlsafe base64 bytes)
            key_bytes = env_key.encode("utf-8")
            Fernet(key_bytes)
            return key_bytes, True
        except Exception:
            # If invalid format, derive valid Fernet key using SHA-256
            derived = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
            return derived, True

    # Ephemeral runtime key fallback
    if _RUNTIME_ENCRYPTION_KEY is None:
        _RUNTIME_ENCRYPTION_KEY = Fernet.generate_key()

    return _RUNTIME_ENCRYPTION_KEY, False


def is_secure_persistence_configured() -> bool:
    """Return True if an explicit persistent encryption key is provided."""
    return bool(os.environ.get("SMART_TOKEN_ENCRYPTION_KEY", "").strip())


def encrypt_token(token: str) -> str:
    """Encrypt a Google OAuth access or refresh token using reversible authenticated encryption."""
    if not token:
        return ""
    key, is_persistent = get_token_encryption_key()
    fernet = Fernet(key)
    encrypted_bytes = fernet.encrypt(token.encode("utf-8"))
    return encrypted_bytes.decode("ascii")


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an encrypted OAuth access or refresh token."""
    if not encrypted_token:
        return ""
    key, _ = get_token_encryption_key()
    fernet = Fernet(key)
    try:
        decrypted_bytes = fernet.decrypt(encrypted_token.encode("ascii"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        raise ValueError("Failed to decrypt Google token: invalid key or corrupted payload.")


def generate_session_id() -> str:
    """Generate high-entropy cryptographically secure session ID."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Generate high-entropy cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)


def get_csrf_signing_secret() -> bytes:
    """Retrieve CSRF state signing secret."""
    secret = os.environ.get("SMART_PROVENANCE_SECRET", "").strip()
    if secret:
        return secret.encode("utf-8")
    key, _ = get_token_encryption_key()
    return key


def generate_oauth_state(role: str = "student", redirect_uri: str = "") -> str:
    """Generate a tamper-proof, timestamped OAuth state string to prevent CSRF."""
    nonce = secrets.token_hex(16)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "nonce": nonce,
        "role": role,
        "redirect_uri": redirect_uri,
        "ts": timestamp,
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("ascii")
    sig = hmac.new(get_csrf_signing_secret(), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def validate_oauth_state(state: str, max_age_seconds: int = 600) -> Optional[dict[str, Any]]:
    """Validate OAuth state parameter and return payload if valid and unexpired."""
    if not state or "." not in state:
        return None
    parts = state.split(".", 1)
    if len(parts) != 2:
        return None
    payload_b64, sig = parts
    expected_sig = hmac.new(get_csrf_signing_secret(), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None

    try:
        raw_json = base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8")
        payload = json.loads(raw_json)
        ts = int(payload.get("ts", 0))
        now = int(datetime.now(timezone.utc).timestamp())
        if now - ts > max_age_seconds:
            return None  # Expired
        return payload
    except Exception:
        return None


def sanitize_account_for_response(account: dict[str, Any]) -> dict[str, Any]:
    """Sanitize account dictionary to strictly prevent token exposure over API."""
    safe = dict(account)
    has_access_token = bool(safe.pop("encrypted_access_token", None))
    has_refresh_token = bool(safe.pop("encrypted_refresh_token", None))
    safe["has_access_token"] = has_access_token
    safe["has_refresh_token"] = has_refresh_token
    safe["secure_persistence_configured"] = is_secure_persistence_configured()
    return safe
