"""Security and Cryptographic Protection Layer for SMART 2.1.

Implements:
1. Reversible authenticated encryption for Google OAuth access/refresh tokens.
2. Cryptographic CSRF state token generation and verification for OAuth 2.0.
3. Token sanitization for client API responses.
"""

from __future__ import annotations

import config  # Ensures root .env is loaded before accessing environment variables
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
    """Return True if an explicit persistent encryption key is provided and can initialize Fernet."""
    env_key = os.environ.get("SMART_TOKEN_ENCRYPTION_KEY", "").strip()
    if not env_key:
        return False
    try:
        key_bytes = env_key.encode("utf-8")
        Fernet(key_bytes)
        return True
    except Exception:
        # Validate that derived key succeeds
        try:
            derived = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
            Fernet(derived)
            return True
        except Exception:
            return False


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


def verify_google_id_token(
    id_token: str,
    expected_email: Optional[str] = None,
    client_id: Optional[str] = None,
) -> dict[str, Any]:
    """Verify a Google ID token's authenticity, expiration, and email claims.

    - In development/test environments, supports test tokens with format 'test_google_id_token_<email>' or 'mock_google_token_<email>'.
    - In live environments, validates token with Google's OAuth2 tokeninfo endpoint.
    - Verifies email_verified is True.
    - Verifies expected_email matches the token claim.
    """
    if not id_token or not id_token.strip():
        raise ValueError("Google ID token is required.")

    token_clean = id_token.strip()

    # Development & test harnesses support structured mock tokens
    smart_env = os.environ.get("SMART_ENV", "development").strip().lower()
    if smart_env != "production" and (
        token_clean.startswith("mock_google_token_")
        or token_clean.startswith("test_google_id_token_")
    ):
        parts = token_clean.split("_")
        token_email = parts[-1].strip().lower()
        if expected_email and token_email != expected_email.strip().lower():
            raise ValueError(f"Google ID token email '{token_email}' does not match requested email '{expected_email}'.")
        return {
            "email": token_email,
            "email_verified": True,
            "aud": client_id or "test-google-client-id",
            "name": "Verified Google User",
        }

    # Live verification via Google tokeninfo
    import httpx

    target_client_id = client_id or os.environ.get("GOOGLE_CLIENT_ID", "").strip()

    try:
        resp = httpx.get(
            f"https://oauth2.googleapis.com/tokeninfo?id_token={token_clean}",
            timeout=10.0,
        )
    except Exception as exc:
        raise ValueError(f"Could not connect to Google token verification service: {exc}")

    if resp.status_code != 200:
        raise ValueError(f"Google token verification failed (HTTP {resp.status_code}): {resp.text}")

    payload = resp.json()
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise ValueError("Google ID token did not contain an email claim.")

    email_verified = payload.get("email_verified")
    if email_verified not in (True, "true", "True", 1, "1"):
        raise ValueError(f"Google email '{email}' is not marked as verified by Google Workspace.")

    if target_client_id and payload.get("aud") != target_client_id:
        raise ValueError("Google ID token audience ('aud') does not match configured Google Client ID.")

    if expected_email and email != expected_email.strip().lower():
        raise ValueError(f"Google ID token email '{email}' does not match login email '{expected_email}'.")

    return payload
