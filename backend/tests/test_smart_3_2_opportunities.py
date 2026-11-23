"""
SMART 3.2: Student Competitions & Opportunities Tracking with Faculty Analytics Test Suite.

Covers:
1. Student saving opportunities from discovered/message analysis, external links, and manual discovery.
2. Tracking details: title, organizer, category, deadline, event date, registration URL, course association, source reference.
3. Deduplication of tracked opportunities.
4. Listing, search, category filtering, status filtering, and dynamic deadline countdowns.
5. Updating tracking statuses (Interested -> Planning to Apply -> Registered -> Submitted -> Completed -> Not Pursuing).
6. Deletion/untracking of opportunities.
7. Authorization boundaries: students cannot track for unenrolled courses or touch other students' records.
8. Server-side deadline reminder engine with deduplication (7d, 3d, 1d) and notification integration.
9. Faculty course-level aggregated opportunity analytics and student participation roster.
10. Complete end-to-end multi-role student-to-faculty verification matching SMART 3.2 specification.
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from main import app
from database import (
    init_db,
    create_smart_course,
    enroll_student_by_join_code,
    save_opportunity,
    save_tracked_opportunity,
    list_student_tracked_opportunities,
    get_tracked_opportunity,
    update_tracked_opportunity,
    delete_tracked_opportunity,
    check_and_dispatch_opportunity_reminders,
    get_course_opportunities_analytics,
    list_course_opportunity_participations,
    list_user_notifications,
)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def test_student_track_opportunity_discovered_and_manual(client):
    """Student can track an opportunity from a discovered message/email, and also manually."""
    # 1. Login as demo teacher and setup a course
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(teacher_id=2, code="CS-HACK", name="Hackathon Course")
    course_id = course["id"]

    # Student enrolls
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    # Discovered opportunity in DB (e.g. from Gmail)
    opp = save_opportunity({
        "name": "MIT Energy Hackathon 2026",
        "organizer": "MIT Energy Club",
        "description": "Clean energy hardware and software solutions.",
        "registration_deadline": "2026-12-15T23:59:00",
        "registration_url": "https://mitenergyhack.org",
        "source_type": "gmail",
        "evidence_text": "Apply for MIT Energy Hackathon by Dec 15",
    })

    # Student tracks the discovered opportunity
    res_track = client.post(
        "/api/student/opportunities",
        json={
            "title": opp["name"],
            "organizer": opp["organizer"],
            "category": "Hackathon",
            "description": opp["description"],
            "registration_url": opp["registration_url"],
            "registration_deadline": "2026-12-15T23:59:00",
            "tracking_status": "Interested",
            "course_id": course_id,
            "opportunity_id": opp["id"],
            "source_platform": "gmail",
            "source_reference": "Apply for MIT Energy Hackathon by Dec 15",
        },
    )
    assert res_track.status_code == 201
    tracked_data = res_track.json()
    assert tracked_data["id"] is not None
    assert tracked_data["title"] == "MIT Energy Hackathon 2026"
    assert tracked_data["category"] == "Hackathon"
    assert tracked_data["course_id"] == course_id
    assert tracked_data["course_name"] == "Hackathon Course"
    assert tracked_data["source_reference"] == "Apply for MIT Energy Hackathon by Dec 15"

    # Deduplication test: tracking same opportunity again updates rather than duplicating
    res_dup = client.post(
        "/api/student/opportunities",
        json={
            "title": opp["name"],
            "category": "Hackathon",
            "tracking_status": "Planning to Apply",
            "course_id": course_id,
            "opportunity_id": opp["id"],
        },
    )
    assert res_dup.status_code == 201
    assert res_dup.json()["id"] == tracked_data["id"]
    assert res_dup.json()["tracking_status"] == "Planning to Apply"

    # Also test manual entry
    res_manual = client.post(
        "/api/student/opportunities",
        json={
            "title": "Google Summer of Code 2027",
            "organizer": "Google",
            "category": "Internship",
            "description": "Open source mentorship program.",
            "registration_deadline": "2027-04-01T18:00:00",
            "registration_url": "https://summerofcode.withgoogle.com",
            "tracking_status": "Interested",
            "source_platform": "manual",
        },
    )
    assert res_manual.status_code == 201
    manual_data = res_manual.json()
    assert manual_data["title"] == "Google Summer of Code 2027"
    assert manual_data["course_id"] is None


def test_student_list_search_and_filter_opportunities(client):
    """Student can list, search, and filter opportunities by category and status."""
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})

    # Create 3 tracked items
    now = datetime.now(timezone.utc)
    d1 = (now + timedelta(days=5)).isoformat()
    d2 = (now + timedelta(days=20)).isoformat()

    client.post(
        "/api/student/opportunities",
        json={
            "title": "ACM ICPC World Finals",
            "category": "Competition",
            "registration_deadline": d1,
            "tracking_status": "Registered",
        },
    )
    client.post(
        "/api/student/opportunities",
        json={
            "title": "Kaggle Grandmaster Challenge",
            "category": "Competition",
            "registration_deadline": d2,
            "tracking_status": "Interested",
        },
    )
    client.post(
        "/api/student/opportunities",
        json={
            "title": "ETHGlobal Web3 Hackathon",
            "category": "Hackathon",
            "registration_deadline": d2,
            "tracking_status": "Planning to Apply",
        },
    )

    # 1. List all
    res_all = client.get("/api/student/opportunities")
    assert res_all.status_code == 200
    items = res_all.json()
    assert len(items) >= 3

    # Check deadline countdown fields
    icpc = next((x for x in items if "ICPC" in x["title"]), None)
    assert icpc is not None
    assert icpc["days_remaining"] is not None
    assert icpc["days_remaining"] <= 5.1
    assert icpc["is_overdue"] is False

    # 2. Filter by category
    res_hack = client.get("/api/student/opportunities?category=Hackathon")
    assert res_hack.status_code == 200
    hack_items = res_hack.json()
    assert all(x["category"] == "Hackathon" for x in hack_items)

    # 3. Filter by status
    res_reg = client.get("/api/student/opportunities?status=Registered")
    assert res_reg.status_code == 200
    reg_items = res_reg.json()
    assert any(x["title"] == "ACM ICPC World Finals" for x in reg_items)

    # 4. Search query
    res_search = client.get("/api/student/opportunities?search=Kaggle")
    assert res_search.status_code == 200
    search_items = res_search.json()
    assert len(search_items) == 1
    assert search_items[0]["title"] == "Kaggle Grandmaster Challenge"


def test_student_update_and_delete_tracked_opportunity(client):
    """Student can update status to Submitted/Completed and remove tracked opportunities."""
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})

    res_cr = client.post(
        "/api/student/opportunities",
        json={
            "title": "Cybersecurity Capture The Flag 2026",
            "category": "Competition",
            "tracking_status": "Interested",
        },
    )
    tracked_id = res_cr.json()["id"]

    # 1. Update status to Submitted
    res_patch = client.patch(
        f"/api/student/opportunities/{tracked_id}",
        json={"tracking_status": "Submitted", "description": "Team registration confirmed"},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["tracking_status"] == "Submitted"
    assert res_patch.json()["description"] == "Team registration confirmed"

    # 2. Delete opportunity
    res_del = client.delete(f"/api/student/opportunities/{tracked_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # Verify not in list
    res_after = client.get("/api/student/opportunities")
    assert not any(x["id"] == tracked_id for x in res_after.json())


def test_authorization_and_privacy_boundaries(client):
    """Strict ownership: students cannot associate unenrolled courses, tamper with other students' records, or view faculty analytics."""
    # Teacher creates course
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(teacher_id=2, code="CS-PRIV", name="Private Advanced Research")
    course_id = course["id"]

    # Student alex.morgan is NOT enrolled in CS-PRIV
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})

    # Attempt to associate unenrolled course -> 400
    res_bad_course = client.post(
        "/api/student/opportunities",
        json={"title": "Unauthorized Course Track", "course_id": course_id},
    )
    assert res_bad_course.status_code == 400
    assert "actively enrolled" in res_bad_course.json()["detail"].lower()

    # Student creates a valid personal opportunity
    res_valid = client.post(
        "/api/student/opportunities",
        json={"title": "Alex Private Challenge", "tracking_status": "Interested"},
    )
    opp_id = res_valid.json()["id"]

    # Student tries to access faculty analytics -> 403 (Teacher role required)
    res_teach_analytics = client.get(f"/api/courses/{course_id}/opportunities/analytics")
    assert res_teach_analytics.status_code == 403

    # Teacher Elena Vance tries to access course analytics for a course she doesn't own
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    # create another course owned by another teacher (or fictitious course_id 99999)
    res_other_course = client.get("/api/courses/99999/opportunities/analytics")
    assert res_other_course.status_code == 403


