"""Tests for SMART Phase 2B: Dual-Database Engine and SQL Compatibility Layer.

Covers:
1. SQL-aware lexical scanner (? -> %s conversion preserving quotes and comments).
2. Parameter count validation.
3. Target-specific INSERT OR IGNORE translation.
4. Selective RETURNING id injection and cursor.lastrowid emulation.
5. PostgresRowWrapper interface parity (row['col'], row[0], dict(row)).
6. Engine selection and invalid DATABASE_URL validation.
7. Complete 24-table PostgreSQL schema coverage in schema_postgres.sql.
8. Live PostgreSQL integration tests (executed if DATABASE_URL is configured, otherwise clearly skipped).
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import pytest

import config  # Ensures root .env is loaded before checking environment
from db_engine import (
    CONFLICT_TARGETS,
    LASTROWID_TABLES,
    PostgresRowWrapper,
    convert_sqlite_to_postgres_sql,
    get_engine_type,
)


def is_live_postgres_configured() -> bool:
    """Safely check if valid, non-placeholder DATABASE_URL is configured."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not (url.startswith("postgresql://") or url.startswith("postgres://")):
        return False
    # Prohibit unpopulated template placeholders like [YOUR-DATABASE-PASSWORD]
    if "[" in url or "]" in url or "YOUR-" in url.upper():
        return False
    return True


HAS_LIVE_POSTGRES = is_live_postgres_configured()


# ==============================================================================
# 1. SQL-Aware Lexical Scanner & Query Converter Unit Tests
# ==============================================================================

def test_scanner_basic_placeholder_conversion():
    """Verify ? is converted to %s in simple queries."""
    sql = "SELECT id, email FROM users WHERE role = ? AND status = ?;"
    conv_sql, returns_id = convert_sqlite_to_postgres_sql(sql, ("student", "active"))
    assert conv_sql == "SELECT id, email FROM users WHERE role = %s AND status = %s;"
    assert returns_id is False


def test_scanner_preserves_question_mark_in_single_quotes():
    """Literal ? inside single-quoted string literals must NOT be converted."""
    sql = "SELECT * FROM course_polls WHERE question = 'Are you ready for Exam 1?' AND id = ?;"
    conv_sql, returns_id = convert_sqlite_to_postgres_sql(sql, (42,))
    assert conv_sql == "SELECT * FROM course_polls WHERE question = 'Are you ready for Exam 1?' AND id = %s;"
    assert returns_id is False


def test_scanner_preserves_escaped_quotes_and_question_marks():
    """Literal ? inside single quotes with escaped quotes (''') must remain untouched."""
    sql = "INSERT INTO academic_items (title, source_text) VALUES (?, 'Professor''s note: due tomorrow? yes.');"
    conv_sql, returns_id = convert_sqlite_to_postgres_sql(sql, ("Assignment 1",))
    assert conv_sql == "INSERT INTO academic_items (title, source_text) VALUES (%s, 'Professor''s note: due tomorrow? yes.') RETURNING id;"
    assert returns_id is True


def test_scanner_preserves_question_marks_in_comments():
    """Question marks inside SQL line comments and block comments must NOT be converted."""
    sql = """
    -- Is this query needed? Yes
    SELECT * FROM notifications /* Did user read? */ WHERE user_id = ? AND is_read = ?;
    """
    conv_sql, _ = convert_sqlite_to_postgres_sql(sql, (10, 0))
    assert "%s" in conv_sql
    assert "Is this query needed?" in conv_sql
    assert "Did user read?" in conv_sql
    assert conv_sql.count("%s") == 2


def test_scanner_validates_parameter_count():
    """Parameter count mismatch must raise ValueError before query execution."""
    sql = "SELECT * FROM users WHERE email = ? AND role = ?;"
    with pytest.raises(ValueError, match="SQL parameter count mismatch"):
        convert_sqlite_to_postgres_sql(sql, ("student@univ.edu",))

    with pytest.raises(ValueError, match="SQL parameter count mismatch"):
        convert_sqlite_to_postgres_sql(sql, ("student@univ.edu", "student", "extra_param"))


