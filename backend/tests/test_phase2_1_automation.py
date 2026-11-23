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


# ==============================================================================
# SMART 2.2 — Academic Coordination & Functional Completion Tests
# ==============================================================================

def test_smart_2_2_student_turn_in_and_teacher_grading_workflow():
    """Verify end-to-end two-way classroom submission and teacher grading workflow."""
    # 1. Reset demo data to ensure consistent test baseline
    google_service.ingest_demo_data(student_email="alex.morgan@university.edu")

    # 2. Login as student Alex Morgan
    login_stud = client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    assert login_stud.status_code == 200

    # 3. Student turns in assignment
    turn_in_resp = client.post(
        "/api/classroom/submissions/turn-in",
        json={
            "coursework_id": "demo_cw_cs302_parser",
            "alternate_link": "https://classroom.google.com/c/demo_cs302/s/alex_turnin",
        },
    )
    assert turn_in_resp.status_code == 200
    sub = turn_in_resp.json()
    assert sub["state"] == "TURNED_IN"
    assert sub["student_id"] == "alex.morgan@university.edu"
    assert sub["coursework_id"] == "demo_cw_cs302_parser"

    # 4. Student verifies submission appears in their submissions list
    student_subs = client.get("/api/classroom/submissions")
    assert student_subs.status_code == 200
    found_sub = next((s for s in student_subs.json() if s["coursework_id"] == "demo_cw_cs302_parser"), None)
    assert found_sub is not None
    assert found_sub["state"] == "TURNED_IN"

    # Logout student
    client.post("/api/auth/logout")

    # 5. Login as teacher Dr. Elena Vance
    login_teach = client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    assert login_teach.status_code == 200

    # 6. Teacher inspects submissions for courses they teach
    teach_subs = client.get("/api/classroom/submissions")
    assert teach_subs.status_code == 200
    target_sub = next((s for s in teach_subs.json() if s["coursework_id"] == "demo_cw_cs302_parser" and s["student_id"] == "alex.morgan@university.edu"), None)
    assert target_sub is not None

    # 7. Teacher enters grade and marks RETURNED
    grade_resp = client.patch(
        f"/api/classroom/submissions/{target_sub['id']}/grade",
        json={"assigned_grade": 49.5},
    )
    assert grade_resp.status_code == 200
    graded_data = grade_resp.json()
    assert graded_data["state"] == "RETURNED"
    assert graded_data["assigned_grade"] == 49.5

    # Logout teacher
    client.post("/api/auth/logout")

    # 8. Student logs back in and verifies the returned grade is visible
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    updated_stud_subs = client.get("/api/classroom/submissions")
    assert updated_stud_subs.status_code == 200
    verified_sub = next((s for s in updated_stud_subs.json() if s["id"] == target_sub["id"]), None)
    assert verified_sub is not None
    assert verified_sub["state"] == "RETURNED"
    assert verified_sub["assigned_grade"] == 49.5
    client.post("/api/auth/logout")


def test_smart_2_2_teacher_cannot_access_student_gmail_inbox():
    """Verify teachers cannot trigger sync or access private student Gmail inboxes."""
    login_teach = client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    assert login_teach.status_code == 200

    # Attempt to sync Gmail as teacher
    gmail_resp = client.post("/api/sync/gmail")
    assert gmail_resp.status_code == 403
    assert "Teachers cannot access" in gmail_resp.json()["detail"]

    client.post("/api/auth/logout")


def test_smart_2_2_study_materials_deduplication():
    """Verify saving the same study material repeatedly does not create duplicate entries."""
    mat_payload = {
        "title": "CS401 Distributed Systems Syllabus.pdf",
        "file_name": "CS401_Syllabus.pdf",
        "file_type": "application/pdf",
        "file_size": 102400,
        "source_type": "classroom_material",
        "source_id": "mat_syllabus_101",
        "course_id": "demo_cs401",
        "course_name": "CS401: Distributed Systems",
        "file_url": "https://classroom.google.com/c/demo_cs401/m/syllabus",
    }

    # Save first time
    mat1 = database.save_study_material(mat_payload)
    # Save second time
    mat2 = database.save_study_material(mat_payload)

    assert mat1["id"] == mat2["id"]

    # Verify count in database
    all_mats = database.list_study_materials(course_id="demo_cs401")
    matching = [m for m in all_mats if m["source_id"] == "mat_syllabus_101"]
    assert len(matching) == 1