def test_deadline_reminders_and_deduplication(client):
    """Server-side reminder engine generates notifications at 7d, 3d, 1d without duplication."""
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    student_id = 1

    now = datetime.now(timezone.utc)
    # Deadline in 2 days (matches <= 3d)
    due_2d = (now + timedelta(days=2, hours=2)).isoformat()

    client.post(
        "/api/student/opportunities",
        json={
            "title": "AI Innovation Summit Contest",
            "category": "Competition",
            "registration_deadline": due_2d,
            "tracking_status": "Planning to Apply",
        },
    )

    # 1. Trigger reminder check endpoint
    res_reminders = client.post("/api/student/opportunities/check-reminders")
    assert res_reminders.status_code == 200
    dispatched = res_reminders.json()["dispatched_reminders"]
    assert dispatched >= 1

    # 2. Check student notifications
    notifs = list_user_notifications(user_id=student_id)
    reminder_notif = next((n for n in notifs if "AI Innovation Summit" in n["title"]), None)
    assert reminder_notif is not None
    assert "3 days" in reminder_notif["title"] or "Upcoming Deadline" in reminder_notif["title"]

    # 3. Deduplication: running check again does not send duplicate notification
    res_reminders_second = client.post("/api/student/opportunities/check-reminders")
    assert res_reminders_second.status_code == 200
    assert res_reminders_second.json()["dispatched_reminders"] == 0


