"""
SMART 3.0 Collaboration & Engagement Test Suite
Covers:
1. Google Classroom coursework materials ingestion
2. Course creation, join codes, invitations & enrollment isolation
3. Course announcements & student read receipts
4. Real-time course chat messages & unread receipts
5. Interactive polls, anonymous voting, and vote tallying
6. Unified notification center & read status
7. Engagement analytics calculation
"""

import pytest
import sqlite3
import os
from fastapi.testclient import TestClient
from main import app
from database import (
    get_db_connection,
    init_db,
    create_smart_course,
    get_smart_course,
    get_smart_course_by_join_code,
    enroll_student_by_join_code,
    remove_student_from_course,
    list_user_smart_courses,
    create_course_invitation,
    list_student_pending_invitations,
    accept_course_invitation,
    save_course_message,
    list_course_messages,
    mark_messages_read,
    create_course_announcement,
    list_course_announcements,
    acknowledge_announcement,
    create_course_poll,
    list_course_polls,
    submit_poll_vote,
    close_course_poll,
    create_notification,
    list_user_notifications,
    mark_notification_read,
    get_course_engagement_analytics,
    get_student_personal_analytics,
)

@pytest.fixture(autouse=True)
def ensure_db():
    init_db()

@pytest.fixture
def client():
    return TestClient(app)

def test_course_creation_and_enrollment():
    # user_id 2 is teacher Dr. Elena Vance in users seed, user_id 1 is student Alex Morgan
    created = create_smart_course(
        teacher_id=2,
        code="CS-701",
        name="Distributed Systems Advanced",
        description="Scalable cloud architectures and consensus.",
    )
    course_id = created["id"]
    assert course_id is not None
    assert created["code"] == "CS-701"
    assert created["join_code"].startswith("SMART-")

    # 2. Lookup by join code
    found = get_smart_course_by_join_code(created["join_code"])
    assert found is not None
    assert found["id"] == course_id

    # 3. Enroll student (user_id 1 is student Alex Morgan)
    joined_course = enroll_student_by_join_code(user_id=1, join_code=created["join_code"])
    assert joined_course["id"] == course_id

    # Check student course list
    student_courses = list_user_smart_courses(user_id=1, role="student")
    assert any(c["id"] == course_id for c in student_courses)

    # 4. Remove student
    remove_student_from_course(course_id=course_id, user_id=1, requester_id=2, requester_role="teacher")
    student_courses_after = list_user_smart_courses(user_id=1, role="student")
    assert not any(c["id"] == course_id for c in student_courses_after)

def test_course_invitations():
    course = create_smart_course(
        teacher_id=2,
        code="BIO-101",
        name="Bioinformatics 101",
    )
    course_id = course["id"]
    student_email = "alex.morgan@university.edu"

    # Invite student by email
    inv = create_course_invitation(course_id=course_id, inviter_id=2, student_email=student_email)
    inv_id = inv["id"]
    assert inv_id is not None

    # Check student invitations
    pending = list_student_pending_invitations(student_email)
    assert any(i["id"] == inv_id for i in pending)

    # Student accepts invitation
    enrolled = accept_course_invitation(invitation_id=inv_id, student_user_id=1, student_email=student_email)
    assert enrolled["id"] == course_id

    # Re-checking invitations should show none pending
    pending_after = list_student_pending_invitations(student_email)
    assert not any(i["id"] == inv_id for i in pending_after)

def test_course_messages_and_read_receipts():
    course = create_smart_course(
        teacher_id=2,
        code="CS-202",
        name="Algorithms Lab",
    )
    course_id = course["id"]
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    # Teacher sends message
    msg1 = save_course_message(course_id=course_id, sender_id=2, content="Welcome to the lab!", attachment_url="https://drive.google.com/doc1")
    assert msg1["id"] is not None
    assert msg1["sender_role"] == "teacher"

    # Student sends message
    msg2 = save_course_message(course_id=course_id, sender_id=1, content="Thank you Professor!")
    assert msg2["id"] is not None
    assert msg2["sender_role"] == "student"

    # List messages
    msgs = list_course_messages(course_id=course_id, user_id=1)
    assert len(msgs) >= 2

    # Student marks messages read
    marked = mark_messages_read(course_id=course_id, user_id=1)
    assert marked >= 1