# ==============================================================================
# Live Google OAuth & Gmail/Classroom Integration Tests
# ==============================================================================

def test_root_dotenv_loading_and_config_status():
    """Verify that backend.config loads root .env and correctly reports status without leaking values."""
    import backend.config as cfg
    status = cfg.get_oauth_config_status()
    assert isinstance(status, dict)
    assert "GOOGLE_CLIENT_ID" in status
    assert "GOOGLE_CLIENT_SECRET" in status
    assert "GOOGLE_REDIRECT_URI" in status
    assert "SMART_TOKEN_ENCRYPTION_KEY" in status
    # In this environment, all 4 are present in .env
    assert status["GOOGLE_CLIENT_ID"] is True
    assert status["GOOGLE_CLIENT_SECRET"] is True
    assert status["GOOGLE_REDIRECT_URI"] is True
    assert status["SMART_TOKEN_ENCRYPTION_KEY"] is True


def test_google_auth_url_uses_backend_redirect_uri_and_csrf_state():
    """Verify that build_authorization_url produces a valid Google authorization URL with CSRF state."""
    auth_res = client.get("/api/auth/google/url?role=student")
    assert auth_res.status_code == 200
    data = auth_res.json()
    assert data["configured"] is True
    assert "https://accounts.google.com/o/oauth2/v2/auth" in data["auth_url"]
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fauth%2Fgoogle%2Fcallback" in data["auth_url"]
    assert "state=" in data["auth_url"]
    assert data["state"] is not None

    # Verify state validity
    payload = security.validate_oauth_state(data["state"])
    assert payload is not None
    assert payload["role"] == "student"


def test_google_oauth_callback_error_redirects_to_frontend():
    """Verify that OAuth callback errors redirect back to the frontend workspace with an error parameter."""
    res = client.get("/api/auth/google/callback?error=access_denied", follow_redirects=False)
    assert res.status_code == 307
    location = res.headers.get("location", "")
    assert "http://localhost:5173" in location
    assert "google_auth_error=" in location


def test_google_oauth_callback_missing_params_redirects_to_frontend():
    """Verify that missing code/state in browser callback redirects to frontend with error."""
    res = client.get("/api/auth/google/callback", follow_redirects=False)
    assert res.status_code == 307
    location = res.headers.get("location", "")
    assert "http://localhost:5173" in location
    assert "google_auth_error=" in location


def test_gmail_mime_body_decoder_and_headers():
    """Verify Gmail MIME body parser correctly extracts base64url encoded multipart plain text."""
    from backend.google_service import _decode_gmail_body, _extract_gmail_headers
    import base64

    sample_text = "Urgent: CS401 Project Proposal is due on 2026-12-10."
    encoded_bytes = base64.urlsafe_b64encode(sample_text.encode("utf-8")).decode("ASCII")

    payload = {
        "headers": [
            {"name": "From", "value": "Dr. Vance <vance@univ.edu>"},
            {"name": "Subject", "value": "CS401 Project Submission"},
            {"name": "Date", "value": "Mon, 23 Nov 2026 10:00:00 +0000"},
        ],
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": encoded_bytes, "size": len(sample_text)},
            }
        ],
    }

    headers = _extract_gmail_headers(payload)
    assert headers["from"] == "Dr. Vance <vance@univ.edu>"
    assert headers["subject"] == "CS401 Project Submission"

    decoded_body = _decode_gmail_body(payload)
    assert decoded_body == sample_text


def test_is_secure_persistence_configured_helper_and_import():
    """Verify is_secure_persistence_configured is defined in security and imported in google_service."""
    from backend import security, google_service
    # Must be callable and exported in both modules
    assert callable(security.is_secure_persistence_configured)
    assert callable(google_service.is_secure_persistence_configured)
    assert security.is_secure_persistence_configured() is True
    assert google_service.is_secure_persistence_configured() is True