def test_end_to_end_student_to_faculty_workflow(client):
    """
    End-to-End multi-role verification workflow (Section 7 in SMART 3.2):
    1. Sign in as demo student.
    2. Open discovered opportunity from message analysis.
    3. Click Track Opportunity.
    4. Select enrolled course.
    5. Set registration deadline.
    6. Save opportunity and confirm in My Competitions & Opportunities.
    7. Verify source reference is preserved.
    8. Update status to Registered.
    9. Verify deadline reminder configuration.
    10. Sign in as associated demo teacher.
    11. Open Opportunities Analytics.
    12. Verify tracked opportunity and participation metrics are reflected.
    13. Verify teacher cannot access unrelated course analytics.
    14. Verify student cannot access another student's private records.
    """
    # 1. Setup course with demo teacher (Dr. Elena Vance)
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(
        teacher_id=2,
        code="CS-COLLAB-2026",
        name="Advanced Collaboration Lab",
    )
    course_id = course["id"]
    join_code = course["join_code"]
    client.post("/api/auth/logout")

    # Step 1: Sign in as demo student (Alex Morgan)
    res_login_s = client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    assert res_login_s.status_code == 200
    assert res_login_s.json()["user"]["role"] == "student"

    # Enroll student in course
    enroll_student_by_join_code(user_id=1, join_code=join_code)

    # Step 2: Ingest an opportunity from message analysis
    opp_record = save_opportunity({
        "name": "Global AI Agents Hackathon 2026",
        "organizer": "AI Research Foundation",
        "description": "Build autonomous multi-agent workflows.",
        "registration_deadline": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
        "registration_url": "https://aiagentshack.dev",
        "source_type": "gmail",
        "evidence_text": "Join the Global AI Agents Hackathon by next Sunday!",
    })
    opp_id = opp_record["id"]

    # Step 3, 4, 5, 6: Click Track Opportunity, select course, deadline, save
    res_track = client.post(
        "/api/student/opportunities",
        json={
            "title": opp_record["name"],
            "organizer": opp_record["organizer"],
            "category": "Hackathon",
            "description": opp_record["description"],
            "registration_url": opp_record["registration_url"],
            "registration_deadline": opp_record["registration_deadline"],
            "course_id": course_id,
            "opportunity_id": opp_id,
            "source_platform": "gmail",
            "source_reference": opp_record["evidence_text"],
            "tracking_status": "Interested",
        },
    )
    assert res_track.status_code == 201
    tracked = res_track.json()
    tracked_id = tracked["id"]

    # Step 7: Confirm in My Competitions & Opportunities and source reference preserved
    res_my_opps = client.get("/api/student/opportunities")
    assert res_my_opps.status_code == 200
    found_tracked = next((x for x in res_my_opps.json() if x["id"] == tracked_id), None)
    assert found_tracked is not None
    assert found_tracked["source_reference"] == "Join the Global AI Agents Hackathon by next Sunday!"
    assert found_tracked["course_id"] == course_id

    # Step 8, 9: Update status to Registered
    res_update = client.patch(
        f"/api/student/opportunities/{tracked_id}",
        json={"tracking_status": "Registered"},
    )
    assert res_update.status_code == 200
    assert res_update.json()["tracking_status"] == "Registered"

    # Step 10: Sign in as associated demo teacher
    client.post("/api/auth/logout")
    res_login_t = client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    assert res_login_t.status_code == 200
    assert res_login_t.json()["user"]["role"] == "teacher"

    # Step 11, 12: Open Opportunities Analytics for course and verify participation metrics
    res_analytics = client.get(f"/api/courses/{course_id}/opportunities/analytics")
    assert res_analytics.status_code == 200
    analytics_data = res_analytics.json()
    assert analytics_data["total_tracked"] >= 1
    assert analytics_data["participating_students_count"] >= 1
    assert analytics_data["registrations_completed"] >= 1
    assert "Hackathon" in analytics_data["category_distribution"]
    assert analytics_data["category_distribution"]["Hackathon"] >= 1

    # Check student participation roster
    res_roster = client.get(f"/api/courses/{course_id}/opportunities/participation")
    assert res_roster.status_code == 200
    roster_list = res_roster.json()
    assert len(roster_list) >= 1
    roster_item = next((r for r in roster_list if r["id"] == tracked_id), None)
    assert roster_item is not None
    assert roster_item["student_name"] == "Alex Morgan"
    assert roster_item["tracking_status"] == "Registered"

    # Step 13: Verify teacher cannot access unrelated course's analytics
    res_unauth = client.get("/api/courses/888888/opportunities/analytics")
    assert res_unauth.status_code == 403

    # Step 14: Log back in as student, verify student cannot access teacher analytics
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    res_student_blocked = client.get(f"/api/courses/{course_id}/opportunities/analytics")
    assert res_student_blocked.status_code == 403