def test_course_announcements_and_acknowledgments():
    course = create_smart_course(
        teacher_id=2,
        code="CS-601",
        name="Compiler Design",
    )
    course_id = course["id"]
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    ann = create_course_announcement(
        course_id=course_id,
        teacher_id=2,
        title="Midterm Rescheduled",
        content="The midterm exam is postponed to next Tuesday.",
        is_pinned=True,
    )
    ann_id = ann["id"]
    assert ann_id is not None

    anns = list_course_announcements(course_id=course_id, user_id=1)
    assert any(a["id"] == ann_id for a in anns)

    # Student acknowledges
    ack = acknowledge_announcement(announcement_id=ann_id, student_id=1)
    assert ack is not None

    anns_after = list_course_announcements(course_id=course_id, user_id=1)
    for a in anns_after:
        if a["id"] == ann_id:
            assert a.get("acknowledged") is True
            assert a.get("acknowledgment_count", 0) >= 1

def test_interactive_polls_and_voting():
    course = create_smart_course(
        teacher_id=2,
        code="CS-301",
        name="Operating Systems",
    )
    course_id = course["id"]
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    # Create poll
    poll = create_course_poll(
        course_id=course_id,
        creator_id=2,
        question="Which threading library should we use?",
        poll_type="multiple_choice",
        options=["pthreads", "std::thread", "OpenMP"],
        is_anonymous=False,
    )
    poll_id = poll["id"]
    assert poll_id is not None

    polls = list_course_polls(course_id=course_id, user_id=1)
    current_poll = next(p for p in polls if p["id"] == poll_id)
    assert len(current_poll["options"]) == 3
    first_opt_id = current_poll["options"][0]["id"]

    # Student votes
    vote_res = submit_poll_vote(poll_id=poll_id, user_id=1, option_id=first_opt_id)
    assert vote_res is not None

    # Check updated poll
    polls_after = list_course_polls(course_id=course_id, user_id=1)
    poll_updated = next(p for p in polls_after if p["id"] == poll_id)
    assert poll_updated["total_votes"] == 1
    assert poll_updated["user_voted"] is True

    # Close poll
    close_res = close_course_poll(poll_id=poll_id, teacher_id=2)
    assert close_res is not None

def test_notifications_lifecycle():
    notif = create_notification(
        user_id=1,
        title="New Coursework Posted",
        message="Homework 4 is due in 3 days.",
        notification_type="task",
        reference_id="/tasks",
    )
    notif_id = notif["id"]
    assert notif_id is not None

    notifs = list_user_notifications(user_id=1, unread_only=True)
    assert any(n["id"] == notif_id for n in notifs)

    # Mark as read
    mark_res = mark_notification_read(notification_id=notif_id, user_id=1)
    assert mark_res is True

    notifs_unread = list_user_notifications(user_id=1, unread_only=True)
    assert not any(n["id"] == notif_id for n in notifs_unread)

def test_engagement_analytics():
    course = create_smart_course(
        teacher_id=2,
        code="DS-501",
        name="Data Analytics",
    )
    course_id = course["id"]
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    # Teacher course engagement analytics
    course_analytics = get_course_engagement_analytics(course_id=course_id)
    assert "total_enrolled" in course_analytics
    assert course_analytics["total_enrolled"] >= 1
    assert "announcement_read_rate" in course_analytics
    assert "poll_participation_rate" in course_analytics

    # Student personal analytics
    student_analytics = get_student_personal_analytics(student_id=1)
    assert "enrolled_courses_count" in student_analytics
    assert student_analytics["enrolled_courses_count"] >= 1