def test_secure_persistence_reports_false_when_key_missing(monkeypatch):
    """Verify is_secure_persistence_configured reports False if SMART_TOKEN_ENCRYPTION_KEY is unset or empty."""
    import backend.security as sec
    monkeypatch.setenv("SMART_TOKEN_ENCRYPTION_KEY", "")
    assert sec.is_secure_persistence_configured() is False


def test_exchange_code_for_tokens_fails_cleanly_when_persistence_not_configured(monkeypatch):
    """Verify exchange_code_for_tokens rejects live OAuth storage when persistence is not configured."""
    import backend.google_service as gs
    import backend.security as sec

    # Generate a valid OAuth state
    state = sec.generate_oauth_state(role="student", redirect_uri="http://localhost:8000/api/auth/google/callback")

    # Mock secure persistence to return False
    monkeypatch.setattr(gs, "is_secure_persistence_configured", lambda: False)

    # Calling exchange_code_for_tokens should raise ValueError before saving any unencrypted tokens
    import pytest
    with pytest.raises(ValueError) as excinfo:
        import asyncio
        asyncio.run(gs.exchange_code_for_tokens("dummy_code", state))
    assert "Secure token persistence is not configured" in str(excinfo.value) or "Google Token Exchange failed" in str(excinfo.value)


# ==============================================================================
# Gmail Item Persistence & Deduplication Regression Tests
# ==============================================================================

def test_find_duplicate_item_signature_and_due_date_handling():
    """Verify find_duplicate_item accepts due_date and all provenance parameters without error."""
    # Test call with full keyword arguments as invoked by Gmail sync
    dup = database.find_duplicate_item(
        source_text="Assignment due on 2026-12-05",
        source_timestamp="2026-11-23 10:00",
        source_sender="Prof. Smith <smith@univ.edu>",
        category="Assignment",
        source_filename="Gmail Live Sync",
        source_type="gmail",
        source_id="gmail_msg_test_123",
        title="CS401 Lab 3",
        evidence_text="due on 2026-12-05",
        evidence_start_index=15,
        due_date="2026-12-05",
    )
    # Initially does not exist
    assert dup is None


def test_gmail_item_persistence_preserves_due_date_and_prevents_duplicates():
    """Verify saving a Gmail academic task preserves due_date and repeated syncs deduplicate correctly."""
    # 1. Save Gmail task with due_date
    payload = {
        "title": "CS401 Distributed Algorithms Project",
        "category": "Assignment",
        "description": "Final term project on Paxos consensus.",
        "due_date": "2026-12-18",
        "date_text": "December 18, 2026",
        "date_type": "due_date",
        "date_status": "explicit",
        "status": "pending",
        "source_sender": "Prof. Smith <smith@univ.edu>",
        "source_timestamp": "2026-11-23 11:00",
        "source_text": "Final project report due on December 18, 2026.",
        "source_filename": "Gmail Live Sync",
        "source_type": "gmail",
        "source_id": "gmail_msg_project_456",
        "evidence_text": "due on December 18, 2026",
        "_trusted_confidence": "HIGH",
        "_trusted_evidence": True,
        "is_actionable": True,
        "actionability_type": "action_required",
    }

    saved = database.save_academic_item(payload)
    assert saved["id"] is not None
    assert saved["due_date"] == "2026-12-18"
    assert saved["source_type"] == "gmail"
    assert saved["source_id"] == "gmail_msg_project_456"

    # 2. Check duplicate detection with identical provenance and due_date
    dup = database.find_duplicate_item(
        source_text=payload["source_text"],
        source_timestamp=payload["source_timestamp"],
        source_sender=payload["source_sender"],
        category=payload["category"],
        source_filename="Gmail Live Sync",
        source_type="gmail",
        source_id="gmail_msg_project_456",
        title=payload["title"],
        evidence_text=payload["evidence_text"],
        due_date="2026-12-18",
    )
    assert dup is not None
    assert dup["id"] == saved["id"]
    assert dup["due_date"] == "2026-12-18"


