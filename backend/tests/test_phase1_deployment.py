"""Tests for Phase 1: Environment Configuration and Authentication Hardening."""

from __future__ import annotations

import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

import config
from config import (
    DEFAULT_DEV_ORIGINS,
    get_cookie_settings,
    get_cors_origins,
    is_demo_login_allowed,
    is_production,
    validate_production_config,
)
from google_service import build_authorization_url
from main import app
from security import get_token_encryption_key


@pytest.fixture
def client():
    return TestClient(app)


# ------------------------------------------------------------------------------
# 1. CORS Configuration Tests
# ------------------------------------------------------------------------------

def test_cors_origins_dev_defaults(monkeypatch):
    """Verify that default development origins are included when CORS_ORIGINS is empty."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    origins = get_cors_origins()
    for dev_origin in DEFAULT_DEV_ORIGINS:
        assert dev_origin in origins


def test_cors_origins_custom_configured(monkeypatch):
    """Verify comma-separated origins are parsed and normalized without trailing slashes."""
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://smart-app.vercel.app, https://smart-dashboard.edu/ , https://preview.vercel.app"
    )
    origins = get_cors_origins()
    assert "https://smart-app.vercel.app" in origins
    assert "https://smart-dashboard.edu" in origins
    assert "https://preview.vercel.app" in origins
    # Dev origins should still be preserved
    assert "http://localhost:5173" in origins


def test_cors_origins_prod_requires_origins(monkeypatch):
    """In production, missing CORS_ORIGINS raises ValueError."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with pytest.raises(ValueError, match="CORS_ORIGINS is required"):
        get_cors_origins()


def test_cors_origins_prod_requires_https(monkeypatch):
    """In production, CORS_ORIGINS without any HTTPS origin raises ValueError."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    with pytest.raises(ValueError, match="must contain at least one valid HTTPS"):
        get_cors_origins()


def test_cors_origins_prod_no_localhost_defaults(monkeypatch):
    """In production, valid HTTPS origin is returned without injecting localhost defaults."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://smart-app.vercel.app")
    origins = get_cors_origins()
    assert origins == ["https://smart-app.vercel.app"]
    assert "http://localhost:5173" not in origins


def test_cors_origins_wildcard_prohibited(monkeypatch):
    """Verify that wildcard '*' with credentials enabled raises a security ValueError."""
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match=r"Wildcard '\*' origin is prohibited"):
        get_cors_origins()


def test_cors_preflight_options(client):
    """Verify CORS preflight OPTIONS request returns 200 with credentials allowed."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    response = client.options("/api/auth/login", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


# ------------------------------------------------------------------------------
# 2. Cookie Security Attributes Tests
# ------------------------------------------------------------------------------

def test_cookie_settings_dev_default(monkeypatch):
    """Verify default development cookie settings: SameSite=lax, Secure=False."""
    monkeypatch.setenv("SMART_ENV", "development")
    monkeypatch.delenv("COOKIE_SAMESITE", raising=False)
    monkeypatch.delenv("COOKIE_SECURE", raising=False)

    cfg = get_cookie_settings()
    assert cfg["samesite"] == "lax"
    assert cfg["secure"] is False
    assert cfg["httponly"] is True
    assert cfg["path"] == "/"


def test_cookie_settings_prod_default(monkeypatch):
    """Verify default production cookie settings: SameSite=none, Secure=True."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.delenv("COOKIE_SAMESITE", raising=False)
    monkeypatch.delenv("COOKIE_SECURE", raising=False)

    cfg = get_cookie_settings()
    assert cfg["samesite"] == "none"
    assert cfg["secure"] is True
    assert cfg["httponly"] is True
    assert cfg["path"] == "/"


def test_cookie_settings_samesite_none_forces_secure(monkeypatch):
    """Verify that SameSite=none always forces Secure=True to comply with modern browser standards."""
    monkeypatch.setenv("SMART_ENV", "development")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")
    monkeypatch.setenv("COOKIE_SECURE", "false")

    cfg = get_cookie_settings()
    assert cfg["samesite"] == "none"
    assert cfg["secure"] is True


# ------------------------------------------------------------------------------
# 3. Demo Login Configuration Tests
# ------------------------------------------------------------------------------

def test_demo_login_allowed_dev(monkeypatch):
    """Demo login is allowed by default in development."""
    monkeypatch.setenv("SMART_ENV", "development")
    monkeypatch.delenv("ALLOW_DEMO_LOGINS", raising=False)
    assert is_demo_login_allowed() is True


def test_demo_login_allowed_prod_default_disabled(monkeypatch):
    """Demo login is disabled by default in production."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.delenv("ALLOW_DEMO_LOGINS", raising=False)
    assert is_demo_login_allowed() is False


def test_demo_login_allowed_prod_explicitly_enabled(monkeypatch):
    """Demo login can be explicitly permitted in production via ALLOW_DEMO_LOGINS=true."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.setenv("ALLOW_DEMO_LOGINS", "true")
    assert is_demo_login_allowed() is True