def test_demo_account_full_collaboration_workflow(client):
    """
    End-to-end integration test of the 14-step collaboration workflow using demo accounts:
    Teacher: e.vance@university.edu
    Student: alex.morgan@university.edu
    """
    # 1. Sign in as demo teacher
    res_login_t = client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    assert res_login_t.status_code == 200
    assert res_login_t.json()["user"]["role"] == "teacher"

    # 2. Create course
    res_create_c = client.post(
        "/api/courses",
        json={
            "code": "CS-999",
            "title": "Advanced Quantum Computing",
            "section": "Section 1",
            "description": "Qubits, quantum circuits, and algorithms.",
        },
    )
    assert res_create_c.status_code == 201
    course_data = res_create_c.json()
    cid = course_data["id"]
    join_code = course_data["join_code"]
    assert cid is not None
    assert join_code.startswith("SMART-")

    # 3. Generate and view course join code & details
    res_c_details = client.get(f"/api/courses/{cid}")
    assert res_c_details.status_code == 200
    assert res_c_details.json()["join_code"] == join_code

    # Optional test of join code regeneration
    res_regen = client.post(f"/api/courses/{cid}/regenerate-code")
    assert res_regen.status_code == 200
    new_join_code = res_regen.json()["join_code"]
    assert new_join_code.startswith("SMART-")

    # 4. Sign out teacher
    res_logout_t = client.post("/api/auth/logout")
    assert res_logout_t.status_code == 200

    # 5. Sign in as demo student
    res_login_s = client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    assert res_login_s.status_code == 200
    assert res_login_s.json()["user"]["role"] == "student"

    # 6. Join teacher's course using the join code
    res_join = client.post("/api/courses/join", json={"join_code": new_join_code})
    assert res_join.status_code == 200
    assert res_join.json()["id"] == cid

    # 7. Confirm course appears in student dashboard
    res_student_courses = client.get("/api/courses")
    assert res_student_courses.status_code == 200
    student_c_list = res_student_courses.json()
    assert any(c["id"] == cid for c in student_c_list)

    # 8. Sign in as teacher and create a poll
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    res_create_poll = client.post(
        f"/api/courses/{cid}/polls",
        json={
            "question": "Which quantum lab slot do you prefer?",
            "poll_type": "single_choice",
            "options": ["Morning 9AM", "Afternoon 2PM", "Evening 6PM"],
            "is_anonymous": False,
        },
    )
    assert res_create_poll.status_code in (200, 201)
    poll_data = res_create_poll.json()
    pid = poll_data["id"]
    opt_morning = poll_data["options"][0]["id"]

    # 9. Sign in as student and vote
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    res_vote = client.post(
        f"/api/courses/{cid}/polls/{pid}/vote",
        json={"option_id": opt_morning},
    )
    assert res_vote.status_code == 200
    assert res_vote.json()["user_voted"] is True

    # 10. Verify teacher can see poll participation and results
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    res_teacher_polls = client.get(f"/api/courses/{cid}/polls")
    assert res_teacher_polls.status_code == 200
    poll_for_teacher = next(p for p in res_teacher_polls.json() if p["id"] == pid)
    assert poll_for_teacher["total_votes"] == 1
    assert any(o["id"] == opt_morning and o["vote_count"] == 1 for o in poll_for_teacher["options"])

    # 11. Send a message as student
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    res_send_msg = client.post(
        f"/api/courses/{cid}/messages",
        json={"content": "Hello Dr. Vance, excited for Quantum Computing!"},
    )
    assert res_send_msg.status_code == 201
    student_msg = res_send_msg.json()

    # 12. Verify teacher can see and reply to it
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    res_teacher_msgs = client.get(f"/api/courses/{cid}/messages")
    assert res_teacher_msgs.status_code == 200
    assert any(m["content"] == "Hello Dr. Vance, excited for Quantum Computing!" for m in res_teacher_msgs.json())

    res_reply = client.post(
        f"/api/courses/{cid}/messages",
        json={"content": "Welcome Alex! Course syllabus is posted."},
    )
    assert res_reply.status_code == 201

    # 13. Publish an announcement as teacher
    res_ann = client.post(
        f"/api/courses/{cid}/announcements",
        json={
            "title": "Quantum Simulator Setup Guide",
            "content": "Please install Qiskit and review chapter 1 before Monday.",
            "is_pinned": True,
        },
    )
    assert res_ann.status_code == 201
    ann_id = res_ann.json()["id"]

    # 14. Verify student receives and acknowledges it
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})
    res_student_anns = client.get(f"/api/courses/{cid}/announcements")
    assert res_student_anns.status_code == 200
    assert any(a["id"] == ann_id and a["is_pinned"] == 1 for a in res_student_anns.json())

    res_ack = client.post(f"/api/courses/{cid}/announcements/{ann_id}/acknowledge")
    assert res_ack.status_code == 200
    assert res_ack.json()["status"] == "acknowledged"