# ==============================================================================
# 2. INSERT OR IGNORE Translation Tests
# ==============================================================================

def test_insert_or_ignore_announcement_read_receipts():
    """Translate INSERT OR IGNORE for announcement_read_receipts with conflict target."""
    sql = "INSERT OR IGNORE INTO announcement_read_receipts (announcement_id, student_id, acknowledged_at) VALUES (?, ?, ?);"
    conv_sql, _ = convert_sqlite_to_postgres_sql(sql, (1, 2, "2026-11-24T00:00:00Z"))
    assert conv_sql.startswith("INSERT INTO announcement_read_receipts")
    assert "ON CONFLICT (announcement_id, student_id) DO NOTHING;" in conv_sql
    assert conv_sql.count("%s") == 3


def test_insert_or_ignore_course_memberships():
    """Translate INSERT OR IGNORE for course_memberships with (course_id, user_id) target."""
    sql = "INSERT OR IGNORE INTO course_memberships (course_id, user_id, role, status, joined_at) VALUES (?, ?, ?, ?, ?);"
    conv_sql, _ = convert_sqlite_to_postgres_sql(sql, (5, 10, "student", "enrolled", "now"))
    assert "ON CONFLICT (course_id, user_id) DO NOTHING;" in conv_sql


def test_insert_or_ignore_message_read_receipts():
    """Translate INSERT OR IGNORE for message_read_receipts with (message_id, user_id) target."""
    sql = "INSERT OR IGNORE INTO message_read_receipts (message_id, user_id, read_at) VALUES (?, ?, ?);"
    conv_sql, _ = convert_sqlite_to_postgres_sql(sql, (100, 20, "now"))
    assert "ON CONFLICT (message_id, user_id) DO NOTHING;" in conv_sql


def test_insert_or_ignore_unmapped_table():
    """Unmapped tables fall back safely to generic ON CONFLICT DO NOTHING."""
    sql = "INSERT OR IGNORE INTO unknown_audit_log (event_id, payload) VALUES (?, ?);"
    conv_sql, _ = convert_sqlite_to_postgres_sql(sql, (1, "data"))
    assert "ON CONFLICT DO NOTHING;" in conv_sql


# ==============================================================================
# 3. Selective RETURNING id & Generated ID Emulation Tests
# ==============================================================================

def test_returning_id_injected_for_lastrowid_tables():
    """All 12 lastrowid tables must have RETURNING id appended."""
    for table in LASTROWID_TABLES:
        sql = f"INSERT INTO {table} (created_at) VALUES (?);"
        conv_sql, returns_id = convert_sqlite_to_postgres_sql(sql, ("now",))
        assert returns_id is True, f"Table {table} must flag returns_id=True"
        assert "RETURNING id;" in conv_sql, f"Table {table} must have RETURNING id appended"


def test_returning_id_not_injected_for_non_lastrowid_tables():
    """Tables with text IDs or non-lastrowid inserts must NOT have RETURNING id appended."""
    non_lastrowid_tables = [
        "classroom_courses",
        "classroom_coursework",
        "classroom_submissions",
        "user_sessions",
        "schema_migrations",
    ]
    for table in non_lastrowid_tables:
        sql = f"INSERT INTO {table} (id, created_at) VALUES (?, ?);"
        conv_sql, returns_id = convert_sqlite_to_postgres_sql(sql, ("text_id_1", "now"))
        assert returns_id is False, f"Table {table} must NOT flag returns_id=True"
        assert "RETURNING" not in conv_sql, f"Table {table} must NOT have RETURNING appended"


def test_returning_id_not_duplicated_if_already_present():
    """If query already specifies a RETURNING clause, do not append another."""
    sql = "INSERT INTO academic_items (title) VALUES (?) RETURNING id, title;"
    conv_sql, returns_id = convert_sqlite_to_postgres_sql(sql, ("Test Task",))
    assert conv_sql.count("RETURNING") == 1
    assert returns_id is False


