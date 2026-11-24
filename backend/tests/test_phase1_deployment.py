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


def test_get_frontend_url_development_default(monkeypatch):
    """In development mode, get_frontend_url defaults to localhost:5173."""
    from config import get_frontend_url
    monkeypatch.delenv("SMART_FRONTEND_URL", raising=False)
    monkeypatch.setenv("SMART_ENV", "development")
    assert get_frontend_url() == "http://localhost:5173"


def test_get_frontend_url_production_from_cors_origins(monkeypatch):
    """In production mode, get_frontend_url extracts the primary HTTPS origin from CORS_ORIGINS."""
    from config import get_frontend_url
    monkeypatch.delenv("SMART_FRONTEND_URL", raising=False)
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://smart-academic-lake.vercel.app,https://smart-preview.vercel.app")
    assert get_frontend_url() == "https://smart-academic-lake.vercel.app"


def test_get_frontend_url_explicit_override(monkeypatch):
    """SMART_FRONTEND_URL overrides CORS_ORIGINS in both development and production."""
    from config import get_frontend_url
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://other-domain.com")
    monkeypatch.setenv("SMART_FRONTEND_URL", "https://custom-smart.vercel.app/")
    # Trailing slashes must be stripped
    assert get_frontend_url() == "https://custom-smart.vercel.app"


def test_google_oauth_callback_redirects_to_production_frontend(client, monkeypatch):
    """Google OAuth callback error and missing params redirect to the production frontend URL."""
    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://smart-academic-lake.vercel.app")
    monkeypatch.delenv("SMART_FRONTEND_URL", raising=False)

    # 1. Error callback redirect
    res_err = client.get("/api/auth/google/callback?error=access_denied", follow_redirects=False)
    assert res_err.status_code == 307
    location_err = res_err.headers.get("location", "")
    assert location_err.startswith("https://smart-academic-lake.vercel.app/?google_auth_error=")

    # 2. Missing params callback redirect
    res_miss = client.get("/api/auth/google/callback", follow_redirects=False)
    assert res_miss.status_code == 307
    location_miss = res_miss.headers.get("location", "")
    assert location_miss.startswith("https://smart-academic-lake.vercel.app/?google_auth_error=")


def test_google_oauth_callback_provisions_user_and_restores_session(client, monkeypatch):
    """Successful Google OAuth callback provisions unseeded user, sets session cookie, and restores session via /api/auth/me."""
    from unittest.mock import AsyncMock
    import main

    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://smart-academic-lake.vercel.app")
    monkeypatch.delenv("SMART_FRONTEND_URL", raising=False)

    test_email = "new.google.user@academic.edu"
    mock_account = {
        "email": test_email,
        "name": "New Google Scholar",
        "picture": "https://lh3.googleusercontent.com/photo.jpg",
        "role": "student",
        "is_demo": 0,
    }

    monkeypatch.setattr(main, "exchange_code_for_tokens", AsyncMock(return_value=mock_account))

    # 1. Trigger OAuth callback
    resp = client.get("/api/auth/google/callback?code=mock_code&state=mock_state", follow_redirects=False)
    assert resp.status_code == 307
    location = resp.headers.get("location", "")
    assert location.startswith("https://smart-academic-lake.vercel.app/?google_auth_success=1")
    assert "new.google.user%40academic.edu" in location

    # Verify session cookie was set
    cookie_header = resp.headers.get("set-cookie", "")
    assert "smart_session=" in cookie_header
    assert "samesite=none" in cookie_header.lower()
    assert "secure" in cookie_header.lower()
    assert "httponly" in cookie_header.lower()

    # 2. Extract cookie and verify session restoration at /api/auth/me
    session_val = resp.cookies.get("smart_session")
    assert session_val is not None

    me_resp = client.get("/api/auth/me", cookies={"smart_session": session_val})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["email"] == test_email
    assert me_data["user"]["name"] == "New Google Scholar"
    assert me_data["user"]["role"] == "student"


def test_is_institutional_email_policy(monkeypatch):
    """Institutional access policy permits educational/institution domains and blocks public domains."""
    from config import is_institutional_email

    # Standard institutional domains pass
    assert is_institutional_email("student@citchennai.net") is True
    assert is_institutional_email("prof.ann@citchennai.net") is True
    assert is_institutional_email("alex.morgan@university.edu") is True
    assert is_institutional_email("student.demo@univ.edu") is True
    assert is_institutional_email("researcher@mit.edu") is True
    assert is_institutional_email("scholar@iitd.ac.in") is True
    assert is_institutional_email("learner@sub.citchennai.net") is True

    # Public/consumer mail domains fail
    assert is_institutional_email("spammer@gmail.com") is False
    assert is_institutional_email("intruder@yahoo.com") is False
    assert is_institutional_email("user@hotmail.com") is False
    assert is_institutional_email("attacker@random.org") is False
    assert is_institutional_email("invalid-email") is False

    # Explicit environment domain override
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "custom-college.ac.uk, .partner.org")
    assert is_institutional_email("student@custom-college.ac.uk") is True
    assert is_institutional_email("collaborator@lab.partner.org") is True
    assert is_institutional_email("intruder@gmail.com") is False