def test_demo_login_endpoint_blocked_in_prod_by_default(client, monkeypatch):
    """POST /api/auth/login returns 403 for demo identities when running in production."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.delenv("ALLOW_DEMO_LOGINS", raising=False)

    response = client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    assert response.status_code == 403
    assert "Demo authentication identities are disabled" in response.json()["detail"]


def test_demo_login_endpoint_allowed_in_prod_with_flag(client, monkeypatch):
    """POST /api/auth/login succeeds for demo identities when ALLOW_DEMO_LOGINS=true in prod."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.setenv("ALLOW_DEMO_LOGINS", "true")

    response = client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    assert response.status_code == 200
    assert response.json()["status"] == "authenticated"
    # Check set-cookie header has SameSite=none and Secure in prod
    set_cookie_header = response.headers.get("set-cookie", "")
    assert "smart_session=" in set_cookie_header
    assert "SameSite=none" in set_cookie_header or "samesite=none" in set_cookie_header.lower()
    assert "secure" in set_cookie_header.lower()
    assert "httponly" in set_cookie_header.lower()


def test_institutional_login_never_bypasses_id_token(client, monkeypatch):
    """Institutional non-demo accounts always require a verified Google ID token."""
    from database import provision_user
    provision_user(
        email="student.test@citchennai.net",
        name="CIT Student",
        role="student",
        is_demo=False,
    )

    # Even with ALLOW_DEMO_LOGINS=true, an institutional account must not authenticate with email alone
    monkeypatch.setenv("ALLOW_DEMO_LOGINS", "true")
    response = client.post("/api/auth/login", json={"email": "student.test@citchennai.net"})
    assert response.status_code == 401
    assert "Authentication proof required" in response.json()["detail"]


def test_logout_clears_cookie_attributes(client, monkeypatch):
    """POST /api/auth/logout deletes the smart_session cookie with matching security attributes."""
    monkeypatch.setenv("SMART_ENV", "production")
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    set_cookie_header = response.headers.get("set-cookie", "")
    assert "smart_session=" in set_cookie_header
    assert "samesite=none" in set_cookie_header.lower()
    assert "secure" in set_cookie_header.lower()


# ------------------------------------------------------------------------------
# 4. Google OAuth Configuration Tests
# ------------------------------------------------------------------------------

def test_google_redirect_uri_prod_validation(monkeypatch):
    """build_authorization_url requires GOOGLE_REDIRECT_URI in production."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")

    with pytest.raises(ValueError, match="GOOGLE_REDIRECT_URI is required in production"):
        build_authorization_url(redirect_uri="")


def test_encryption_key_prod_validation(monkeypatch):
    """get_token_encryption_key fails clearly in production if SMART_TOKEN_ENCRYPTION_KEY is unset."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.delenv("SMART_TOKEN_ENCRYPTION_KEY", raising=False)

    with pytest.raises(ValueError, match="SMART_TOKEN_ENCRYPTION_KEY is required in production"):
        get_token_encryption_key()


def test_validate_production_config(monkeypatch):
    """validate_production_config checks for required vars without leaking values."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.delenv("SMART_TOKEN_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/callback")

    with pytest.raises(ValueError) as excinfo:
        validate_production_config()
    err_msg = str(excinfo.value)
    assert "SMART_TOKEN_ENCRYPTION_KEY is required" in err_msg
    assert "CORS_ORIGINS is required" in err_msg
    assert "GOOGLE_REDIRECT_URI must not point to localhost" in err_msg

    # Now provide valid key and origins, but invalid DATABASE_URL
    monkeypatch.setenv("SMART_TOKEN_ENCRYPTION_KEY", "dGVzdC1rZXktdmFsdWUtZm9yLXByb2R1Y3Rpb24=")
    monkeypatch.setenv("CORS_ORIGINS", "https://smart-app.vercel.app")
    monkeypatch.setenv("DATABASE_URL", "mysql://user:pass@host/db")
    with pytest.raises(ValueError) as excinfo2:
        validate_production_config()
    assert "DATABASE_URL must be a valid postgresql://" in str(excinfo2.value)


# ------------------------------------------------------------------------------
# 5. Health Endpoints Tests
# ------------------------------------------------------------------------------

def test_health_endpoints_healthy(client):
    """Health endpoints return 200 and expected status when DB is connected."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"

    resp_live = client.get("/api/health/live")
    assert resp_live.status_code == 200
    assert resp_live.json() == {"status": "alive"}

    resp_ready = client.get("/api/health/ready")
    assert resp_ready.status_code == 200
    assert resp_ready.json() == {"status": "ready", "database": "connected"}


def test_health_endpoints_database_failure(client):
    """Health endpoints return 503 and no leaked paths when DB check fails."""
    with patch("main.get_db_connection", side_effect=Exception("Database lock error at /sensitive/path/smart.db")):
        resp = client.get("/api/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
        assert "/sensitive/path" not in str(data)

        resp_ready = client.get("/api/health/ready")
        assert resp_ready.status_code == 503
        data_ready = resp_ready.json()
        assert data_ready["status"] == "not_ready"
        assert data_ready["database"] == "disconnected"
        assert "/sensitive/path" not in str(data_ready)

        # Liveness endpoint should still report alive
        resp_live = client.get("/api/health/live")
        assert resp_live.status_code == 200
        assert resp_live.json() == {"status": "alive"}
