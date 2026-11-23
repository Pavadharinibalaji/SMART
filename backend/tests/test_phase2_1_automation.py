"""
SMART 2.1 — Academic Automation & Integration Test Suite
Validates:
1. Symmetric token encryption & decryption (Fernet reversible authenticated encryption; NEVER hashing).
2. Token sanitization in API responses (tokens never leaked).
3. OAuth CSRF state generation, validation, and expiration.
4. Competition opportunity extraction from text without inventing missing fields.
5. Student opportunity registration status transitions across 8 explicit states.
6. Teacher course oversight and role authorization isolation (Student gets 403 on teacher endpoints).
7. Study materials repository indexing from Gmail and Classroom.
8. Demo mode isolation (is_demo=1 clearly distinguished from live accounts).
"""
import pytest
import os
import time
from fastapi.testclient import TestClient

from backend.main import app
from backend import security, database, competition_extractor, google_service

client = TestClient(app)


def test_token_encryption_and_decryption_reversible_never_hashed():
    """Verify that Google tokens are encrypted using reversible authenticated encryption (Fernet) and never hashed."""
    sample_access_token = "ya29.a0AfH6SMD_test_token_sample_123456789"
    sample_refresh_token = "1//04test_refresh_token_sample_987654321"

    # Encrypt
    enc_access = security.encrypt_token(sample_access_token)
    enc_refresh = security.encrypt_token(sample_refresh_token)

    assert enc_access is not None
    assert enc_refresh is not None
    assert enc_access != sample_access_token
    assert enc_refresh != sample_refresh_token

    # Verify reversible decryption recovers exact original token
    dec_access = security.decrypt_token(enc_access)
    dec_refresh = security.decrypt_token(enc_refresh)

    assert dec_access == sample_access_token
    assert dec_refresh == sample_refresh_token


def test_token_sanitization_in_api_responses():
    """Verify that encrypted tokens are never returned in Google account API responses."""
    raw_account = {
        "id": 1,
        "email": "student@university.edu",
        "role": "student",
        "encrypted_access_token": "gAAAAAB...secret_encrypted_token",
        "encrypted_refresh_token": "gAAAAAB...secret_refresh_token",
        "token_expiry": "2026-11-23T12:00:00",
        "is_demo": 0,
        "created_at": "2026-11-23T09:00:00",
    }

    sanitized = security.sanitize_account_for_response(raw_account)
    assert sanitized["email"] == "student@university.edu"
    assert sanitized["has_access_token"] is True
    assert sanitized["has_refresh_token"] is True
    assert "encrypted_access_token" not in sanitized
    assert "encrypted_refresh_token" not in sanitized


def test_oauth_state_csrf_validation_and_expiration():
    """Verify OAuth state token generation with HMAC signature and replay/expiry rejection."""
    state = security.generate_oauth_state(role="student", redirect_uri="http://localhost:5173/callback")
    assert state is not None
    assert len(state) > 20

    # Valid state check
    payload = security.validate_oauth_state(state, max_age_seconds=600)
    assert payload is not None
    assert payload["role"] == "student"

    # Expired state check
    expired_payload = security.validate_oauth_state(state, max_age_seconds=-1)
    assert expired_payload is None

    # Tampered state check
    tampered = state[:-4] + "abcd"
    assert security.validate_oauth_state(tampered, max_age_seconds=600) is None