def test_google_oauth_callback_rejects_unauthorized_public_email(client, monkeypatch):
    """OAuth callback rejects unprovisioned public Google accounts to prevent unrestricted public account creation."""
    from unittest.mock import AsyncMock
    import main
    from database import get_user_by_email

    monkeypatch.setenv("SMART_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://smart-academic-lake.vercel.app")
    monkeypatch.delenv("SMART_FRONTEND_URL", raising=False)

    unauthorized_email = "random.public.user@gmail.com"
    mock_account = {
        "email": unauthorized_email,
        "name": "Random Public User",
        "picture": "https://lh3.googleusercontent.com/photo.jpg",
        "role": "student",
        "is_demo": 0,
    }

    monkeypatch.setattr(main, "exchange_code_for_tokens", AsyncMock(return_value=mock_account))

    # 1. Callback redirect response
    resp = client.get("/api/auth/google/callback?code=mock_code&state=mock_state", follow_redirects=False)
    assert resp.status_code == 307
    location = resp.headers.get("location", "")
    assert location.startswith("https://smart-academic-lake.vercel.app/?google_auth_error=")
    import urllib.parse
    decoded_loc = urllib.parse.unquote(location)
    assert "not an authorized institutional account" in decoded_loc

    # 2. Verify no session cookie was set
    assert "smart_session" not in resp.cookies

    # 3. Verify user was NOT provisioned in database
    assert get_user_by_email(unauthorized_email) is None


# ------------------------------------------------------------------------------
# 8. Vercel Production CORS Regression Tests
# ------------------------------------------------------------------------------

def test_cors_options_preflight_vercel_origin(client, monkeypatch):
    """OPTIONS preflight from the exact Vercel production origin returns 200 with required CORS headers."""
    vercel_origin = "https://smart-academic-lake.vercel.app"
    headers = {
        "Origin": vercel_origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Content-Type, Authorization, X-User-Email",
    }
    resp = client.options("/api/opportunities", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == vercel_origin
    assert resp.headers.get("access-control-allow-credentials") == "true"
    allowed_methods = resp.headers.get("access-control-allow-methods", "")
    for method in ["GET", "POST", "OPTIONS"]:
        assert method in allowed_methods


def test_cors_get_request_vercel_origin(client):
    """GET request to /api/opportunities from Vercel origin returns 200 with CORS headers."""
    vercel_origin = "https://smart-academic-lake.vercel.app"
    resp = client.get("/api/opportunities", headers={"Origin": vercel_origin})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == vercel_origin
    assert resp.headers.get("access-control-allow-credentials") == "true"
    assert isinstance(resp.json(), list)


def test_cors_authenticated_request_with_credentials(client, monkeypatch):
    """Authenticated request with session cookie from Vercel origin returns 200 and CORS headers."""
    from database import provision_user, create_user_session
    from security import generate_session_id, generate_csrf_token
    from datetime import datetime, timezone, timedelta

    vercel_origin = "https://smart-academic-lake.vercel.app"
    user = provision_user(
        email="cors.student@citchennai.net",
        name="CORS Student",
        role="student",
    )
    session_id = generate_session_id()
    csrf_token = generate_csrf_token()
    expires_dt = datetime.now(timezone.utc) + timedelta(hours=24)
    create_user_session(
        user_id=user["id"],
        session_id=session_id,
        csrf_token=csrf_token,
        expires_at_iso=expires_dt.isoformat(),
    )

    resp = client.get(
        "/api/auth/me",
        headers={"Origin": vercel_origin},
        cookies={"smart_session": session_id},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == vercel_origin
    assert resp.headers.get("access-control-allow-credentials") == "true"
    data = resp.json()
    assert data["authenticated"] is True
    assert data["user"]["email"] == "cors.student@citchennai.net"


def test_cors_rejected_unknown_origin(client):
    """Request from an unauthorized origin does not receive Access-Control-Allow-Origin header."""
    attacker_origin = "https://unauthorized-attacker.com"
    resp = client.get("/api/opportunities", headers={"Origin": attacker_origin})
    assert resp.headers.get("access-control-allow-origin") is None


def test_cors_headers_on_error_response(client):
    """404 and error responses still return Access-Control-Allow-Origin to prevent browser masking as CORS error."""
    vercel_origin = "https://smart-academic-lake.vercel.app"
    resp = client.get("/api/non-existent-endpoint", headers={"Origin": vercel_origin})
    assert resp.status_code == 404
    assert resp.headers.get("access-control-allow-origin") == vercel_origin
    assert resp.headers.get("access-control-allow-credentials") == "true"