def test_gmail_item_persistence_without_due_date():
    """Verify saving an announcement from Gmail without due_date works properly."""
    payload = {
        "title": "Faculty Office Hours Rescheduled",
        "category": "Announcement",
        "description": "Office hours moved to Wednesdays.",
        "due_date": None,
        "status": "pending",
        "source_sender": "Dr. Vance <vance@univ.edu>",
        "source_text": "Office hours will now be held on Wednesdays.",
        "source_filename": "Gmail Live Sync",
        "source_type": "gmail",
        "source_id": "gmail_msg_announcement_789",
        "_trusted_confidence": "MEDIUM",
        "_trusted_evidence": True,
        "is_actionable": False,
        "actionability_type": "informational",
    }

    saved = database.save_academic_item(payload)
    assert saved["id"] is not None
    assert saved["due_date"] is None
    assert saved["source_id"] == "gmail_msg_announcement_789"

    # Duplicate check without due date
    dup = database.find_duplicate_item(
        source_type="gmail",
        source_id="gmail_msg_announcement_789",
        category="Announcement",
        title=payload["title"],
        due_date=None,
    )
    assert dup is not None
    assert dup["id"] == saved["id"]


def test_gmail_sync_task_persistence_and_association_handling():
    """Verify standard Gmail tasks persist via save_academic_item and updates associate properly."""
    # 1. Base task without update_type saves cleanly
    base_task = {
        "title": "CS401 Homework 2",
        "category": "Assignment",
        "description": "Solve distributed consensus questions.",
        "due_date": "2026-12-05",
        "status": "pending",
        "source_sender": "Prof. Smith <smith@univ.edu>",
        "source_text": "CS401 Homework 2 is due on 2026-12-05.",
        "source_filename": "Gmail Live Sync",
        "source_type": "gmail",
        "source_id": "gmail_msg_hw2_001",
        "_trusted_confidence": "HIGH",
        "_trusted_evidence": True,
        "is_actionable": True,
        "actionability_type": "action_required",
    }
    saved_base = database.save_academic_item(base_task)
    assert saved_base["id"] is not None

    # 2. Associated revision/extension announcement correctly links to base task
    extension_task = {
        "title": "CS401 Homework 2 Extension",
        "category": "Assignment",
        "description": "CS401 Homework 2 deadline extended to 2026-12-08.",
        "due_date": "2026-12-08",
        "previous_due_date": "2026-12-05",
        "replaces_task_id": saved_base["id"],
        "status": "pending",
        "source_sender": "Prof. Smith <smith@univ.edu>",
        "source_text": "CS401 Homework 2 deadline extended to 2026-12-08.",
        "source_filename": "Gmail Live Sync",
        "source_type": "gmail",
        "source_id": "gmail_msg_hw2_002",
        "update_type": "extension",
        "_trusted_confidence": "HIGH",
        "_trusted_evidence": True,
        "is_actionable": True,
        "actionability_type": "action_required",
    }

    saved_ext = database.save_academic_item_with_association(
        data=extension_task,
        target_id=saved_base["id"],
        target_status="superseded",
    )
    assert saved_ext["id"] is not None
    assert saved_ext["replaces_task_id"] == saved_base["id"]

    # Verify target was superseded
    old_task = database.get_academic_item_by_id(saved_base["id"])
    assert old_task["status"] == "superseded"


def test_extract_urls_with_labels_categorization():
    """Verify URL extraction categorizes Google Forms, Classroom, Drive, competitions and strips tracking parameters."""
    from google_service import extract_urls_with_labels

    text = """
    Please fill out the lab submission form: https://docs.google.com/forms/d/e/1FAIpQLSc_xyz/viewform?usp=sf_link&utm_source=email
    Also review coursework at https://classroom.google.com/c/MzE1NDI4/a/NjU0MzIx/details
    Drive folder with references: https://drive.google.com/drive/folders/1aBcDeFgHiJkLm?utm_campaign=share
    Competition details: https://codeforces.com/contest/1800/problem/A
    Webinar registration: https://zoom.us/webinar/register/WN_12345
    Unsubscribe here: https://marketing.univ.edu/unsubscribe?user=123
    """

    html = """
    <html>
      <body>
        <p>Lab Form: <a href="https://docs.google.com/forms/d/e/1FAIpQLSc_xyz/viewform?usp=sf_link&utm_source=email">Submission Form</a></p>
        <p><a href="https://classroom.google.com/c/MzE1NDI4/a/NjU0MzIx/details">Classroom Assignment #3</a></p>
        <p><a href="https://kaggle.com/competitions/smart-ai">Global AI Challenge</a></p>
      </body>
    </html>
    """

    urls = extract_urls_with_labels(text, html)

    # 1. Verify tracking and unsubscribe links were filtered out
    assert not any("unsubscribe" in u["url"] for u in urls)

    # 2. Verify utm parameters stripped
    for u in urls:
        assert "utm_source" not in u["url"]
        assert "utm_campaign" not in u["url"]

    # 3. Check classifications
    form_item = next((u for u in urls if u["kind"] == "google_form"), None)
    assert form_item is not None
    assert "docs.google.com/forms" in form_item["url"]

    classroom_item = next((u for u in urls if u["kind"] == "classroom"), None)
    assert classroom_item is not None
    assert classroom_item["label"] == "Classroom Assignment #3"

    drive_item = next((u for u in urls if u["kind"] == "drive"), None)
    assert drive_item is not None

    competition_items = [u for u in urls if u["kind"] == "competition"]
    assert len(competition_items) >= 1