def test_returning_keyword_in_string_literal_does_not_block_returning_id():
    """The word 'returning' inside a string literal must not prevent appending RETURNING id."""
    sql = "INSERT INTO academic_items (title) VALUES ('Return book: returning to library');"
    conv_sql, returns_id = convert_sqlite_to_postgres_sql(sql)
    assert returns_id is True
    assert "RETURNING id" in conv_sql


def test_insert_with_leading_comments_handled():
    """Queries with leading SQL comments must still have INSERT OR IGNORE and RETURNING id handled."""
    sql = """
    -- Audit note
    INSERT OR IGNORE INTO announcement_read_receipts (announcement_id, student_id, acknowledged_at)
    VALUES (?, ?, ?);
    """
    conv_sql, _ = convert_sqlite_to_postgres_sql(sql, (1, 2, "now"))
    assert "ON CONFLICT (announcement_id, student_id) DO NOTHING" in conv_sql


# ==============================================================================
# 4. PostgresRowWrapper Interface Parity Tests
# ==============================================================================

def test_row_wrapper_indexing_and_dictionary():
    """PostgresRowWrapper must support integer indexing, key lookup, dict(r), and len."""
    col_names = ["id", "title", "confidence", "review_required"]
    row_data = [42, "Assignment 1", "HIGH", 0]

    row = PostgresRowWrapper(row_data, col_names)

    # 1. Integer indexing
    assert row[0] == 42
    assert row[1] == "Assignment 1"
    assert row[2] == "HIGH"
    assert row[3] == 0

    # 2. Key-based access
    assert row["id"] == 42
    assert row["title"] == "Assignment 1"
    assert row["confidence"] == "HIGH"
    assert row["review_required"] == 0

    # 3. Case-insensitivity
    assert row["ID"] == 42
    assert row["Title"] == "Assignment 1"

    # 4. Dictionary conversion
    as_dict = dict(row)
    assert as_dict == {
        "id": 42,
        "title": "Assignment 1",
        "confidence": "HIGH",
        "review_required": 0,
    }

    # 5. Dict methods
    assert "title" in row
    assert "non_existent" not in row
    assert row.get("title") == "Assignment 1"
    assert row.get("non_existent", "default_val") == "default_val"
    assert len(row) == 4
    assert list(row.keys()) == col_names


# ==============================================================================
# 5. Engine Selection & URL Validation Tests
# ==============================================================================

def test_engine_type_sqlite_default(monkeypatch):
    """When DATABASE_URL is unset or empty, SQLite engine is selected."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_engine_type() == "sqlite"

    monkeypatch.setenv("DATABASE_URL", "   ")
    assert get_engine_type() == "sqlite"


def test_engine_type_postgresql_detection(monkeypatch):
    """When DATABASE_URL starts with postgresql:// or postgres://, PostgreSQL is selected."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/dbname")
    assert get_engine_type() == "postgresql"

    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/dbname")
    assert get_engine_type() == "postgresql"


def test_engine_type_invalid_scheme_fails_clearly(monkeypatch):
    """Invalid DATABASE_URL schemes must fail clearly rather than silently falling back."""
    monkeypatch.setenv("DATABASE_URL", "mysql://root@localhost/smart")
    with pytest.raises(ValueError, match="Unsupported DATABASE_URL configuration"):
        get_engine_type()


# ==============================================================================
# 6. PostgreSQL Schema Coverage (schema_postgres.sql) Verification
# ==============================================================================