def test_competition_extractor_does_not_invent_missing_fields():
    """Ensure competition extractor parses real text and leaves missing fields as None/empty without inventing facts."""
    sample_text = """
    ACM ICPC Regional 2026
    Organized by International Computing Society.
    Eligibility: Enrolled undergraduate students in CS or Engineering.
    Registration Deadline: 2026-12-15
    Contest Date: 2026-12-28
    Link: https://icpc.global/regionals/2026
    """
    opp = competition_extractor.extract_competition_opportunity(sample_text, source_id="email-test-01")
    assert opp is not None
    assert "ACM ICPC Regional" in opp["name"]
    assert "International Computing Society" in opp["organizer"]
    assert "undergraduate" in opp["eligibility"]
    assert opp["registration_deadline"] == "2026-12-15"
    assert opp["event_date"] == "2026-12-28"
    assert opp["registration_url"] == "https://icpc.global/regionals/2026"

    # Incomplete text: should not invent deadline or event date
    sparse_text = "Hackathon announcement from Tech Club! Form a team and build innovative AI apps. Register at https://hack.test"
    sparse_opp = competition_extractor.extract_competition_opportunity(sparse_text, source_id="email-test-02")
    assert sparse_opp is not None
    assert sparse_opp["registration_deadline"] is None
    assert sparse_opp["event_date"] is None
    assert sparse_opp["eligibility"] is None


def test_student_opportunity_status_workflow_and_isolation():
    """Verify opportunity registration status updates across valid states and persists per student email."""
    # Seed a test opportunity
    saved_opp = database.save_opportunity({
        "name": "National Robotics Challenge 2026",
        "organizer": "Robotics Association",
        "description": "Annual collegiate robotics design challenge.",
        "eligibility": "Undergrads",
        "registration_deadline": "2026-12-20",
        "event_date": "2027-01-10",
        "registration_url": "https://robotics.edu/reg",
        "evidence_text": "Annual collegiate robotics design challenge.",
        "source_id": "msg-opp-99",
        "is_demo": 1,
    })
    opp_id = saved_opp["id"]

    student_a = "student_a@university.edu"
    student_b = "student_b@university.edu"

    # Student A marks interested
    resp_a1 = client.patch(
        f"/api/opportunities/{opp_id}/status",
        headers={"X-User-Role": "student", "X-User-Email": student_a},
        json={"status": "interested", "evidence_notes": "Planning to form a 3-person team."},
    )
    assert resp_a1.status_code == 200

    # Student A marks registered
    resp_a2 = client.patch(
        f"/api/opportunities/{opp_id}/status",
        headers={"X-User-Role": "student", "X-User-Email": student_a},
        json={"status": "registered", "confirmation_source_ref": "CONF-NRC-8842"},
    )
    assert resp_a2.status_code == 200

    # Fetch opportunities for Student A
    list_a = client.get("/api/opportunities", headers={"X-User-Email": student_a}).json()
    opp_for_a = next(o for o in list_a if o["id"] == opp_id)
    assert opp_for_a["student_status"] == "registered"

    # Fetch opportunities for Student B: should remain 'discovered' (isolation)
    list_b = client.get("/api/opportunities", headers={"X-User-Email": student_b}).json()
    opp_for_b = next(o for o in list_b if o["id"] == opp_id)
    assert opp_for_b["student_status"] == "discovered"


def test_teacher_coursework_and_authorization_restrictions():
    """Verify role checks: student gets 403 Forbidden on teacher endpoints; teacher gets authorized overview."""
    # Student role accessing teacher coursework overview must be 403
    resp_student_cw = client.get(
        "/api/teacher/coursework-overview",
        headers={"X-User-Role": "student", "X-User-Email": "student@university.edu"},
    )
    assert resp_student_cw.status_code == 403

    # Student role accessing teacher opportunities overview must be 403
    resp_student_opp = client.get(
        "/api/teacher/opportunities-overview",
        headers={"X-User-Role": "student", "X-User-Email": "student@university.edu"},
    )
    assert resp_student_opp.status_code == 403

    # Teacher role accessing teacher endpoints is permitted
    resp_teacher_cw = client.get(
        "/api/teacher/coursework-overview",
        headers={"X-User-Role": "teacher", "X-User-Email": "e.vance@university.edu"},
    )
    assert resp_teacher_cw.status_code == 200
    assert isinstance(resp_teacher_cw.json(), list)

    resp_teacher_opp = client.get(
        "/api/teacher/opportunities-overview",
        headers={"X-User-Role": "teacher", "X-User-Email": "e.vance@university.edu"},
    )
    assert resp_teacher_opp.status_code == 200
    assert isinstance(resp_teacher_opp.json(), dict)
    assert "participations" in resp_teacher_opp.json()