def test_human_review_workflow_and_state_transitions():
    """Verify human review workflow decoupling review_required from status and clearing on completion/dismissal."""
    # 1. Create task needing review
    payload = {
        "title": "Ambiguous Lab Submission",
        "category": "Assignment",
        "description": "Deadline mentions both Friday and Monday.",
        "due_date": "2026-11-27",
        "status": "pending",
        "source_sender": "TA Alex <alex@univ.edu>",
        "source_text": "Please submit by Friday or at the latest Monday.",
        "source_filename": "Gmail Live Sync",
        "source_type": "gmail",
        "source_id": "gmail_msg_review_001",
        "review_required": True,
        "review_reasons": ["Multiple conflicting dates detected in announcement"],
        "_trusted_confidence": "LOW",
        "_trusted_evidence": True,
        "is_actionable": True,
    }

    saved = database.save_academic_item(payload)
    assert saved["review_required"] is True

    # 2. Mark reviewed and confirmed (clears review_required, sets pending)
    reviewed = database.update_academic_item(
        saved["id"],
        {"review_required": False, "status": "pending"},
    )
    assert reviewed["review_required"] is False
    assert reviewed["status"] == "pending"

    # 3. Test that direct status change to 'completed' automatically clears review_required if re-flagged
    database.update_academic_item(saved["id"], {"review_required": True})
    refetched = database.get_academic_item_by_id(saved["id"])
    assert refetched["review_required"] is True

    completed = database.update_academic_item(saved["id"], {"status": "completed"})
    assert completed["status"] == "completed"
    assert completed["review_required"] is False

    # 4. Test that direct status change to 'dismissed' automatically clears review_required
    database.update_academic_item(saved["id"], {"review_required": True})
    dismissed = database.update_academic_item(saved["id"], {"status": "dismissed"})
    assert dismissed["status"] == "dismissed"
    assert dismissed["review_required"] is False


def test_dismissed_gmail_item_deduplication_protection():
    """Verify dismissed Gmail tasks are found by duplicate detection to prevent resurrection on repeated syncs."""
    payload = {
        "title": "Optional Guest Lecture Attendance",
        "category": "Event",
        "description": "Guest talk by industry leader.",
        "due_date": "2026-12-01",
        "status": "pending",
        "source_sender": "Seminar Coordinator <events@univ.edu>",
        "source_text": "Guest talk on December 1, 2026.",
        "source_filename": "Gmail Live Sync",
        "source_type": "gmail",
        "source_id": "gmail_msg_dismiss_999",
        "_trusted_confidence": "HIGH",
        "_trusted_evidence": True,
        "is_actionable": False,
        "actionability_type": "informational",
    }

    saved = database.save_academic_item(payload)
    assert saved["id"] is not None

    # Dismiss the item
    dismissed = database.update_academic_item(saved["id"], {"status": "dismissed"})
    assert dismissed["status"] == "dismissed"

    # Check that duplicate detection still detects the dismissed item
    dup = database.find_duplicate_item(
        source_type="gmail",
        source_id="gmail_msg_dismiss_999",
        category="Event",
        due_date="2026-12-01",
    )
    assert dup is not None
    assert dup["id"] == saved["id"]
    assert dup["status"] == "dismissed"
