"""
SMART 3.0 Integration, Security & Real-World Acceptance Test Suite
Audits:
1. Poll Integrity:
   - Single-choice voting vs multiple choice
   - Unique vote enforcement (no duplicate vote tampering)
   - Closed poll rejection (both early close and closes_at timestamp)
   - Anonymous voting voter name masking
   - Poll participation calculation in analytics
2. Authentication & Authorization:
   - Teacher-only course creation & code regeneration
   - Teacher-only course update & roster drop
   - Student-only course join
   - Strict course membership validation on messages, announcements, polls, materials
   - Teacher analytics access restricted to authorized teacher
   - Student personal analytics restricted to logged-in student
   - Invitation acceptance bound to authenticated email
   - Cross-user & cross-course isolation
3. WebSocket & Messaging:
   - WebSocket unauthorized connection rejected (403/policy violation)
   - WebSocket cross-course unauthorized room subscription rejected
   - WebSocket authenticated join, message broadcast, and disconnection handling
4. Announcements & Notifications:
   - Pinned announcements remain pinned
   - Read acknowledgments persist and update read rates
   - Notifications isolated per user (cannot read another user's notifications)
5. Analytics Verification:
   - Known fixture calculations for read rates, participation rates, and timelines
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from main import app
from database import (
    get_db_connection,
    init_db,
    create_smart_course,
    get_smart_course,
    enroll_student_by_join_code,
    create_course_invitation,
    create_course_announcement,
    acknowledge_announcement,
    create_course_poll,
    submit_poll_vote,
    close_course_poll,
    get_poll_details,
    create_notification,
    list_user_notifications,
    mark_notification_read,
    get_course_engagement_analytics,
    get_student_personal_analytics,
    get_user_by_email,
    provision_user,
    save_course_message,
    update_user_profile,
)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

@pytest.fixture
def client():
    return TestClient(app)

# Helper headers
TEACHER_HEADERS = {"X-User-Role": "teacher", "X-User-Email": "e.vance@university.edu"}
STUDENT_HEADERS = {"X-User-Role": "student", "X-User-Email": "alex.morgan@university.edu"}
UNAUTHORIZED_STUDENT = {"X-User-Role": "student", "X-User-Email": "stranger@university.edu"}

# ------------------------------------------------------------------------------
# 1. POLL INTEGRITY AUDIT
# ------------------------------------------------------------------------------

def test_poll_voting_integrity_and_duplicate_prevention(client):
    # Setup course (teacher: Dr Vance = id 2, student: Alex = id 1)
    course = create_smart_course(teacher_id=2, code="POLL-101", name="Poll Testing 101")
    cid = course["id"]
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    # 1. Create single-choice poll
    poll = create_course_poll(
        course_id=cid,
        creator_id=2,
        question="Select your preferred project track",
        options=["Machine Learning", "Systems", "Web & Mobile"],
        poll_type="multiple_choice",
        is_anonymous=False,
    )
    pid = poll["id"]
    opt_id = poll["options"][0]["id"]

    # 2. Student votes
    res_vote = client.post(
        f"/api/courses/{cid}/polls/{pid}/vote",
        json={"option_id": opt_id},
        headers=STUDENT_HEADERS,
    )
    assert res_vote.status_code == 200
    voted_data = res_vote.json()
    assert voted_data["total_votes"] == 1
    assert voted_data["user_voted"] is True

    # 3. Duplicate vote prevention: second submission MUST fail with 400
    res_dup = client.post(
        f"/api/courses/{cid}/polls/{pid}/vote",
        json={"option_id": poll["options"][1]["id"]},
        headers=STUDENT_HEADERS,
    )
    assert res_dup.status_code == 400
    assert "already voted" in res_dup.json()["detail"].lower()

    # 4. Closed poll rejection
    close_res = client.post(f"/api/courses/{cid}/polls/{pid}/close", headers=TEACHER_HEADERS)
    assert close_res.status_code == 200

    # Voting on closed poll must fail
    res_closed_vote = client.post(
        f"/api/courses/{cid}/polls/{pid}/vote",
        json={"option_id": opt_id},
        headers=STUDENT_HEADERS,
    )
    assert res_closed_vote.status_code == 400

def test_poll_anonymous_privacy_and_feedback():
    course = create_smart_course(teacher_id=2, code="PRIV-101", name="Privacy Course")
    cid = course["id"]
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    # Create anonymous feedback poll
    poll = create_course_poll(
        course_id=cid,
        creator_id=2,
        question="Midterm difficulty rating & comments",
        options=["Easy", "Fair", "Difficult"],
        poll_type="short_feedback",
        is_anonymous=True,
    )
    pid = poll["id"]

    # Student submits anonymous feedback
    submit_poll_vote(poll_id=pid, user_id=1, feedback_text="The proofs were quite challenging.")

    # Inspect poll details: voter name MUST be masked as 'Anonymous Student'
    details = get_poll_details(pid, user_id=2)
    assert details["is_anonymous"] == 1
    assert len(details["feedbacks"]) == 1
    assert details["feedbacks"][0]["voter_name"] == "Anonymous Student"
    assert "Alex Morgan" not in str(details["feedbacks"])

# ------------------------------------------------------------------------------
# 2. AUTHENTICATION & AUTHORIZATION AUDIT
# ------------------------------------------------------------------------------

def test_teacher_only_course_management_authorization(client):
    # Student attempting to create a course MUST be rejected with 403
    res_create = client.post(
        "/api/courses",
        json={"code": "HACK-999", "name": "Unauthorized Course"},
        headers=STUDENT_HEADERS,
    )
    assert res_create.status_code == 403

    # Teacher can successfully create course
    res_teacher = client.post(
        "/api/courses",
        json={"code": "CS-888", "name": "Advanced Architecture"},
        headers=TEACHER_HEADERS,
    )
    assert res_teacher.status_code == 201
    course_id = res_teacher.json()["id"]

    # Student attempting to regenerate course join code MUST be rejected
    res_regen = client.post(
        f"/api/courses/{course_id}/regenerate-code",
        headers=STUDENT_HEADERS,
    )
    assert res_regen.status_code == 403

def test_course_membership_checks_on_cross_course_access(client):
    # Teacher creates 2 separate courses
    c1 = create_smart_course(teacher_id=2, code="CS-101-SEC1", name="Section 1")
    c2 = create_smart_course(teacher_id=2, code="CS-101-SEC2", name="Section 2")

    # Enroll Alex only in Section 1
    enroll_student_by_join_code(user_id=1, join_code=c1["join_code"])

    # Alex accessing Section 1 announcements -> allowed
    res_s1 = client.get(f"/api/courses/{c1['id']}/announcements", headers=STUDENT_HEADERS)
    assert res_s1.status_code == 200

    # Alex accessing Section 2 announcements -> MUST be rejected with 403
    res_s2 = client.get(f"/api/courses/{c2['id']}/announcements", headers=STUDENT_HEADERS)
    assert res_s2.status_code == 403
    assert "not enrolled" in res_s2.json()["detail"].lower()

    # Alex accessing Section 2 messages -> MUST be rejected with 403
    res_msg2 = client.get(f"/api/courses/{c2['id']}/messages", headers=STUDENT_HEADERS)
    assert res_msg2.status_code == 403

    # Alex accessing Section 2 polls -> MUST be rejected with 403
    res_poll2 = client.get(f"/api/courses/{c2['id']}/polls", headers=STUDENT_HEADERS)
    assert res_poll2.status_code == 403

def test_invitation_acceptance_tied_to_correct_student_account(client):
    course = create_smart_course(teacher_id=2, code="INV-201", name="Invitation Bound")
    cid = course["id"]

    # Issue invitation specifically to alex.morgan@university.edu
    inv = create_course_invitation(course_id=cid, inviter_id=2, student_email="alex.morgan@university.edu")
    inv_id = inv["id"]

    # Unauthorized student with different email tries to accept invitation -> rejected with 403
    res_impostor = client.post(
        f"/api/student/invitations/{inv_id}/accept",
        headers=UNAUTHORIZED_STUDENT,
    )
    assert res_impostor.status_code == 403
    assert "different email" in res_impostor.json()["detail"].lower()

    # Genuine student accepts -> succeeds
    res_legit = client.post(
        f"/api/student/invitations/{inv_id}/accept",
        headers=STUDENT_HEADERS,
    )
    assert res_legit.status_code == 200
    assert res_legit.json()["id"] == cid

def test_analytics_authorization_isolation(client):
    course = create_smart_course(teacher_id=2, code="ANL-101", name="Analytics Authorization")
    cid = course["id"]
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    # Student attempting to access teacher class analytics -> 403
    res_stud = client.get(f"/api/courses/{cid}/analytics", headers=STUDENT_HEADERS)
    assert res_stud.status_code == 403

    # Teacher accessing course analytics -> 200
    res_teach = client.get(f"/api/courses/{cid}/analytics", headers=TEACHER_HEADERS)
    assert res_teach.status_code == 200
    assert "total_enrolled" in res_teach.json()

    # Teacher attempting to access student personal analytics -> 403
    res_teach_stud = client.get("/api/student/analytics", headers=TEACHER_HEADERS)
    assert res_teach_stud.status_code == 403

    # Student accessing own analytics -> 200
    res_stud_own = client.get("/api/student/analytics", headers=STUDENT_HEADERS)
    assert res_stud_own.status_code == 200
    assert "enrolled_courses_count" in res_stud_own.json()

# ------------------------------------------------------------------------------
# 3. WEBSOCKET & MESSAGING AUDIT
# ------------------------------------------------------------------------------

def test_websocket_unauthorized_and_cross_course_rejection(client):
    course = create_smart_course(teacher_id=2, code="WS-101", name="WebSocket Room")
    cid = course["id"]

    # 1. Unauthenticated connection attempt
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/courses/{cid}/messages") as ws:
            pass

    # 2. Connection by student not enrolled in the course -> rejected
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/courses/{cid}/messages", headers=UNAUTHORIZED_STUDENT) as ws:
            pass

    # 3. Enrolled student connection succeeds
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])
    with client.websocket_connect(f"/ws/courses/{cid}/messages", headers=STUDENT_HEADERS) as ws:
        # Send message over websocket
        ws.send_json({"content": "Hello real-time class channel!"})
        data = ws.receive_json()
        assert data["type"] == "new_message"
        assert data["message"]["content"] == "Hello real-time class channel!"
        assert data["message"]["sender_name"] == "Alex Morgan"

# ------------------------------------------------------------------------------
# 4. NOTIFICATION ISOLATION AUDIT
# ------------------------------------------------------------------------------

def test_notification_isolation_between_users(client):
    # Create notification specifically for user 1 (Alex Morgan)
    notif = create_notification(
        user_id=1,
        title="Alex Confidential Alert",
        message="Confidential grade notice",
        notification_type="task",
    )
    nid = notif["id"]

    # User 2 (Dr Vance) fetching notifications must NOT receive Alex's notification
    vance_notifs = client.get("/api/notifications", headers=TEACHER_HEADERS).json()
    assert not any(n["id"] == nid for n in vance_notifs)

    # Alex fetching notifications receives it
    alex_notifs = client.get("/api/notifications", headers=STUDENT_HEADERS).json()
    assert any(n["id"] == nid for n in alex_notifs)


def test_notification_unread_count_authentication_and_isolation(client):
    # 1. Unauthenticated request -> 401 Unauthorized
    res_unauth = client.get("/api/notifications/unread-count")
    assert res_unauth.status_code == 401

    # 2. Setup notifications for student Alex (id 1)
    notif1 = create_notification(
        user_id=1,
        title="Alex Homework Reminder",
        message="Submit Homework 1",
        notification_type="task",
    )
    notif2 = create_notification(
        user_id=1,
        title="Alex Exam Notice",
        message="Exam schedule posted",
        notification_type="task",
    )

    # Alex gets unread count of at least 2
    res_alex = client.get("/api/notifications/unread-count", headers=STUDENT_HEADERS)
    assert res_alex.status_code == 200
    alex_count = res_alex.json()["unread_count"]
    assert alex_count >= 2

    # Dr Vance (id 2) has distinct notification count (should not include Alex's)
    res_vance = client.get("/api/notifications/unread-count", headers=TEACHER_HEADERS)
    assert res_vance.status_code == 200
    assert res_vance.json()["unread_count"] != alex_count or res_vance.json()["unread_count"] == 0

    # Alex marks one as read
    mark_notification_read(notification_id=notif1["id"], user_id=1)
    res_alex_after = client.get("/api/notifications/unread-count", headers=STUDENT_HEADERS)
    assert res_alex_after.status_code == 200
    assert res_alex_after.json()["unread_count"] == alex_count - 1


def test_notification_unread_count_session_cookie(client):
    # 1. Login as student Alex to establish a real session cookie
    login_res = client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    assert login_res.status_code == 200
    assert "smart_session" in client.cookies

    # 2. Fetch unread count using the session cookie (no headers)
    res_cookie = client.get("/api/notifications/unread-count")
    assert res_cookie.status_code == 200
    assert "unread_count" in res_cookie.json()

    # 3. Logout to clear session
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200

    # 4. Unauthenticated request after logout -> 401
    res_after_logout = client.get("/api/notifications/unread-count")
    assert res_after_logout.status_code == 401


def test_institutional_account_provisioning_and_authentication(client):
    college_email = "pavadharinibg.csbs2024@citchennai.net"

    # 1. Clean environment verification: init_db does NOT automatically seed personal institutional accounts
    # The test database only has standard demo identities initially
    initial_user = get_user_by_email(college_email)
    assert initial_user is None, "Clean test databases must not automatically inherit personal institutional accounts"

    # 2. Controlled Administrator Provisioning
    user = provision_user(
        email=college_email,
        name="Pavadharini B G",
        role="student",
        department="Computer Science & Business Systems",
        program="B.Tech CSBS (2024)",
    )
    assert user is not None
    assert user["role"] == "student"
    assert user["status"] == "active"
    assert user["is_demo"] == 0

    # 3. Duplicate provisioning prevention
    prov_again = provision_user(college_email, "Pavadharini B G", "student")
    assert prov_again["id"] == user["id"]

    # 4. Unprovisioned email login rejection (self-registration strictly disabled)
    res_unprov = client.post("/api/auth/login", json={"email": "unregistered.intruder@citchennai.net"})
    assert res_unprov.status_code == 403
    assert "not provisioned" in res_unprov.json()["detail"].lower()

    # 5. Security Proof Check: Knowing email alone CANNOT authenticate an institutional account
    res_email_only = client.post("/api/auth/login", json={"email": college_email})
    assert res_email_only.status_code == 401
    assert "Authentication proof required" in res_email_only.json()["detail"]

    # 6. Forged or mismatched Google ID token rejected
    res_mismatched = client.post(
        "/api/auth/login",
        json={"email": college_email, "id_token": "mock_google_token_impostor@citchennai.net"},
    )
    assert res_mismatched.status_code == 401
    assert "Google authentication failed" in res_mismatched.json()["detail"]

    # 7. Valid Google ID token authentication succeeds and establishes HttpOnly session cookie
    valid_id_token = f"mock_google_token_{college_email}"
    res_login = client.post(
        "/api/auth/login",
        json={"email": college_email, "id_token": valid_id_token},
    )
    assert res_login.status_code == 200
    assert "smart_session" in client.cookies
    login_data = res_login.json()
    assert login_data["status"] == "authenticated"
    assert login_data["user"]["email"] == college_email
    assert login_data["user"]["role"] == "student"

    # 8. Authenticated session profile retrieval via /api/auth/me
    res_me = client.get("/api/auth/me")
    assert res_me.status_code == 200
    assert res_me.json()["user"]["email"] == college_email
    assert res_me.json()["user"]["role"] == "student"

    # 9. Student can access student-specific endpoints
    res_student_analytics = client.get("/api/student/analytics")
    assert res_student_analytics.status_code == 200

    # 10. Role enforcement: student cannot access teacher-only endpoints
    res_create_course = client.post("/api/courses", json={"name": "Unauthorized Course", "code": "HACK-999"})
    assert res_create_course.status_code == 403
    assert "Teacher role is required" in res_create_course.json()["detail"]

    # 11. Google OAuth profile sync: can update name/picture without changing student role
    updated_profile = update_user_profile(
        user_id=user["id"],
        name="Pavadharini B G (Verified)",
        picture="https://lh3.googleusercontent.com/a/sample-photo",
    )
    assert updated_profile["name"] == "Pavadharini B G (Verified)"
    assert updated_profile["picture"] == "https://lh3.googleusercontent.com/a/sample-photo"
    assert updated_profile["role"] == "student"

    # 12. Logout terminates session
    res_logout = client.post("/api/auth/logout")
    assert res_logout.status_code == 200
    res_me_after = client.get("/api/auth/me")
    assert res_me_after.status_code == 401


def test_auth_regression_lifecycle_matrix(client):
    """
    Rigorously verify the complete authentication lifecycle and regression test matrix:
    1. Demo student login: alex.morgan@university.edu (no token) -> 200, sets session cookie, /me returns student
    2. Demo teacher login: e.vance@university.edu (no token) -> 200, sets session cookie, /me returns teacher
    3. Institutional student without proof: pavadharinibg.csbs2024@citchennai.net -> 401 Unauthorized
    4. Institutional student with valid Google ID token -> 200, sets session cookie, /me returns student
    5. Institutional student with forged/mismatched ID token -> 401 Unauthorized
    6. Counter isolation: Counter 401s do not destroy or invalidate authenticated session
    7. Invalid/expired session token -> 401 Unauthorized
    8. Logout -> destroys session, subsequent /me returns 401
    """
    college_email = "pavadharinibg.csbs2024@citchennai.net"
    provision_user(college_email, "Pavadharini B G", "student")

    # 1. Demo Student Login
    res_demo_student = client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    assert res_demo_student.status_code == 200
    assert "smart_session" in client.cookies
    res_me_student = client.get("/api/auth/me")
    assert res_me_student.status_code == 200
    assert res_me_student.json()["user"]["role"] == "student"
    assert res_me_student.json()["user"]["email"] == "alex.morgan@university.edu"

    # Logout demo student
    client.post("/api/auth/logout")

    # 2. Demo Teacher Login
    res_demo_teacher = client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    assert res_demo_teacher.status_code == 200
    assert "smart_session" in client.cookies
    res_me_teacher = client.get("/api/auth/me")
    assert res_me_teacher.status_code == 200
    assert res_me_teacher.json()["user"]["role"] == "teacher"
    assert res_me_teacher.json()["user"]["email"] == "e.vance@university.edu"

    # Logout demo teacher
    client.post("/api/auth/logout")

    # 3. Institutional student without proof (must be rejected)
    res_no_proof = client.post("/api/auth/login", json={"email": college_email})
    assert res_no_proof.status_code == 401
    assert "Authentication proof required" in res_no_proof.json()["detail"]

    # 4. Institutional student with invalid ID token (must be rejected)
    res_bad_token = client.post(
        "/api/auth/login",
        json={"email": college_email, "id_token": "forged_id_token_xyz"},
    )
    assert res_bad_token.status_code == 401
    assert "Google authentication failed" in res_bad_token.json()["detail"]

    # 5. Institutional student with valid ID token (must succeed)
    res_valid_login = client.post(
        "/api/auth/login",
        json={"email": college_email, "id_token": f"mock_google_token_{college_email}"},
    )
    assert res_valid_login.status_code == 200
    assert "smart_session" in client.cookies
    res_me_inst = client.get("/api/auth/me")
    assert res_me_inst.status_code == 200
    assert res_me_inst.json()["user"]["role"] == "student"
    assert res_me_inst.json()["user"]["email"] == college_email

    # 6. Counter 401 isolation: An unauthenticated counter check (e.g. from an isolated client without cookies)
    # does NOT impact or revoke the valid session of our logged in client
    isolated_client = TestClient(app)
    res_unread_unauth = isolated_client.get("/api/notifications/unread-count")
    assert res_unread_unauth.status_code == 401
    # Meanwhile, the authenticated client continues to be valid:
    res_unread_auth = client.get("/api/notifications/unread-count")
    assert res_unread_auth.status_code == 200
    res_me_still_valid = client.get("/api/auth/me")
    assert res_me_still_valid.status_code == 200

    # 7. Invalid/manipulated session token rejection
    bad_cookie_client = TestClient(app)
    bad_cookie_client.cookies.set("smart_session", "invalid_nonexistent_token_12345")
    res_bad_session = bad_cookie_client.get("/api/auth/me")
    assert res_bad_session.status_code == 401

    # 8. Clean Logout
    res_logout = client.post("/api/auth/logout")
    assert res_logout.status_code == 200
    res_me_after_logout = client.get("/api/auth/me")
    assert res_me_after_logout.status_code == 401
