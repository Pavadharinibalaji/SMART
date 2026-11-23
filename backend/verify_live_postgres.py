"""Standalone verification script for Live Supabase PostgreSQL database.

Usage:
    py backend/verify_live_postgres.py

Checks:
1. Validates DATABASE_URL is present and starts with postgresql:// or postgres://.
2. Connects using db_engine (psycopg v3 with prepare_threshold=None).
3. Executes schema_postgres.sql and verifies all 24 tables exist.
4. Executes live operational CRUD tests for all SMART modules.
5. Verifies transactions, rollback, duplicate prevention, and generated IDs.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import config  # Loads .env
from db_engine import create_db_connection, get_engine_type
from database import (
    acknowledge_announcement,
    create_course_announcement,
    create_course_poll,
    create_notification,
    create_smart_course,
    create_user_session,
    delete_google_account,
    delete_user_session,
    enroll_student_by_join_code,
    get_google_account,
    get_poll_details,
    get_session_with_user,
    get_unread_notification_count,
    init_db,
    mark_messages_read,
    mark_notification_read,
    provision_user,
    save_academic_item,
    save_course_material,
    save_course_message,
    save_google_account,
    save_opportunity,
    save_tracked_opportunity,
    submit_poll_vote,
)


def run_live_verification() -> bool:
    print("=" * 70)
    print(" SMART 3.0 — LIVE SUPABASE POSTGRESQL VALIDATION")
    print("=" * 70)

    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        print("\n[!] DATABASE_URL is NOT set.")
        print("    Please set DATABASE_URL in your .env file or environment:")
        print("    DATABASE_URL=postgresql://postgres.[REF]:[PASSWORD]@[POOLER-HOST]:6543/postgres\n")
        return False

    if "[" in db_url and "]" in db_url:
        print("\n[!] Error: DATABASE_URL appears to contain placeholder brackets [ ... ].")
        print("    Please replace '[YOUR-DATABASE-PASSWORD]' (including the square brackets '[ ]')")
        print("    with your actual database password in .env.\n")
        return False

    scheme = db_url.split("://")[0] if "://" in db_url else "unknown"
    print(f"\n[+] Configured Engine Type: {get_engine_type()} ({scheme}://...)")

    # Step 1: Connect
    print("\n--- Step 1: Connecting to PostgreSQL ---")
    try:
        conn = create_db_connection()
        cur = conn.execute("SELECT version();")
        pg_ver = cur.fetchone()[0]
        print(f"[*] Connected successfully!")
        print(f"[*] Engine: {pg_ver.split(',')[0]}")
        conn.close()
    except Exception as e:
        print(f"[-] Connection failed: {e}")
        return False

    # Step 2: Initialize 24-table Schema
    print("\n--- Step 2: Initializing Schema & Verifying Tables ---")
    try:
        init_db()
        conn = create_db_connection()
        cur = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
            """
        )
        found_tables = {r[0] for r in cur.fetchall()}
        conn.close()

        expected_24 = [
            "academic_items", "announcement_read_receipts", "classroom_courses",
            "classroom_coursework", "classroom_submissions", "course_announcements",
            "course_invitations", "course_materials", "course_memberships",
            "course_messages", "course_polls", "google_accounts",
            "message_read_receipts", "notifications", "opportunities",
            "poll_options", "poll_votes", "schema_migrations",
            "smart_courses", "student_opportunity_statuses",
            "student_tracked_opportunities", "study_materials",
            "user_sessions", "users"
        ]

        missing = [t for t in expected_24 if t not in found_tables]
        if missing:
            print(f"[-] Missing tables: {missing}")
            return False
        print(f"[*] Verified all {len(expected_24)} tables present in public schema.")
    except Exception as e:
        print(f"[-] Schema initialization failed: {e}")
        return False

    # Step 3: Run Module Operations
    print("\n--- Step 3: Executing Live Module Tests ---")
    results: list[tuple[str, bool, str]] = []

    # 3.1 Authentication & Sessions
    try:
        test_email = f"live.user.{uuid.uuid4().hex[:6]}@citchennai.net"
        user = provision_user(email=test_email, name="Live CIT Student", role="student", is_demo=0)
        assert user.get("id") is not None, "User id must be returned"
        uid = user["id"]

        sid = f"sess_{uuid.uuid4().hex}"
        csrf = f"csrf_{uuid.uuid4().hex}"
        create_user_session(user_id=uid, session_id=sid, csrf_token=csrf, expires_at_iso="2099-12-31T23:59:59Z")
        sess = get_session_with_user(sid)
        assert sess is not None and sess["email"] == test_email
        delete_user_session(sid)
        assert get_session_with_user(sid) is None
        results.append(("User Provisioning & Sessions", True, f"User ID {uid} provisioned & session deleted cleanly"))
    except Exception as e:
        results.append(("User Provisioning & Sessions", False, str(e)))

    # 3.2 Course Creation & Enrollment
    try:
        t_email = f"live.prof.{uuid.uuid4().hex[:6]}@citchennai.net"
        teacher = provision_user(email=t_email, name="Live Teacher", role="teacher")
        c_code = f"CIT-{uuid.uuid4().hex[:4].upper()}"
        course = create_smart_course(teacher_id=teacher["id"], code=c_code, name="Cloud Distributed Systems")
        assert course.get("id") is not None
        cid = course["id"]
        join_code = course["join_code"]

        s_email = f"live.student.{uuid.uuid4().hex[:6]}@citchennai.net"
        student = provision_user(email=s_email, name="Enrolled Student", role="student")
        enroll_res = enroll_student_by_join_code(user_id=student["id"], join_code=join_code)
        assert enroll_res["status"] == "enrolled"
        # Duplicate test
        enroll_dup = enroll_student_by_join_code(user_id=student["id"], join_code=join_code)
        assert enroll_dup["status"] == "already_enrolled"
        results.append(("Course Creation & Enrollment", True, f"Course ID {cid} created, student enrolled via {join_code}"))
    except Exception as e:
        results.append(("Course Creation & Enrollment", False, str(e)))

    # 3.3 Announcements & Acknowledgements
    try:
        ann = create_course_announcement(course_id=cid, teacher_id=teacher["id"], title="Exam Schedule", content="Exam on Friday")
        assert ann.get("id") is not None
        aid = ann["id"]
        ack = acknowledge_announcement(announcement_id=aid, student_id=student["id"])
        assert ack["status"] == "acknowledged"
        results.append(("Announcements & Read Receipts", True, f"Announcement ID {aid} acknowledged by student"))
    except Exception as e:
        results.append(("Announcements & Read Receipts", False, str(e)))

    # 3.4 Polls & Single-Choice Voting
    try:
        poll = create_course_poll(course_id=cid, creator_id=teacher["id"], question="Topic Interest", options=["Cloud", "AI", "Security"])
        assert poll.get("id") is not None
        pid = poll["id"]
        opt_id = poll["options"][0]["id"]
        vote = submit_poll_vote(poll_id=pid, user_id=student["id"], option_id=opt_id)
        assert vote["user_voted"] is True
        # Duplicate vote attempt must raise ValueError
        dup_failed = False
        try:
            submit_poll_vote(poll_id=pid, user_id=student["id"], option_id=poll["options"][1]["id"])
        except ValueError:
            dup_failed = True
        assert dup_failed, "Duplicate vote must be blocked"
        results.append(("Polls & Single-Choice Voting", True, f"Poll ID {pid} voted, duplicate blocked"))
    except Exception as e:
        results.append(("Polls & Single-Choice Voting", False, str(e)))

    # 3.5 Chat Messages & Receipts
    try:
        msg = save_course_message(course_id=cid, sender_id=teacher["id"], content="Welcome to the live test chat room!")
        assert msg.get("id") is not None
        read_cnt = mark_messages_read(course_id=cid, user_id=student["id"])
        assert read_cnt >= 1
        results.append(("Messaging & Read Receipts", True, f"Message ID {msg['id']} created and marked read"))
    except Exception as e:
        results.append(("Messaging & Read Receipts", False, str(e)))

    # 3.6 Notifications
    try:
        notif = create_notification(user_id=student["id"], title="Live Ping", message="Testing notification", notification_type="announcement")
        assert notif.get("id") is not None
        nid = notif["id"]
        unread = get_unread_notification_count(student["id"])
        assert unread >= 1
        mark_notification_read(nid, student["id"])
        results.append(("Notifications Lifecycle", True, f"Notification ID {nid} created and marked read"))
    except Exception as e:
        results.append(("Notifications Lifecycle", False, str(e)))

    # 3.7 Study Material Metadata
    try:
        mat = save_course_material(
            course_id=cid,
            uploaded_by=teacher["id"],
            title="Syllabus PDF",
            original_filename="syllabus.pdf",
            stored_filename="syllabus_uuid.pdf",
            storage_path="/materials/syllabus_uuid.pdf",
            file_extension="pdf",
            mime_type="application/pdf",
            file_size=102400,
        )
        assert mat.get("id") is not None
        results.append(("Study Materials Metadata", True, f"Material ID {mat['id']} persisted"))
    except Exception as e:
        results.append(("Study Materials Metadata", False, str(e)))

    # 3.8 Academic Tasks & Opportunities
    try:
        task = save_academic_item(
            {
                "title": "Lab 1 Submission",
                "category": "Assignment",
                "source_text": "Submit Lab 1 by Dec 1st",
                "due_date": "2026-12-01",
                "status": "pending",
            }
        )
        assert task.get("id") is not None

        opp = save_opportunity(
            {
                "name": "Live Cloud Hackathon",
                "organizer": "Tech Council",
                "registration_deadline": "2026-12-10",
                "category": "Competition",
            }
        )
        assert opp.get("id") is not None

        tracked = save_tracked_opportunity(
            student_id=student["id"],
            title="Live Cloud Hackathon",
            opportunity_id=opp["id"],
            course_id=cid,
            tracking_status="Interested",
        )
        assert tracked.get("id") is not None
        results.append(("Academic Tasks & Opportunities", True, f"Task {task['id']}, Opp {opp['id']}, Tracked {tracked['id']}"))
    except Exception as e:
        results.append(("Academic Tasks & Opportunities", False, str(e)))

    # 3.9 Google Account Token Storage (Upsert)
    try:
        g_email = f"google.{uuid.uuid4().hex[:6]}@citchennai.net"
        acc1 = save_google_account(
            account_data={
                "email": g_email,
                "name": "Google Live User",
                "encrypted_access_token": "enc_token_1",
                "encrypted_refresh_token": "enc_refresh_1",
                "role": "student",
            }
        )
        # Update tokens (verifying ON CONFLICT (email) DO UPDATE SET)
        acc2 = save_google_account(
            account_data={
                "email": g_email,
                "name": "Google Live User Updated",
                "encrypted_access_token": "enc_token_2",
                "encrypted_refresh_token": "enc_refresh_2",
                "role": "student",
            }
        )
        assert acc2["name"] == "Google Live User Updated"
        retrieved = get_google_account(email=g_email)
        assert retrieved["encrypted_access_token"] == "enc_token_2"
        delete_google_account(email=g_email)
        results.append(("Google Account Token Storage", True, f"Account {g_email} upserted and retrieved"))
    except Exception as e:
        results.append(("Google Account Token Storage", False, str(e)))

    # 3.10 Transaction Rollback
    try:
        rollback_marker = f"rollback_{uuid.uuid4().hex[:6]}"
        unique_email = f"{rollback_marker}@citchennai.net"
        conn = create_db_connection()
        error_triggered = False
        try:
            with conn:
                # 1. Execute valid parameterized insert with '?' placeholders
                conn.execute(
                    "INSERT INTO users (email, name, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?);",
                    (unique_email, "Rollback Test User", "student", "now", "now"),
                )
                # 2. Deliberately trigger genuine database constraint violation (duplicate UNIQUE email)
                conn.execute(
                    "INSERT INTO users (email, name, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?);",
                    (unique_email, "Duplicate User", "student", "now", "now"),
                )
        except Exception:
            error_triggered = True

        assert error_triggered, "Database constraint error must be triggered during transaction"
        
        # Verify row does not exist (entire transaction rolled back)
        cur = conn.execute("SELECT id FROM users WHERE email = ?;", (unique_email,))
        row = cur.fetchone()
        conn.close()
        assert row is None, "Rollback failed: row should not exist in database"
        results.append(("Transaction Rollback Verification", True, "Multi-statement rollback verified via constraint violation"))
    except Exception as e:
        results.append(("Transaction Rollback Verification", False, str(e)))

    # Summary
    print("\n" + "=" * 70)
    print(" LIVE POSTGRESQL VALIDATION SUMMARY")
    print("=" * 70)
    all_passed = True
    for name, status, details in results:
        status_str = "[PASS]" if status else "[FAIL]"
        print(f" {status_str} {name:35} : {details}")
        if not status:
            all_passed = False

    print("=" * 70)
    return all_passed


if __name__ == "__main__":
    success = run_live_verification()
    sys.exit(0 if success else 1)