def test_schema_postgres_contains_all_24_tables():
    """Verify schema_postgres.sql contains valid definitions for all 24 SMART tables."""
    schema_path = Path(__file__).resolve().parent.parent / "schema_postgres.sql"
    assert schema_path.exists(), "schema_postgres.sql must exist"

    with open(schema_path, "r", encoding="utf-8") as f:
        content = f.read()

    expected_tables = [
        "users",
        "user_sessions",
        "smart_courses",
        "course_memberships",
        "course_invitations",
        "course_announcements",
        "announcement_read_receipts",
        "course_messages",
        "message_read_receipts",
        "course_polls",
        "poll_options",
        "poll_votes",
        "notifications",
        "course_materials",
        "academic_items",
        "opportunities",
        "student_opportunity_statuses",
        "student_tracked_opportunities",
        "google_accounts",
        "classroom_courses",
        "classroom_coursework",
        "classroom_submissions",
        "study_materials",
        "schema_migrations",
    ]

    for table in expected_tables:
        pattern = rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table}\b"
        assert re.search(pattern, content, re.IGNORECASE), f"Table {table} must be defined in schema_postgres.sql"


# ==============================================================================
# 7. Live PostgreSQL Integration Tests (Conditional)
# ==============================================================================

@pytest.mark.skipif(not HAS_LIVE_POSTGRES, reason="PostgreSQL instance not configured in environment via DATABASE_URL; skipping live PostgreSQL integration tests")
def test_live_postgres_connection_and_table_lifecycle():
    """Live test 1: Basic connection and row access."""
    from db_engine import create_db_connection

    conn = create_db_connection()
    try:
        cur = conn.execute("SELECT 1 AS num, 'SMART' AS project;")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 1
        assert row["num"] == 1
        assert row["project"] == "SMART"
        assert dict(row) == {"num": 1, "project": "SMART"}
    finally:
        conn.close()