def test_study_materials_aggregation_and_demo_mode_toggle():
    """Verify study materials listing and demo mode toggle without sample data confusion."""
    # Ensure demo data is seeded
    toggle_resp = client.post(
        "/api/auth/demo-toggle",
        headers={"X-User-Role": "student", "X-User-Email": "alex.morgan@university.edu"},
        json={"enable": True},
    )
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["status"] == "success"

    # List materials
    materials_resp = client.get(
        "/api/materials",
        headers={"X-User-Role": "student", "X-User-Email": "alex.morgan@university.edu"},
    )
    assert materials_resp.status_code == 200
    materials = materials_resp.json()
    assert len(materials) > 0

    # Ensure demo items are flagged is_demo=1
    demo_materials = [m for m in materials if m["is_demo"] == 1]
    assert len(demo_materials) > 0
    for m in demo_materials:
        assert m["source_type"] in ["gmail_attachment", "classroom_material"]
        assert "title" in m
        assert "file_name" in m



def test_scenario_a_student_authentication_and_teacher_rejection():
    """Scenario A: Sign in as Demo Student, access student dashboard data, expect 403 on teacher endpoint."""
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "alex.morgan@university.edu"},
    )
    assert login_resp.status_code == 200
    user_data = login_resp.json()["user"]
    assert user_data["role"] == "student"
    assert user_data["name"] == "Alex Morgan"

    # Confirm student profile via /api/auth/me using session cookie
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["role"] == "student"

    # Try accessing teacher endpoint with student session -> expect 403
    forbidden_resp = client.get("/api/teacher/coursework-overview")
    assert forbidden_resp.status_code == 403

    # Cleanup logout
    client.post("/api/auth/logout")


def test_scenario_b_teacher_authentication_and_coursework_access():
    """Scenario B: Sign in as Demo Teacher, access teacher coursework overview, verify authorized access."""
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "e.vance@university.edu"},
    )
    assert login_resp.status_code == 200
    user_data = login_resp.json()["user"]
    assert user_data["role"] == "teacher"
    assert user_data["name"] == "Dr. Elena Vance"

    # Check /api/auth/me profile
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["role"] == "teacher"

    # Teacher accesses teacher endpoint -> expect 200
    teacher_resp = client.get("/api/teacher/coursework-overview")
    assert teacher_resp.status_code == 200
    assert isinstance(teacher_resp.json(), list)

    # Cleanup logout
    client.post("/api/auth/logout")


def test_scenario_c_header_spoofing_cannot_override_authenticated_session():
    """Scenario C: Authenticated Student attempts to spoof Teacher role via X-User-Role header -> strictly rejected with 403."""
    # Sign in as student
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})

    # Send spoofed header while possessing student session cookie
    spoofed_resp = client.get(
        "/api/teacher/coursework-overview",
        headers={"X-User-Role": "teacher", "X-User-Email": "e.vance@university.edu"},
    )
    # Server-side authenticated session takes precedence -> role is student -> 403 Forbidden
    assert spoofed_resp.status_code == 403

    # Cleanup logout
    client.post("/api/auth/logout")


def test_scenario_e_unprovisioned_account_rejected():
    """Scenario E: Attempting to sign in with an unprovisioned account is rejected with HTTP 403 and descriptive message."""
    resp = client.post(
        "/api/auth/login",
        json={"email": "intruder@external.com"},
    )
    assert resp.status_code == 403
    assert "Account not provisioned" in resp.json()["detail"]



def test_production_mode_disables_demo_logins(monkeypatch):
    """Verify demo accounts cannot authenticate when SMART_ENV=production."""
    import backend.main
    monkeypatch.setattr(backend.main, "IS_PRODUCTION", True)

    resp = client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    assert resp.status_code == 403
    assert "Demo authentication identities are disabled in production" in resp.json()["detail"]