@pytest.mark.skipif(not HAS_LIVE_POSTGRES, reason="PostgreSQL instance not configured in environment via DATABASE_URL; skipping live PostgreSQL integration tests")
def test_live_postgres_schema_initialization_and_table_count():
    """Live test 2: Schema initialization and verification of all 24 tables."""
    from database import init_db
    from db_engine import create_db_connection

    init_db()
    conn = create_db_connection()
    try:
        cur = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
            """
        )
        tables = [r[0] for r in cur.fetchall()]
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
        for t in expected_24:
            assert t in tables, f"Expected table '{t}' in public schema."
    finally:
        conn.close()


@pytest.mark.skipif(not HAS_LIVE_POSTGRES, reason="PostgreSQL instance not configured in environment via DATABASE_URL; skipping live PostgreSQL integration tests")
def test_live_postgres_user_provisioning_and_sessions():
    """Live test 3: User provisioning with generated ID, session creation and lookup."""
    from database import (
        create_user_session,
        delete_user_session,
        get_session_with_user,
        provision_user,
    )
    import uuid

    email = f"live.student.{uuid.uuid4().hex[:6]}@univ.edu"
    user = provision_user(
        email=email,
        name="Live Test Student",
        role="student",
        is_demo=0,
    )
    assert user is not None
    assert user.get("id") is not None
    user_id = user["id"]

    session_id = f"sess_{uuid.uuid4().hex}"
    csrf_token = f"csrf_{uuid.uuid4().hex}"
    expires_at = "2099-12-31T23:59:59Z"

    create_user_session(user_id=user_id, session_id=session_id, csrf_token=csrf_token, expires_at_iso=expires_at)

    session_data = get_session_with_user(session_id)
    assert session_data is not None
    assert session_data["email"] == email

    deleted = delete_user_session(session_id)
    assert deleted is True
    assert get_session_with_user(session_id) is None


@pytest.mark.skipif(not HAS_LIVE_POSTGRES, reason="PostgreSQL instance not configured in environment via DATABASE_URL; skipping live PostgreSQL integration tests")
def test_live_postgres_course_creation_and_enrollment():
    """Live test 4: Course creation with RETURNING id and join code enrollment."""
    from database import (
        create_smart_course,
        enroll_student_by_join_code,
        get_smart_course,
        provision_user,
    )
    import uuid

    t_email = f"live.prof.{uuid.uuid4().hex[:6]}@univ.edu"
    teacher = provision_user(email=t_email, name="Prof Live", role="teacher")

    code = f"CS-{uuid.uuid4().hex[:4].upper()}"
    course = create_smart_course(teacher_id=teacher["id"], code=code, name="Live Cloud DB Systems")
    assert course["id"] is not None
    cid = course["id"]
    join_code = course["join_code"]

    s_email = f"live.learner.{uuid.uuid4().hex[:6]}@univ.edu"
    student = provision_user(email=s_email, name="Learner Live", role="student")

    res = enroll_student_by_join_code(user_id=student["id"], join_code=join_code)
    assert res["status"] == "enrolled"

    # Duplicate enrollment should be idempotent (ON CONFLICT DO NOTHING)
    res_dup = enroll_student_by_join_code(user_id=student["id"], join_code=join_code)
    assert res_dup["status"] == "already_enrolled"


@pytest.mark.skipif(not HAS_LIVE_POSTGRES, reason="PostgreSQL instance not configured in environment via DATABASE_URL; skipping live PostgreSQL integration tests")
def test_live_postgres_announcements_and_acknowledgements():
    """Live test 5: Announcements, generated IDs, and read receipts with ON CONFLICT DO NOTHING."""
    from database import (
        acknowledge_announcement,
        create_course_announcement,
        create_smart_course,
        provision_user,
    )
    import uuid

    t = provision_user(email=f"prof.ann.{uuid.uuid4().hex[:6]}@univ.edu", name="Prof Ann", role="teacher")
    c = create_smart_course(teacher_id=t["id"], code=f"ANN-{uuid.uuid4().hex[:4].upper()}", name="Ann Course")
    s = provision_user(email=f"stud.ann.{uuid.uuid4().hex[:6]}@univ.edu", name="Stud Ann", role="student")

    ann = create_course_announcement(course_id=c["id"], teacher_id=t["id"], title="Exam Scope", content="Chapters 1-4")
    assert ann["id"] is not None
    ann_id = ann["id"]

    ack = acknowledge_announcement(announcement_id=ann_id, student_id=s["id"])
    assert ack["status"] == "acknowledged"

    # Duplicate acknowledgment should be ignored safely
    ack_dup = acknowledge_announcement(announcement_id=ann_id, student_id=s["id"])
    assert ack_dup["status"] == "acknowledged"


@pytest.mark.skipif(not HAS_LIVE_POSTGRES, reason="PostgreSQL instance not configured in environment via DATABASE_URL; skipping live PostgreSQL integration tests")
def test_live_postgres_single_choice_polls_and_voting():
    """Live test 6: Poll creation, single-choice voting and duplicate rejection."""
    from database import (
        create_course_poll,
        create_smart_course,
        enroll_student_by_join_code,
        get_poll_details,
        provision_user,
        submit_poll_vote,
    )
    import uuid

    t = provision_user(email=f"prof.poll.{uuid.uuid4().hex[:6]}@univ.edu", name="Prof Poll", role="teacher")
    c = create_smart_course(teacher_id=t["id"], code=f"POL-{uuid.uuid4().hex[:4].upper()}", name="Poll Course")
    s = provision_user(email=f"stud.poll.{uuid.uuid4().hex[:6]}@univ.edu", name="Stud Poll", role="student")
    enroll_student_by_join_code(s["id"], c["join_code"])

    poll = create_course_poll(course_id=c["id"], creator_id=t["id"], question="Preferred IDE?", options=["VS Code", "Vim", "PyCharm"])
    pid = poll["id"]
    opt_id = poll["options"][0]["id"]

    vote = submit_poll_vote(poll_id=pid, user_id=s["id"], option_id=opt_id)
    assert vote["user_voted"] is True
    assert vote["total_votes"] == 1

    # Second vote must be rejected (single-choice integrity)
    with pytest.raises(ValueError, match="already voted"):
        submit_poll_vote(poll_id=pid, user_id=s["id"], option_id=poll["options"][1]["id"])


@pytest.mark.skipif(not HAS_LIVE_POSTGRES, reason="PostgreSQL instance not configured in environment via DATABASE_URL; skipping live PostgreSQL integration tests")
def test_live_postgres_chat_and_read_receipts():
    """Live test 7: Course messages and read receipts."""
    from database import (
        create_smart_course,
        mark_messages_read,
        provision_user,
        save_course_message,
    )
    import uuid

    t = provision_user(email=f"prof.msg.{uuid.uuid4().hex[:6]}@univ.edu", name="Prof Msg", role="teacher")
    c = create_smart_course(teacher_id=t["id"], code=f"MSG-{uuid.uuid4().hex[:4].upper()}", name="Msg Course")
    s = provision_user(email=f"stud.msg.{uuid.uuid4().hex[:6]}@univ.edu", name="Stud Msg", role="student")

    msg = save_course_message(course_id=c["id"], sender_id=t["id"], content="Welcome to the course forum!")
    assert msg["id"] is not None

    count = mark_messages_read(course_id=c["id"], user_id=s["id"])
    assert count >= 1


@pytest.mark.skipif(not HAS_LIVE_POSTGRES, reason="PostgreSQL instance not configured in environment via DATABASE_URL; skipping live PostgreSQL integration tests")
def test_live_postgres_notifications_lifecycle():
    """Live test 8: Notifications creation and unread count."""
    from database import (
        create_notification,
        get_unread_notification_count,
        mark_notification_read,
        provision_user,
    )
    import uuid

    u = provision_user(email=f"user.notif.{uuid.uuid4().hex[:6]}@univ.edu", name="User Notif", role="student")
    uid = u["id"]

    notif = create_notification(user_id=uid, title="Assignment Posted", message="Due next week", notification_type="announcement")
    assert notif["id"] is not None
    nid = notif["id"]

    unread = get_unread_notification_count(uid)
    assert unread >= 1

    mark_notification_read(nid, uid)
    assert get_unread_notification_count(uid) == unread - 1


@pytest.mark.skipif(not HAS_LIVE_POSTGRES, reason="PostgreSQL instance not configured in environment via DATABASE_URL; skipping live PostgreSQL integration tests")
def test_live_postgres_google_account_token_storage():
    """Live test 9: Google account token persistence and update conflict handling."""
    from database import (
        delete_google_account,
        get_google_account,
        save_google_account,
    )
    import uuid

    g_email = f"google.user.{uuid.uuid4().hex[:6]}@university.edu"
    acc = save_google_account(
        account_data={
            "email": g_email,
            "name": "Google User",
            "encrypted_access_token": "enc_access_token_abc",
            "encrypted_refresh_token": "enc_refresh_token_xyz",
            "role": "student",
            "is_demo": 0,
        }
    )
    assert acc["email"] == g_email

    # Update with new tokens (verifying ON CONFLICT (email) DO UPDATE SET)
    acc_updated = save_google_account(
        account_data={
            "email": g_email,
            "name": "Google User Renamed",
            "encrypted_access_token": "enc_new_access_token",
            "encrypted_refresh_token": "enc_new_refresh_token",
            "role": "student",
            "is_demo": 0,
        }
    )
    assert acc_updated["name"] == "Google User Renamed"

    retrieved = get_google_account(email=g_email)
    assert retrieved is not None
    assert retrieved["encrypted_access_token"] == "enc_new_access_token"

    delete_google_account(email=g_email)
    assert get_google_account(email=g_email) is None


@pytest.mark.skipif(not HAS_LIVE_POSTGRES, reason="PostgreSQL instance not configured in environment via DATABASE_URL; skipping live PostgreSQL integration tests")
def test_live_postgres_transaction_rollback():
    """Live test 10: Multi-step transaction rollback upon genuine database constraint error."""
    from db_engine import create_db_connection
    import uuid

    conn = create_db_connection()
    unique_marker = f"rollback_test_{uuid.uuid4().hex[:6]}"
    unique_email = f"{unique_marker}@citchennai.net"

    try:
        error_raised = False
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
            error_raised = True

        assert error_raised, "A database constraint violation must be triggered"

        # After rollback, row must NOT exist in the database
        cur = conn.execute("SELECT id FROM users WHERE email = ?;", (unique_email,))
        assert cur.fetchone() is None
    finally:
        conn.close()
