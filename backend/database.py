"""SQLite Persistence and Academic Task Management Database Module.

Provides connection management, schema initialization, CRUD operations,
deduplication, and deterministic queries for SMART academic items.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Optional

from prioritization import (
    ALLOWED_IMPORTANCE_LEVELS,
    ALLOWED_PRIORITY_LEVELS,
    ALLOWED_URGENCY_LEVELS,
    enrich_task_with_prioritization,
)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "smart.db"

ALLOWED_CATEGORIES = {"Assignment", "Exam", "Announcement", "Event", "Opportunity"}
ALLOWED_STATUSES = {"pending", "completed", "dismissed", "cancelled", "superseded"}
# UNASSESSED: legacy rows pre-Phase3 or manually created tasks without a calculated score.
ALLOWED_CONFIDENCE_LEVELS = {"HIGH", "MEDIUM", "LOW", "UNASSESSED"}
ALLOWED_SOURCE_TYPES = {"whatsapp", "gmail", "google_classroom", "manual"}

# Confidence and confidence_reasons are system-generated algorithmic facts reflecting
# extraction fidelity. They must never be modified by API clients after persistence.
IMMUTABLE_FIELDS = {
    "id",
    "source_text",
    "source_sender",
    "source_timestamp",
    "source_filename",
    "source_type",
    "source_id",
    "source_metadata",
    "evidence_text",
    "evidence_start_index",
    "evidence_end_index",
    "confidence",
    "confidence_reasons",
    "created_at",
}

EDITABLE_COLUMNS = {
    "title",
    "category",
    "description",
    "date_text",
    "due_date",
    "date_type",
    "date_status",
    "status",
    "review_required",
    "review_reasons",
    "is_actionable",
    "actionability_type",
    "update_type",
    "is_range",
    "previous_due_date",
    "replaces_task_id",
    "importance",
    "academic_intent",
}


def get_db_path() -> Path:
    """Return the active database path from environment or default location."""
    env_path = os.environ.get("SMART_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def is_valid_iso_date(val: Optional[str]) -> bool:
    """Check if a string is a valid ISO 8601 YYYY-MM-DD date."""
    if not val or not isinstance(val, str):
        return False
    if len(val) != 10 or val[4] != "-" or val[7] != "-":
        return False
    try:
        datetime.strptime(val, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def get_db_connection(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    """Create and configure a SQLite database connection with row factory."""
    resolved_path = Path(db_path) if db_path else get_db_path()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved_path), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db(db_path: Optional[Path | str] = None) -> None:
    """Safely initialize the academic items schema and apply additive migrations."""
    resolved_path = Path(db_path) if db_path else get_db_path()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    with get_db_connection(resolved_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS academic_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                date_text TEXT,
                due_date TEXT,
                date_type TEXT,
                date_status TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                source_sender TEXT,
                source_timestamp TEXT,
                source_text TEXT NOT NULL,
                source_filename TEXT,
                source_type TEXT DEFAULT 'whatsapp',
                source_id TEXT,
                source_metadata TEXT,
                review_required INTEGER NOT NULL DEFAULT 0,
                review_reasons TEXT,
                evidence_text TEXT,
                evidence_start_index INTEGER,
                evidence_end_index INTEGER,
                confidence TEXT DEFAULT 'MEDIUM',
                confidence_reasons TEXT,
                is_actionable INTEGER,
                actionability_type TEXT,
                update_type TEXT,
                is_range INTEGER DEFAULT 0,
                previous_due_date TEXT,
                replaces_task_id INTEGER,
                importance TEXT DEFAULT 'UNASSESSED',
                academic_intent TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        # Additive migration: check existing columns and add missing ones
        cursor = conn.execute("PRAGMA table_info(academic_items);")
        existing_cols = {row["name"] for row in cursor.fetchall()}

        if "evidence_text" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN evidence_text TEXT;")

        if "evidence_start_index" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN evidence_start_index INTEGER;")

        if "evidence_end_index" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN evidence_end_index INTEGER;")

        if "confidence" not in existing_cols:
            conn.execute(
                "ALTER TABLE academic_items ADD COLUMN confidence TEXT DEFAULT 'MEDIUM';"
            )

        if "confidence_reasons" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN confidence_reasons TEXT;")

        if "is_actionable" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN is_actionable INTEGER;")

        if "actionability_type" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN actionability_type TEXT;")

        if "update_type" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN update_type TEXT;")

        if "is_range" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN is_range INTEGER DEFAULT 0;")

        if "previous_due_date" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN previous_due_date TEXT;")

        if "replaces_task_id" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN replaces_task_id INTEGER;")

        if "importance" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN importance TEXT DEFAULT 'UNASSESSED';")

        if "academic_intent" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN academic_intent TEXT;")

        if "source_type" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN source_type TEXT DEFAULT 'whatsapp';")

        if "source_id" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN source_id TEXT;")

        if "source_metadata" not in existing_cols:
            conn.execute("ALTER TABLE academic_items ADD COLUMN source_metadata TEXT;")

        # Schema migrations tracking table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            """
        )

        # Safe additive migration for legacy records:
        # Pre-Phase-4.1 Announcement records must be classified as informational (is_actionable=0),
        # not falsely promoted to actionable tasks.
        # This migration is recorded in schema_migrations so it executes exactly once and remains idempotent.
        cursor = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_name = 'phase_4_1_legacy_classification' LIMIT 1;"
        )
        if cursor.fetchone() is None:
            conn.execute(
                """
                UPDATE academic_items
                SET is_actionable = 0, actionability_type = 'informational'
                WHERE category = 'Announcement' AND (is_actionable IS NULL OR actionability_type IS NULL OR actionability_type = 'action_required');
                """
            )
            conn.execute(
                """
                UPDATE academic_items
                SET is_actionable = 1, actionability_type = 'action_required'
                WHERE category IN ('Assignment', 'Exam') AND (is_actionable IS NULL OR actionability_type IS NULL);
                """
            )
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO schema_migrations (migration_name, applied_at) VALUES ('phase_4_1_legacy_classification', ?);",
                (now_iso,),
            )

        # SMART 2.1 Additive Migration: Google Accounts, Opportunities, Classroom & Materials
        cursor = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_name = 'smart_2_1_tables' LIMIT 1;"
        )
        if cursor.fetchone() is None:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS google_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT,
                    picture TEXT,
                    encrypted_access_token TEXT,
                    encrypted_refresh_token TEXT,
                    token_expiry TEXT,
                    scopes TEXT,
                    role TEXT DEFAULT 'student',
                    is_demo INTEGER DEFAULT 0,
                    last_sync_gmail TEXT,
                    last_sync_classroom TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    organizer TEXT,
                    description TEXT,
                    eligibility TEXT,
                    registration_deadline TEXT,
                    event_date TEXT,
                    registration_url TEXT,
                    source_type TEXT DEFAULT 'gmail',
                    source_id TEXT,
                    source_sender TEXT,
                    source_timestamp TEXT,
                    evidence_text TEXT,
                    confidence TEXT DEFAULT 'HIGH',
                    review_status TEXT DEFAULT 'confirmed',
                    is_demo INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS student_opportunity_statuses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    opportunity_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'discovered',
                    evidence_notes TEXT,
                    confirmation_source_ref TEXT,
                    updated_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE CASCADE,
                    UNIQUE (student_id, opportunity_id)
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS classroom_courses (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    section TEXT,
                    description_heading TEXT,
                    room TEXT,
                    owner_id TEXT,
                    teacher_email TEXT,
                    user_role TEXT DEFAULT 'student',
                    alternate_link TEXT,
                    is_demo INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS classroom_coursework (
                    id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    due_date TEXT,
                    due_time TEXT,
                    max_points REAL,
                    work_type TEXT DEFAULT 'ASSIGNMENT',
                    state TEXT DEFAULT 'PUBLISHED',
                    alternate_link TEXT,
                    is_demo INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (course_id) REFERENCES classroom_courses(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS classroom_submissions (
                    id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    coursework_id TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    student_name TEXT,
                    state TEXT NOT NULL DEFAULT 'NEW',
                    assigned_grade REAL,
                    late INTEGER DEFAULT 0,
                    alternate_link TEXT,
                    is_demo INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (coursework_id) REFERENCES classroom_coursework(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS study_materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_type TEXT,
                    file_size INTEGER,
                    file_url TEXT,
                    source_type TEXT NOT NULL,
                    source_id TEXT,
                    course_id TEXT,
                    course_name TEXT,
                    uploaded_by TEXT,
                    is_demo INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_deadline ON opportunities(registration_deadline);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_source ON opportunities(source_type, source_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_student_opp_status ON student_opportunity_statuses(student_id, status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_classroom_coursework_course ON classroom_coursework(course_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_classroom_submissions_cw ON classroom_submissions(coursework_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_classroom_submissions_student ON classroom_submissions(student_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_study_materials_course ON study_materials(course_id);")

            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO schema_migrations (migration_name, applied_at) VALUES ('smart_2_1_tables', ?);",
                (now_iso,),
            )

        # SMART 2.1 Additive Migration: Users & Session Authentication
        cursor = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_name = 'smart_2_1_auth_tables' LIMIT 1;"
        )
        if cursor.fetchone() is None:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('student', 'teacher')),
                    status TEXT NOT NULL DEFAULT 'active',
                    picture TEXT,
                    is_demo INTEGER DEFAULT 0,
                    department TEXT,
                    program TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    csrf_token TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);")

            now_iso = datetime.now(timezone.utc).isoformat()

            # Seed pre-provisioned demo accounts
            conn.execute(
                """
                INSERT OR IGNORE INTO users (email, name, role, status, is_demo, department, program, created_at, updated_at)
                VALUES ('alex.morgan@university.edu', 'Alex Morgan', 'student', 'active', 1, 'Computer Science', 'B.Tech CS (Year 3)', ?, ?)
                """,
                (now_iso, now_iso),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO users (email, name, role, status, is_demo, department, program, created_at, updated_at)
                VALUES ('e.vance@university.edu', 'Dr. Elena Vance', 'teacher', 'active', 1, 'Computer Science', 'Faculty / Instructor', ?, ?)
                """,
                (now_iso, now_iso),
            )

            conn.execute(
                "INSERT INTO schema_migrations (migration_name, applied_at) VALUES ('smart_2_1_auth_tables', ?);",
                (now_iso,),
            )

        # Seed initial demo courses and coursework if classroom_courses is empty
        cur_cc = conn.execute("SELECT COUNT(*) FROM classroom_courses;").fetchone()
        if cur_cc and cur_cc[0] == 0:
            seed_now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT OR IGNORE INTO classroom_courses (id, name, section, description_heading, room, owner_id, teacher_email, user_role, alternate_link, is_demo, created_at, updated_at)
                VALUES
                ('demo_cs401', 'CS401: Distributed Systems', 'Section A', 'Consensus, Raft, Paxos & Scalable Architectures', 'Hall 301', 'e.vance@university.edu', 'e.vance@university.edu', 'teacher', 'https://classroom.google.com/c/demo_cs401', 1, ?, ?),
                ('demo_cs302', 'CS302: Compiler Design', 'Section B', 'Lexical Analysis, LL/LR Parsers, Code Generation', 'Lab 4', 'e.vance@university.edu', 'e.vance@university.edu', 'teacher', 'https://classroom.google.com/c/demo_cs302', 1, ?, ?),
                ('demo_cs505_teach', 'CS505: Cloud Computing Lab', 'Graduate Section', 'Kubernetes, Microservices & Serverless', 'Cloud Lab 2', 'e.vance@university.edu', 'e.vance@university.edu', 'teacher', 'https://classroom.google.com/c/demo_cs505_teach', 1, ?, ?);
                """,
                (seed_now, seed_now, seed_now, seed_now, seed_now, seed_now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO classroom_coursework (id, course_id, title, description, due_date, due_time, max_points, work_type, state, alternate_link, is_demo, created_at, updated_at)
                VALUES
                ('demo_cw_cs401_lab2', 'demo_cs401', 'Lab 2: Raft Leader Election Implementation', 'Implement consensus leader election and heartbeats.', '2026-12-02', '23:59', 100, 'ASSIGNMENT', 'PUBLISHED', 'https://classroom.google.com/c/demo_cs401/a/lab2', 1, ?, ?),
                ('demo_cw_cs302_parser', 'demo_cs302', 'Assignment 3: LALR(1) Parser Table Generator', 'Construct grammar parsing tables and verify conflicts.', '2026-11-30', '17:00', 50, 'ASSIGNMENT', 'PUBLISHED', 'https://classroom.google.com/c/demo_cs302/a/asg3', 1, ?, ?),
                ('demo_cw_cs505_k8s', 'demo_cs505_teach', 'Lab 1: Docker Swarm vs Kubernetes Deployment', 'Deploy microservices stack with auto-scaling.', '2026-12-08', '23:59', 100, 'ASSIGNMENT', 'PUBLISHED', 'https://classroom.google.com/c/demo_cs505_teach/a/lab1', 1, ?, ?);
                """,
                (seed_now, seed_now, seed_now, seed_now, seed_now, seed_now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO classroom_submissions (id, course_id, coursework_id, student_id, student_name, state, assigned_grade, late, alternate_link, is_demo, created_at, updated_at)
                VALUES
                ('demo_sub_1', 'demo_cs401', 'demo_cw_cs401_lab2', 'alex.morgan@university.edu', 'Alex Morgan', 'TURNED_IN', NULL, 0, 'https://classroom.google.com/c/demo_cs401/s/1', 1, ?, ?),
                ('demo_sub_2', 'demo_cs302', 'demo_cw_cs302_parser', 'alex.morgan@university.edu', 'Alex Morgan', 'RETURNED', 48.0, 0, 'https://classroom.google.com/c/demo_cs302/s/2', 1, ?, ?),
                ('demo_sub_teach_1', 'demo_cs505_teach', 'demo_cw_cs505_k8s', 'riya.sharma@univ.edu', 'Riya Sharma', 'TURNED_IN', 92.0, 0, 'https://classroom.google.com/c/demo_cs505_teach/s/3', 1, ?, ?),
                ('demo_sub_teach_2', 'demo_cs401', 'demo_cw_cs401_lab2', 'marcus.chen@univ.edu', 'Marcus Chen', 'RETURNED', 95.0, 0, 'https://classroom.google.com/c/demo_cs401/s/2', 1, ?, ?);
                """,
                (seed_now, seed_now, seed_now, seed_now, seed_now, seed_now, seed_now, seed_now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO study_materials (title, file_name, file_size, source_type, source_id, course_id, course_name, file_url, uploaded_by, is_demo, created_at)
                VALUES
                ('CS401 Lecture 8 - Consensus & Raft Slides.pdf', 'CS401_Lec8_Raft.pdf', 2450000, 'classroom_material', 'demo_mat_1', 'demo_cs401', 'CS401: Distributed Systems', 'https://classroom.google.com/c/demo_cs401/m/raft_slides', 'Dr. Elena Vance', 1, ?),
                ('ACM ICPC 2026 Problem Set & Solution Guidelines.pdf', 'ICPC_2026_Problem_Set.pdf', 1820000, 'gmail_attachment', 'demo_mat_2', NULL, NULL, 'https://mail.google.com/mail/u/0/#inbox/demo_msg_icpc', 'ACM Student Chapter', 1, ?),
                ('CS302 Lex & Yacc Reference Manual.pdf', 'CS302_Lex_Yacc_Manual.pdf', 3145000, 'classroom_material', 'demo_mat_3', 'demo_cs302', 'CS302: Compiler Design', 'https://classroom.google.com/c/demo_cs302/m/manual', 'Dr. Elena Vance', 1, ?);
                """,
                (seed_now, seed_now, seed_now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO opportunities (id, name, organizer, description, eligibility, registration_deadline, event_date, registration_url, source_type, source_id, source_sender, source_timestamp, evidence_text, confidence, review_status, is_demo, created_at, updated_at)
                VALUES
                (1, 'National Inter-College Hackathon 2026', 'ACM Student Chapter & Tech Council', '48-hour buildathon focusing on Generative AI, Cloud Systems, and Decentralized Tech.', 'Open to all UG/PG CS & IT students (teams of 2-4)', '2026-11-28', '2026-12-05', 'https://acm.univ.edu/hackathon2026', 'gmail', 'demo_msg_hackathon', 'ACM Lead <acm@univ.edu>', '2026-11-20 10:00', 'Registration deadline is 2026-11-28.', 'HIGH', 'confirmed', 1, ?, ?),
                (2, 'Google Solution Challenge 2026', 'Google Developer Student Clubs', 'Build solutions for the UN Sustainable Development Goals using Google Cloud, Android, and Flutter.', 'College students members of GDSC chapters.', '2026-12-20', '2027-01-15', 'https://developers.google.com/community/gdsc-solution-challenge', 'gmail', 'demo_msg_gdsc', 'GDSC Lead <gdsc@univ.edu>', '2026-11-22 10:15', 'Submission window closes on 2026-12-20.', 'HIGH', 'confirmed', 1, ?, ?),
                (3, 'IEEE Student Paper Contest on Distributed AI', 'IEEE Computer Society Chapter', 'Submit original research papers on edge computing, federated learning, or multi-agent systems.', 'Pre-final and Final year undergraduate students', '2026-12-15', '2027-01-10', 'https://ieee.univ.edu/paper-contest', 'gmail', 'demo_msg_ieee', 'IEEE Sponsor <ieee@univ.edu>', '2026-11-21 16:30', 'Paper submissions due by 2026-12-15.', 'HIGH', 'confirmed', 1, ?, ?);
                """,
                (seed_now, seed_now, seed_now, seed_now, seed_now, seed_now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO student_opportunity_statuses (student_id, opportunity_id, status, evidence_notes, created_at, updated_at)
                VALUES
                ('alex.morgan@university.edu', 1, 'interested', 'Sample opportunity participation status for local testing.', ?, ?),
                ('alex.morgan@university.edu', 2, 'registered', 'Sample opportunity participation status for local testing.', ?, ?),
                ('alex.morgan@university.edu', 3, 'registration_pending', 'Sample opportunity participation status for local testing.', ?, ?);
                """,
                (seed_now, seed_now, seed_now, seed_now, seed_now, seed_now),
            )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_academic_items_category ON academic_items(category);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_academic_items_status ON academic_items(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_academic_items_due_date ON academic_items(due_date);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_academic_items_confidence ON academic_items(confidence);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_academic_items_dedup ON academic_items(source_text, source_timestamp, source_sender, category);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_academic_items_source ON academic_items(source_type, source_id);"
        )
        conn.commit()


def row_to_item_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert an academic_items sqlite3.Row to a clean dictionary."""
    row_keys = row.keys()

    reasons_raw = row["review_reasons"] if "review_reasons" in row_keys else None
    reasons: list[str] = []
    if reasons_raw:
        try:
            reasons = json.loads(reasons_raw)
            if not isinstance(reasons, list):
                reasons = [str(reasons)]
        except (json.JSONDecodeError, TypeError):
            reasons = [reasons_raw]

    conf_reasons_raw = row["confidence_reasons"] if "confidence_reasons" in row_keys else None
    conf_reasons: list[str] = []
    if conf_reasons_raw:
        try:
            conf_reasons = json.loads(conf_reasons_raw)
            if not isinstance(conf_reasons, list):
                conf_reasons = [str(conf_reasons)]
        except (json.JSONDecodeError, TypeError):
            conf_reasons = [conf_reasons_raw]

    # Legacy rows (pre-Phase3) with NULL confidence are represented as UNASSESSED rather
    # than silently promoted to MEDIUM, which would misrepresent unscored records.
    confidence = row["confidence"] if ("confidence" in row_keys and row["confidence"]) else "UNASSESSED"
    # Legacy rows without evidence_text remain None — not backfilled from source_text.
    evidence_text = row["evidence_text"] if ("evidence_text" in row_keys and row["evidence_text"]) else None
    evidence_start_index = (
        int(row["evidence_start_index"])
        if ("evidence_start_index" in row_keys and row["evidence_start_index"] is not None)
        else None
    )
    evidence_end_index = (
        int(row["evidence_end_index"])
        if ("evidence_end_index" in row_keys and row["evidence_end_index"] is not None)
        else None
    )

    raw_actionable = row["is_actionable"] if "is_actionable" in row_keys else None
    if raw_actionable is not None:
        is_actionable = bool(raw_actionable)
    elif row["category"] == "Announcement":
        is_actionable = False
    elif row["category"] in ("Assignment", "Exam"):
        is_actionable = True
    else:
        is_actionable = None

    raw_act_type = row["actionability_type"] if "actionability_type" in row_keys else None
    if raw_act_type:
        actionability_type = str(raw_act_type)
    elif row["category"] == "Announcement":
        actionability_type = "informational"
    elif row["category"] in ("Assignment", "Exam"):
        actionability_type = "action_required"
    else:
        actionability_type = "unassessed"

    update_type = row["update_type"] if "update_type" in row_keys else None
    raw_is_range = row["is_range"] if "is_range" in row_keys else None
    is_range = bool(raw_is_range) if raw_is_range is not None else False
    previous_due_date = row["previous_due_date"] if "previous_due_date" in row_keys else None
    replaces_task_id = (
        int(row["replaces_task_id"])
        if ("replaces_task_id" in row_keys and row["replaces_task_id"] is not None)
        else None
    )
    raw_importance = row["importance"] if "importance" in row_keys and row["importance"] else "UNASSESSED"
    importance = str(raw_importance).strip().upper() if raw_importance else "UNASSESSED"
    academic_intent = row["academic_intent"] if "academic_intent" in row_keys and row["academic_intent"] else None

    source_type = row["source_type"] if "source_type" in row_keys and row["source_type"] else "whatsapp"
    source_id = row["source_id"] if "source_id" in row_keys and row["source_id"] else None
    raw_metadata = row["source_metadata"] if "source_metadata" in row_keys else None
    source_metadata: Optional[dict[str, Any]] = None
    if raw_metadata:
        try:
            parsed_meta = json.loads(raw_metadata)
            if isinstance(parsed_meta, dict):
                source_metadata = parsed_meta
            else:
                source_metadata = {"raw": parsed_meta}
        except (json.JSONDecodeError, TypeError):
            source_metadata = {"raw": raw_metadata}

    base_dict = {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "description": row["description"] or "",
        "date_text": row["date_text"],
        "due_date": row["due_date"],
        "date_type": row["date_type"] or "unknown",
        "date_status": row["date_status"] or "not_found",
        "status": row["status"],
        "source_sender": row["source_sender"] or "",
        "source_timestamp": row["source_timestamp"] or "",
        "source_text": row["source_text"],
        "source_filename": row["source_filename"] or "",
        "source_type": source_type,
        "source_id": source_id,
        "source_metadata": source_metadata,
        "evidence_text": evidence_text,
        "evidence_start_index": evidence_start_index,
        "evidence_end_index": evidence_end_index,
        "confidence": confidence,
        "confidence_reasons": conf_reasons,
        "is_actionable": is_actionable,
        "actionability_type": actionability_type,
        "update_type": update_type,
        "is_range": is_range,
        "previous_due_date": previous_due_date,
        "replaces_task_id": replaces_task_id,
        "importance": importance,
        "academic_intent": academic_intent,
        "review_required": bool(row["review_required"]),
        "review_reasons": reasons,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    return enrich_task_with_prioritization(base_dict)


def find_duplicate_item(
    source_text: str,
    source_timestamp: Optional[str],
    source_sender: Optional[str],
    category: str,
    source_filename: Optional[str] = None,
    source_type: Optional[str] = "whatsapp",
    source_id: Optional[str] = None,
    title: Optional[str] = None,
    evidence_text: Optional[str] = None,
    evidence_start_index: Optional[int] = None,
    db_path: Optional[Path | str] = None,
) -> Optional[dict[str, Any]]:
    """Check if an item matching key source provenance already exists.

    Enables multiple independent candidates extracted from the same source message
    (same source_id / source_text) to be saved distinctly when their evidence or title
    differs, while reliably detecting repeated duplicate submissions of the exact same candidate.
    """
    clean_text = (source_text or "").strip()
    clean_timestamp = (source_timestamp or "").strip()
    clean_sender = (source_sender or "").strip()
    clean_filename = (source_filename or "").strip()
    clean_source_type = (source_type or "whatsapp").strip().lower()
    clean_source_id = (source_id or "").strip()
    clean_title = (title or "").strip().lower() if title else None
    clean_evidence = (evidence_text or "").strip() if evidence_text else None
    ev_idx = int(evidence_start_index) if evidence_start_index is not None else None

    with get_db_connection(db_path) as conn:
        # Fast path: deduplicate by stable external source ID when available
        if clean_source_id:
            cursor = conn.execute(
                """
                SELECT * FROM academic_items
                WHERE source_type = ?
                  AND source_id = ?
                  AND category = ?;
                """,
                (clean_source_type, clean_source_id, category),
            )
            rows = cursor.fetchall()
            if not rows:
                return None

            # Differentiate multiple tasks from the same source_id
            for row in rows:
                row_ev_idx = row["evidence_start_index"]
                row_ev_text = (row["evidence_text"] or "").strip() if row["evidence_text"] else None
                row_title = (row["title"] or "").strip().lower() if row["title"] else None

                # 1. Exact occurrence offset match
                if ev_idx is not None and row_ev_idx is not None:
                    if row_ev_idx == ev_idx:
                        return row_to_item_dict(row)
                    continue

                # 2. Exact evidence text match
                if clean_evidence and row_ev_text:
                    if row_ev_text == clean_evidence:
                        return row_to_item_dict(row)
                    continue

                # 3. Normalized title match
                if clean_title and row_title and row_title == clean_title:
                    return row_to_item_dict(row)

            # If incoming item has distinguishing extraction evidence/offsets that didn't match any row,
            # it is a distinct task from the same source message.
            if ev_idx is not None or clean_evidence:
                return None

            # Otherwise, for single-task source_id or items without extraction offsets, return existing row
            return row_to_item_dict(rows[0])

        # Fallback path: deduplicate by source message provenance
        cursor = conn.execute(
            """
            SELECT * FROM academic_items
            WHERE TRIM(source_text) = ?
              AND category = ?
              AND (TRIM(COALESCE(source_timestamp, '')) = ?)
              AND (TRIM(COALESCE(source_sender, '')) = ?)
              AND (TRIM(COALESCE(source_filename, '')) = ?)
              AND (TRIM(COALESCE(source_type, 'whatsapp')) = ?);
            """,
            (clean_text, category, clean_timestamp, clean_sender, clean_filename, clean_source_type),
        )
        rows = cursor.fetchall()
        if not rows:
            return None

        # Differentiate multi-candidate extractions from the same chat message
        for row in rows:
            row_ev_idx = row["evidence_start_index"]
            row_ev_text = (row["evidence_text"] or "").strip() if row["evidence_text"] else None
            row_title = (row["title"] or "").strip().lower() if row["title"] else None

            # 1. Exact occurrence offset match
            if ev_idx is not None and row_ev_idx is not None:
                if row_ev_idx == ev_idx:
                    return row_to_item_dict(row)
                continue

            # 2. Exact evidence text match
            if clean_evidence and row_ev_text:
                if row_ev_text == clean_evidence:
                    return row_to_item_dict(row)
                continue

            # 3. Normalized title match
            if clean_title and row_title and row_title == clean_title:
                return row_to_item_dict(row)

        # If incoming item has distinguishing extraction evidence/offsets that didn't match any row,
        # it is a distinct task from the same chat message.
        if ev_idx is not None or clean_evidence:
            return None

        # For items without extraction evidence (e.g. manual creation or legacy rows),
        # any existing row with identical source message provenance is a duplicate.
        return row_to_item_dict(rows[0])


def save_academic_item(
    data: dict[str, Any],
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Validate and insert an academic item into the database.

    Raises ValueError for schema/business validation errors.
    """
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("Item title is required.")

    category = (data.get("category") or "").strip()
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Allowed categories: {', '.join(sorted(ALLOWED_CATEGORIES))}"
        )

    source_text = (data.get("source_text") or "").strip()
    if not source_text:
        raise ValueError("Source text is required.")

    status = (data.get("status") or "pending").strip().lower()
    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Allowed statuses: {', '.join(sorted(ALLOWED_STATUSES))}"
        )

    due_date = data.get("due_date")
    if due_date:
        due_date = str(due_date).strip()
        if not is_valid_iso_date(due_date):
            raise ValueError(
                f"Invalid due_date format '{due_date}'. Expected YYYY-MM-DD."
            )
    else:
        due_date = None

    description = (data.get("description") or source_text).strip()
    date_text = data.get("date_text")
    date_text = str(date_text).strip() if date_text else None

    date_type = data.get("date_type")
    date_type = str(date_type).strip() if date_type else "unknown"

    date_status = data.get("date_status")
    date_status = str(date_status).strip() if date_status else "not_found"

    source_sender = data.get("source_sender")
    source_sender = str(source_sender).strip() if source_sender else ""

    source_timestamp = data.get("source_timestamp")
    source_timestamp = str(source_timestamp).strip() if source_timestamp else ""

    source_filename = data.get("source_filename")
    source_filename = str(source_filename).strip() if source_filename else ""

    raw_source_type = data.get("source_type") or "whatsapp"
    source_type = str(raw_source_type).strip().lower()
    if source_type not in ALLOWED_SOURCE_TYPES:
        source_type = "whatsapp"

    source_id = data.get("source_id")
    source_id = str(source_id).strip() if source_id else None

    raw_meta = data.get("source_metadata")
    if isinstance(raw_meta, (dict, list)):
        source_metadata_str = json.dumps(raw_meta)
    elif isinstance(raw_meta, str):
        source_metadata_str = raw_meta
    else:
        source_metadata_str = None

    review_required = 1 if data.get("review_required") else 0
    review_reasons = data.get("review_reasons") or []
    if isinstance(review_reasons, str):
        review_reasons_str = json.dumps([review_reasons])
    else:
        review_reasons_str = json.dumps(list(review_reasons))

    # evidence_text: only trusted when sourced from the backend extraction pipeline.
    # The trusted path uses the _trusted_evidence sentinel key.
    # Client-supplied evidence_text via POST is accepted only when it matches source_text
    # exactly, preventing injection of fabricated extraction evidence.
    raw_evidence = data.get("evidence_text")
    if raw_evidence:
        raw_evidence = str(raw_evidence).strip()
        # Validate substring membership only when this is a client-supplied POST (not pipeline).
        if not data.get("_trusted_evidence") and raw_evidence not in source_text:
            raise ValueError(
                "evidence_text must be a substring of source_text. "
                "Fabricated extraction evidence is not permitted."
            )
        evidence_text: str | None = raw_evidence
    else:
        evidence_text = None

    # evidence_start_index and evidence_end_index: occurrence offsets.
    raw_start = data.get("evidence_start_index")
    raw_end = data.get("evidence_end_index")
    evidence_start_index: int | None = None
    evidence_end_index: int | None = None

    if raw_start is not None or raw_end is not None:
        if raw_start is None or raw_end is None:
            raise ValueError("Both evidence_start_index and evidence_end_index must be provided together.")
        try:
            s_idx = int(raw_start)
            e_idx = int(raw_end)
        except (ValueError, TypeError):
            raise ValueError("evidence_start_index and evidence_end_index must be valid integers.")

        if s_idx < 0 or e_idx < 0:
            raise ValueError("Evidence offsets cannot be negative.")
        if s_idx >= e_idx:
            raise ValueError("evidence_start_index must be strictly less than evidence_end_index.")
        if e_idx > len(source_text):
            raise ValueError("evidence_end_index cannot exceed the length of source_text.")

        target_slice = source_text[s_idx:e_idx]
        if evidence_text and target_slice != evidence_text:
            raise ValueError(
                f"Evidence offsets ({s_idx}, {e_idx}) point to '{target_slice[:50]}', "
                f"which does not match evidence_text '{evidence_text[:50]}'."
            )
        evidence_start_index = s_idx
        evidence_end_index = e_idx

    # confidence and confidence_reasons: system-generated fields.
    # Extraction pipeline passes _trusted_confidence to store its calculated score.
    # Manual/client-created tasks receive UNASSESSED to distinguish them from scored records.
    trusted_conf = data.get("_trusted_confidence")
    if trusted_conf:
        confidence = str(trusted_conf).strip().upper()
        if confidence not in ALLOWED_CONFIDENCE_LEVELS:
            confidence = "UNASSESSED"
    else:
        # Manual task creation: ignore client-supplied confidence; mark as UNASSESSED.
        confidence = "UNASSESSED"

    trusted_conf_reasons = data.get("_trusted_confidence_reasons") or []
    if isinstance(trusted_conf_reasons, str):
        conf_reasons_str = json.dumps([trusted_conf_reasons])
    else:
        conf_reasons_str = json.dumps(list(trusted_conf_reasons))

    raw_actionable = data.get("is_actionable")
    if raw_actionable is not None:
        is_actionable = 1 if raw_actionable else 0
    elif category == "Announcement":
        is_actionable = 0
    elif category in ("Assignment", "Exam"):
        is_actionable = 1
    else:
        is_actionable = None

    raw_act_type = data.get("actionability_type")
    if raw_act_type:
        actionability_type = str(raw_act_type).strip()
    elif category == "Announcement":
        actionability_type = "informational"
    elif category in ("Assignment", "Exam"):
        actionability_type = "action_required"
    else:
        actionability_type = "unassessed"

    update_type = data.get("update_type")
    update_type = str(update_type).strip() if update_type else None

    raw_is_range = data.get("is_range")
    is_range = 1 if raw_is_range else 0

    previous_due_date = data.get("previous_due_date")
    if previous_due_date:
        previous_due_date = str(previous_due_date).strip()
        if not is_valid_iso_date(previous_due_date):
            raise ValueError(
                f"Invalid previous_due_date format '{previous_due_date}'. Expected YYYY-MM-DD."
            )
    else:
        previous_due_date = None

    replaces_task_id = data.get("replaces_task_id")
    if replaces_task_id is not None:
        try:
            r_id = int(replaces_task_id)
            # Server-side validation: never trust replaces_task_id without database existence check
            target_task = get_academic_item_by_id(r_id, db_path=db_path)
            if target_task:
                replaces_task_id = r_id
            else:
                replaces_task_id = None
                review_required = 1
                curr_rev = list(review_reasons) if isinstance(review_reasons, (list, tuple)) else []
                curr_rev.append(f"Specified replaces_task_id #{r_id} was not found; cleared for safety.")
                review_reasons_str = json.dumps(curr_rev)
        except (ValueError, TypeError):
            replaces_task_id = None
    else:
        replaces_task_id = None

    raw_importance = data.get("importance")
    if raw_importance:
        clean_imp = str(raw_importance).strip().upper()
        importance = clean_imp if clean_imp in ALLOWED_IMPORTANCE_LEVELS else "UNASSESSED"
    else:
        importance = "UNASSESSED"

    academic_intent = data.get("academic_intent")
    academic_intent = str(academic_intent).strip() if academic_intent else None

    now_iso = datetime.now(timezone.utc).isoformat()

    insert_sql = """
        INSERT INTO academic_items (
            title, category, description, date_text, due_date, date_type,
            date_status, status, source_sender, source_timestamp, source_text,
            source_filename, source_type, source_id, source_metadata,
            evidence_text, evidence_start_index, evidence_end_index,
            confidence, confidence_reasons, is_actionable, actionability_type,
            update_type, is_range, previous_due_date, replaces_task_id,
            importance, academic_intent,
            review_required, review_reasons, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    params = (
        title,
        category,
        description,
        date_text,
        due_date,
        date_type,
        date_status,
        status,
        source_sender,
        source_timestamp,
        source_text,
        source_filename,
        source_type,
        source_id,
        source_metadata_str,
        evidence_text,
        evidence_start_index,
        evidence_end_index,
        confidence,
        conf_reasons_str,
        is_actionable,
        actionability_type,
        update_type,
        is_range,
        previous_due_date,
        replaces_task_id,
        importance,
        academic_intent,
        review_required,
        review_reasons_str,
        now_iso,
        now_iso,
    )

    if conn is not None:
        cursor = conn.execute(insert_sql, params)
        new_id = cursor.lastrowid
        cur = conn.execute("SELECT * FROM academic_items WHERE id = ? LIMIT 1;", (new_id,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Failed to retrieve item immediately after saving in transaction.")
        return row_to_item_dict(row)

    with get_db_connection(db_path) as direct_conn:
        cursor = direct_conn.execute(insert_sql, params)
        new_id = cursor.lastrowid
        direct_conn.commit()

    saved = get_academic_item_by_id(new_id, db_path=db_path)
    if not saved:
        raise RuntimeError("Failed to retrieve item immediately after saving.")
    return saved


def save_academic_item_with_association(
    data: dict[str, Any],
    target_id: int,
    target_status: str = "superseded",
    target_review_required: Optional[bool] = None,
    target_review_reasons: Optional[list[str]] = None,
    db_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Atomically insert a new academic item and update its associated target task.

    Guarantees transactional consistency: status updates on the target task
    and the new task creation commit together or roll back completely on error.
    """
    if not isinstance(target_id, int) or target_id <= 0:
        raise ValueError(f"Invalid target_id {target_id}")

    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.execute("SELECT id FROM academic_items WHERE id = ?;", (target_id,))
            if not cur.fetchone():
                raise ValueError(f"Target task #{target_id} not found in database.")

            if target_review_required is not None:
                reasons_str = json.dumps(target_review_reasons or [])
                conn.execute(
                    """
                    UPDATE academic_items
                    SET status = ?, review_required = ?, review_reasons = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (target_status, 1 if target_review_required else 0, reasons_str, now_iso, target_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE academic_items
                    SET status = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (target_status, now_iso, target_id),
                )

            saved = save_academic_item(data, db_path=db_path, conn=conn)
            conn.commit()
            return saved
        except Exception:
            conn.rollback()
            raise


def get_academic_item_by_id(
    item_id: int,
    db_path: Optional[Path | str] = None,
) -> Optional[dict[str, Any]]:
    """Retrieve a single academic item by its primary key ID."""
    query = "SELECT * FROM academic_items WHERE id = ? LIMIT 1;"
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, (item_id,))
        row = cursor.fetchone()
        if row:
            return row_to_item_dict(row)
    return None


def list_academic_items(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    due_before: Optional[str] = None,
    due_after: Optional[str] = None,
    confidence: Optional[str] = None,
    priority: Optional[str] = None,
    importance: Optional[str] = None,
    urgency: Optional[str] = None,
    academic_intent: Optional[str] = None,
    source_type: Optional[str] = None,
    db_path: Optional[Path | str] = None,
) -> list[dict[str, Any]]:
    """Query and filter academic items with deterministic ordering.

    Orders upcoming dated items first chronologically, followed by undated items,
    with newest ID as tie-breaker.
    """
    conditions: list[str] = []
    params: list[Any] = []

    if source_type:
        st_clean = source_type.strip().lower()
        if st_clean not in ALLOWED_SOURCE_TYPES:
            raise ValueError(
                f"Invalid source_type '{source_type}'. Allowed types: {', '.join(sorted(ALLOWED_SOURCE_TYPES))}"
            )
        conditions.append("COALESCE(source_type, 'whatsapp') = ?")
        params.append(st_clean)

    if category:
        category_clean = category.strip()
        if category_clean not in ALLOWED_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Allowed categories: {', '.join(sorted(ALLOWED_CATEGORIES))}"
            )
        conditions.append("category = ?")
        params.append(category_clean)

    if status:
        status_clean = status.strip().lower()
        if status_clean not in ALLOWED_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Allowed statuses: {', '.join(sorted(ALLOWED_STATUSES))}"
            )
        conditions.append("status = ?")
        params.append(status_clean)

    if confidence:
        confidence_clean = confidence.strip().upper()
        if confidence_clean not in ALLOWED_CONFIDENCE_LEVELS:
            raise ValueError(
                f"Invalid confidence '{confidence}'. Allowed levels: {', '.join(sorted(ALLOWED_CONFIDENCE_LEVELS))}"
            )
        # UNASSESSED rows may be stored as NULL (legacy) or as the literal 'UNASSESSED' string.
        if confidence_clean == "UNASSESSED":
            conditions.append("(confidence IS NULL OR confidence = 'UNASSESSED')")
        else:
            conditions.append("confidence = ?")
            params.append(confidence_clean)

    if search:
        search_pattern = f"%{search.strip()}%"
        conditions.append(
            "(title LIKE ? OR description LIKE ? OR source_text LIKE ?)"
        )
        params.extend([search_pattern, search_pattern, search_pattern])

    if due_before:
        due_before_clean = due_before.strip()
        if not is_valid_iso_date(due_before_clean):
            raise ValueError(
                f"Invalid due_before date format '{due_before}'. Expected YYYY-MM-DD."
            )
        conditions.append("due_date IS NOT NULL AND due_date != '' AND due_date <= ?")
        params.append(due_before_clean)

    if due_after:
        due_after_clean = due_after.strip()
        if not is_valid_iso_date(due_after_clean):
            raise ValueError(
                f"Invalid due_after date format '{due_after}'. Expected YYYY-MM-DD."
            )
        conditions.append("due_date IS NOT NULL AND due_date != '' AND due_date >= ?")
        params.append(due_after_clean)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT * FROM academic_items
        {where_clause}
        ORDER BY
            CASE WHEN due_date IS NOT NULL AND due_date != '' THEN 0 ELSE 1 END ASC,
            due_date ASC,
            id DESC;
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, tuple(params))
        rows = cursor.fetchall()
        items = [row_to_item_dict(r) for r in rows]

        if priority:
            p_clean = priority.strip().upper()
            items = [it for it in items if it.get("priority") == p_clean]
        if importance:
            imp_clean = importance.strip().upper()
            items = [it for it in items if it.get("importance") == imp_clean]
        if urgency:
            u_clean = urgency.strip().upper()
            items = [it for it in items if it.get("urgency") == u_clean]
        if academic_intent:
            ai_clean = academic_intent.strip().lower()
            items = [it for it in items if it.get("academic_intent") == ai_clean]

        return items


def update_academic_item(
    item_id: int,
    updates: dict[str, Any],
    db_path: Optional[Path | str] = None,
) -> Optional[dict[str, Any]]:
    """Safely update an existing academic item's editable fields.

    Parameters:
    - item_id: primary key ID of the task to update.
    - updates: dictionary of column names to new values.
    - db_path: optional database path override.

    Requirements enforced:
    - Only supplied editable fields are modified; unsupplied fields remain untouched.
    - Explicit None is supported for nullable fields (e.g. clearing due_date).
    - Immutable provenance fields (source_text, source_sender, source_timestamp,
      source_filename, created_at, id) are rejected with ValueError.
    - Automatically updates updated_at to the current UTC ISO timestamp.
    - Uses parameterized SQL queries to prevent SQL injection.
    - Returns None if item_id does not exist.
    """
    if not isinstance(item_id, int) or item_id <= 0:
        return None

    # Check for immutable provenance fields
    for field in updates:
        if field in IMMUTABLE_FIELDS:
            raise ValueError(
                f"Field '{field}' is immutable provenance data and cannot be modified."
            )

    # Validate that all update keys are known editable columns
    for field in updates:
        if field not in EDITABLE_COLUMNS:
            raise ValueError(f"Unknown or uneditable field '{field}'.")

    # If updates is empty, verify item exists and return it
    if not updates:
        return get_academic_item_by_id(item_id, db_path=db_path)

    processed: dict[str, Any] = {}

    if "title" in updates:
        val = updates["title"]
        if val is None or not str(val).strip():
            raise ValueError("Item title cannot be null or empty.")
        processed["title"] = str(val).strip()

    if "category" in updates:
        val = updates["category"]
        if val is None:
            raise ValueError("Item category cannot be null.")
        clean_cat = str(val).strip()
        if clean_cat not in ALLOWED_CATEGORIES:
            raise ValueError(
                f"Invalid category '{clean_cat}'. Allowed categories: {', '.join(sorted(ALLOWED_CATEGORIES))}"
            )
        processed["category"] = clean_cat

    if "status" in updates:
        val = updates["status"]
        if val is None:
            raise ValueError("Item status cannot be null.")
        clean_status = str(val).strip().lower()
        if clean_status not in ALLOWED_STATUSES:
            raise ValueError(
                f"Invalid status '{clean_status}'. Allowed statuses: {', '.join(sorted(ALLOWED_STATUSES))}"
            )
        processed["status"] = clean_status

    if "due_date" in updates:
        val = updates["due_date"]
        if val is not None:
            clean_date = str(val).strip()
            if not clean_date:
                processed["due_date"] = None
            elif not is_valid_iso_date(clean_date):
                raise ValueError(
                    f"Invalid due_date format '{clean_date}'. Expected YYYY-MM-DD."
                )
            else:
                processed["due_date"] = clean_date
        else:
            processed["due_date"] = None

    if "description" in updates:
        val = updates["description"]
        processed["description"] = str(val).strip() if val is not None else ""

    if "date_text" in updates:
        val = updates["date_text"]
        processed["date_text"] = str(val).strip() if val is not None else None

    if "date_type" in updates:
        val = updates["date_type"]
        processed["date_type"] = str(val).strip() if val is not None else "unknown"

    if "date_status" in updates:
        val = updates["date_status"]
        processed["date_status"] = str(val).strip() if val is not None else "not_found"

    if "review_required" in updates:
        val = updates["review_required"]
        processed["review_required"] = 1 if val else 0

    if "review_reasons" in updates:
        val = updates["review_reasons"]
        if val is None:
            processed["review_reasons"] = "[]"
        elif isinstance(val, str):
            processed["review_reasons"] = json.dumps([val])
        else:
            processed["review_reasons"] = json.dumps(list(val))

    if "is_actionable" in updates:
        val = updates["is_actionable"]
        processed["is_actionable"] = 1 if val else 0

    if "actionability_type" in updates:
        val = updates["actionability_type"]
        processed["actionability_type"] = str(val).strip() if val is not None else "action_required"

    if "update_type" in updates:
        val = updates["update_type"]
        processed["update_type"] = str(val).strip() if val is not None else None

    if "is_range" in updates:
        val = updates["is_range"]
        processed["is_range"] = 1 if val else 0

    if "previous_due_date" in updates:
        val = updates["previous_due_date"]
        if val is not None:
            clean_prev = str(val).strip()
            if not clean_prev:
                processed["previous_due_date"] = None
            elif not is_valid_iso_date(clean_prev):
                raise ValueError(
                    f"Invalid previous_due_date format '{clean_prev}'. Expected YYYY-MM-DD."
                )
            else:
                processed["previous_due_date"] = clean_prev
        else:
            processed["previous_due_date"] = None

    if "replaces_task_id" in updates:
        val = updates["replaces_task_id"]
        if val is not None:
            try:
                processed["replaces_task_id"] = int(val)
            except (ValueError, TypeError):
                raise ValueError("replaces_task_id must be a valid integer.")
        else:
            processed["replaces_task_id"] = None

    if "importance" in updates:
        val = updates["importance"]
        if val is not None:
            clean_imp = str(val).strip().upper()
            if clean_imp not in ALLOWED_IMPORTANCE_LEVELS:
                raise ValueError(
                    f"Invalid importance '{val}'. Allowed: {', '.join(sorted(ALLOWED_IMPORTANCE_LEVELS))}"
                )
            processed["importance"] = clean_imp
        else:
            processed["importance"] = "UNASSESSED"

    if "academic_intent" in updates:
        val = updates["academic_intent"]
        processed["academic_intent"] = str(val).strip() if val is not None else None

    # confidence and confidence_reasons are now IMMUTABLE_FIELDS.
    # The IMMUTABLE_FIELDS check at the top of this function already rejects them with ValueError.
    # No processing branch is needed here.

    now_iso = datetime.now(timezone.utc).isoformat()
    processed["updated_at"] = now_iso

    set_clauses = [f"{col} = ?" for col in processed]
    params = list(processed.values())
    params.append(item_id)

    update_sql = f"""
        UPDATE academic_items
        SET {', '.join(set_clauses)}
        WHERE id = ?;
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(update_sql, tuple(params))
        conn.commit()
        if cursor.rowcount == 0:
            return None

    return get_academic_item_by_id(item_id, db_path=db_path)


def update_academic_item_status(
    item_id: int,
    new_status: str,
    db_path: Optional[Path | str] = None,
) -> Optional[dict[str, Any]]:
    """Update task status ('pending', 'completed', 'dismissed') and timestamp."""
    clean_status = (new_status or "").strip().lower()
    if clean_status not in ALLOWED_STATUSES:
        raise ValueError(
            f"Invalid status '{new_status}'. Allowed statuses: {', '.join(sorted(ALLOWED_STATUSES))}"
        )

    return update_academic_item(item_id, {"status": clean_status}, db_path=db_path)


def delete_academic_item(
    item_id: int,
    db_path: Optional[Path | str] = None,
) -> bool:
    """Delete a saved academic item by ID. Returns True if deleted, False if not found."""
    delete_sql = "DELETE FROM academic_items WHERE id = ?;"
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(delete_sql, (item_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_confirmed_deadline_items(
    db_path: Optional[Path | str] = None,
) -> list[dict[str, Any]]:
    """Fetch saved items that have a confirmed due date and date_type='deadline'.

    Strictly excludes mentioned dates, event dates, unknown dates, or undated records.
    Also excludes dismissed, cancelled, or superseded items, and cancellation announcements.
    """
    query = """
        SELECT * FROM academic_items
        WHERE due_date IS NOT NULL
          AND due_date != ''
          AND date_type = 'deadline'
          AND status NOT IN ('dismissed', 'cancelled', 'superseded')
          AND (update_type IS NULL OR update_type != 'cancellation')
        ORDER BY due_date ASC, id ASC;
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        # Verify valid ISO date formatting
        confirmed = []
        for r in rows:
            item = row_to_item_dict(r)
            if is_valid_iso_date(item["due_date"]):
                confirmed.append(item)
        return confirmed


def extract_task_core_identifier(title: str, text: str = "") -> str:
    """Extract a normalized core subject/identifier for task matching and association."""
    import re

    combined = f"{title} {text}".strip()

    # Priority 1: Specific numbered academic markers (e.g., Assignment 1, Internal Exam 2, Quiz 3)
    m = re.search(
        r"\b(assignment\s+\d+|internal(?:\s+exam)?\s+\d+|quiz\s+\d+|exam\s+\d+|test\s+\d+|lab(?:\s+exam|\s+test|\s+assignment)?\s+\d+)\b",
        combined,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1).lower().strip())

    # Priority 2: Named milestones/deliverables (e.g. project proposal, term paper, seminar presentation)
    m2 = re.search(
        r"\b(project\s+(?:proposal|phase\s*\d+|report|presentation|submission)|term\s+paper|seminar\s+presentation)\b",
        combined,
        re.IGNORECASE,
    )
    if m2:
        return re.sub(r"\s+", " ", m2.group(1).lower().strip())

    # Priority 3: Clean action words from title to extract subject noun
    cleaned = re.sub(
        r"\b(?:deadline|submission|due\s+date|extended|postponed|rescheduled|revision|cancelled|updated?|notice|announcement)\b",
        "",
        title,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    tokens = [t.lower() for t in cleaned.split() if len(t) > 2]
    return " ".join(tokens)


def find_associated_task(
    data: dict[str, Any],
    db_path: Optional[Path | str] = None,
) -> Optional[dict[str, Any]]:
    """Search for an existing active/pending task in the database matching an update candidate.

    Looks for items that share the core subject/task identifier and are not already
    dismissed, cancelled, or superseded. Matches in reverse ID order (newest first).
    """
    title = (data.get("title") or "").strip()
    source_text = (data.get("source_text") or "").strip()

    core_id = extract_task_core_identifier(title, source_text)
    if not core_id:
        return None

    query = """
        SELECT * FROM academic_items
        WHERE status NOT IN ('dismissed', 'cancelled', 'superseded')
        ORDER BY id DESC;
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        for row in rows:
            item = row_to_item_dict(row)
            item_core = extract_task_core_identifier(item["title"], item.get("source_text", ""))
            if not item_core:
                continue

            if core_id == item_core:
                return item
            if len(core_id) >= 6 and (core_id in item_core or item_core in core_id):
                return item
    return None


def get_task_relationships(
    item_id: int,
    db_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Retrieve full relationship hierarchy and revision lineage for an academic task."""
    current = get_academic_item_by_id(item_id, db_path=db_path)
    if not current:
        return {
            "task_id": item_id,
            "found": False,
            "parent": None,
            "children": [],
            "related": [],
            "history": [],
        }

    parent = None
    if current.get("replaces_task_id"):
        parent = get_academic_item_by_id(current["replaces_task_id"], db_path=db_path)

    children: list[dict[str, Any]] = []
    related: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    core_id = extract_task_core_identifier(current["title"], current.get("source_text", ""))

    query = "SELECT * FROM academic_items WHERE id != ? ORDER BY id ASC;"
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, (item_id,))
        for r in cursor.fetchall():
            it = row_to_item_dict(r)
            if it.get("replaces_task_id") == item_id:
                children.append(it)
            elif core_id:
                other_core = extract_task_core_identifier(it["title"], it.get("source_text", ""))
                if other_core and (core_id == other_core or (len(core_id) >= 6 and (core_id in other_core or other_core in core_id))):
                    if it.get("id") != current.get("replaces_task_id"):
                        related.append(it)

    # Build history timeline (parent -> current -> children)
    if parent:
        history.append({
            "task_id": parent["id"],
            "title": parent["title"],
            "status": parent["status"],
            "due_date": parent.get("due_date"),
            "relationship": "superseded_by_current" if parent["status"] == "superseded" else "predecessor",
        })
    history.append({
        "task_id": current["id"],
        "title": current["title"],
        "status": current["status"],
        "due_date": current.get("due_date"),
        "relationship": "current",
    })
    for ch in children:
        history.append({
            "task_id": ch["id"],
            "title": ch["title"],
            "status": ch["status"],
            "due_date": ch.get("due_date"),
            "relationship": "replacement" if ch["status"] == "pending" else "child",
        })

    return {
        "task_id": item_id,
        "found": True,
        "current": current,
        "parent": parent,
        "children": children,
        "related": related,
        "history": history,
    }


# ==============================================================================
# SMART 2.1 — User Identity, Session Authentication & Role Provisioning
# ==============================================================================


def get_user_by_email(
    email: str,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict[str, Any]]:
    """Retrieve provisioned user by email."""
    if not email:
        return None
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True
    try:
        cur = conn.execute("SELECT * FROM users WHERE LOWER(TRIM(email)) = LOWER(TRIM(?)) LIMIT 1;", (email,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        if close_after:
            conn.close()


def get_user_by_id(
    user_id: int,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict[str, Any]]:
    """Retrieve provisioned user by primary ID."""
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True
    try:
        cur = conn.execute("SELECT * FROM users WHERE id = ? LIMIT 1;", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        if close_after:
            conn.close()


def create_user_session(
    user_id: int,
    session_id: str,
    csrf_token: str,
    expires_at_iso: str,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Store an authenticated user session."""
    now_iso = datetime.now(timezone.utc).isoformat()
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True
    try:
        conn.execute(
            """
            INSERT INTO user_sessions (id, user_id, csrf_token, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            (session_id, user_id, csrf_token, expires_at_iso, now_iso),
        )
        conn.commit()
        return {
            "session_id": session_id,
            "user_id": user_id,
            "csrf_token": csrf_token,
            "expires_at": expires_at_iso,
        }
    finally:
        if close_after:
            conn.close()


def get_session_with_user(
    session_id: str,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict[str, Any]]:
    """Retrieve session record and joined user details if not expired."""
    if not session_id:
        return None
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True
    try:
        cur = conn.execute(
            """
            SELECT s.id as session_id, s.csrf_token, s.expires_at,
                   u.id as user_id, u.email, u.name, u.role, u.status, u.picture,
                   u.is_demo, u.department, u.program
            FROM user_sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ?
            LIMIT 1;
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        res = dict(row)
        now_iso = datetime.now(timezone.utc).isoformat()
        if res["expires_at"] < now_iso:
            # Session expired
            conn.execute("DELETE FROM user_sessions WHERE id = ?;", (session_id,))
            conn.commit()
            return None
        return res
    finally:
        if close_after:
            conn.close()


def delete_user_session(
    session_id: str,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """Invalidate and delete a session."""
    if not session_id:
        return False
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True
    try:
        cur = conn.execute("DELETE FROM user_sessions WHERE id = ?;", (session_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        if close_after:
            conn.close()


# ==============================================================================
# SMART 2.1 — Google Accounts, Opportunities & Classroom Storage Helpers
# ==============================================================================


def save_google_account(
    account_data: dict[str, Any],
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Insert or update a connected Google account with encrypted tokens."""
    email = (account_data.get("email") or "").strip().lower()
    if not email:
        raise ValueError("Google account email is required.")

    now_iso = datetime.now(timezone.utc).isoformat()
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        conn.execute(
            """
            INSERT INTO google_accounts (
                email, name, picture, encrypted_access_token, encrypted_refresh_token,
                token_expiry, scopes, role, is_demo, last_sync_gmail, last_sync_classroom,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                name = COALESCE(excluded.name, google_accounts.name),
                picture = COALESCE(excluded.picture, google_accounts.picture),
                encrypted_access_token = COALESCE(excluded.encrypted_access_token, google_accounts.encrypted_access_token),
                encrypted_refresh_token = COALESCE(excluded.encrypted_refresh_token, google_accounts.encrypted_refresh_token),
                token_expiry = COALESCE(excluded.token_expiry, google_accounts.token_expiry),
                scopes = COALESCE(excluded.scopes, google_accounts.scopes),
                role = COALESCE(excluded.role, google_accounts.role),
                is_demo = excluded.is_demo,
                last_sync_gmail = COALESCE(excluded.last_sync_gmail, google_accounts.last_sync_gmail),
                last_sync_classroom = COALESCE(excluded.last_sync_classroom, google_accounts.last_sync_classroom),
                updated_at = excluded.updated_at;
            """,
            (
                email,
                account_data.get("name"),
                account_data.get("picture"),
                account_data.get("encrypted_access_token"),
                account_data.get("encrypted_refresh_token"),
                account_data.get("token_expiry"),
                account_data.get("scopes"),
                account_data.get("role", "student"),
                1 if account_data.get("is_demo") else 0,
                account_data.get("last_sync_gmail"),
                account_data.get("last_sync_classroom"),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()

        cur = conn.execute("SELECT * FROM google_accounts WHERE email = ? LIMIT 1;", (email,))
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        if close_after:
            conn.close()


def get_google_account(
    email: Optional[str] = None,
    role: Optional[str] = None,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict[str, Any]]:
    """Retrieve connected Google account by email or role."""
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        if email:
            cur = conn.execute("SELECT * FROM google_accounts WHERE email = ? LIMIT 1;", (email.strip().lower(),))
        elif role:
            cur = conn.execute("SELECT * FROM google_accounts WHERE role = ? ORDER BY id DESC LIMIT 1;", (role,))
        else:
            cur = conn.execute("SELECT * FROM google_accounts ORDER BY id DESC LIMIT 1;")
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        if close_after:
            conn.close()


def delete_google_account(
    email: str,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """Disconnect and completely delete a connected Google account."""
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        cur = conn.execute("DELETE FROM google_accounts WHERE email = ?;", (email.strip().lower(),))
        conn.commit()
        return cur.rowcount > 0
    finally:
        if close_after:
            conn.close()


def save_opportunity(
    opp: dict[str, Any],
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Insert or update a competition / academic opportunity."""
    name = (opp.get("name") or "").strip()
    if not name:
        raise ValueError("Opportunity name is required.")

    now_iso = datetime.now(timezone.utc).isoformat()
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        # Deduplicate on (name, organizer) or (source_type, source_id)
        source_id = opp.get("source_id")
        source_type = opp.get("source_type") or "gmail"
        existing = None
        if source_id:
            cur = conn.execute("SELECT id FROM opportunities WHERE source_type = ? AND source_id = ? LIMIT 1;", (source_type, source_id))
            existing = cur.fetchone()
        if not existing:
            cur = conn.execute("SELECT id FROM opportunities WHERE LOWER(TRIM(name)) = LOWER(?) LIMIT 1;", (name,))
            existing = cur.fetchone()

        if existing:
            opp_id = existing["id"]
            conn.execute(
                """
                UPDATE opportunities SET
                    name = ?, organizer = ?, description = ?, eligibility = ?,
                    registration_deadline = ?, event_date = ?, registration_url = ?,
                    source_sender = ?, source_timestamp = ?, evidence_text = ?,
                    confidence = ?, review_status = ?, is_demo = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    name,
                    opp.get("organizer"),
                    opp.get("description"),
                    opp.get("eligibility"),
                    opp.get("registration_deadline"),
                    opp.get("event_date"),
                    opp.get("registration_url"),
                    opp.get("source_sender"),
                    opp.get("source_timestamp"),
                    opp.get("evidence_text"),
                    opp.get("confidence", "HIGH"),
                    opp.get("review_status", "confirmed"),
                    1 if opp.get("is_demo") else 0,
                    now_iso,
                    opp_id,
                ),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO opportunities (
                    name, organizer, description, eligibility, registration_deadline,
                    event_date, registration_url, source_type, source_id, source_sender,
                    source_timestamp, evidence_text, confidence, review_status, is_demo,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    name,
                    opp.get("organizer"),
                    opp.get("description"),
                    opp.get("eligibility"),
                    opp.get("registration_deadline"),
                    opp.get("event_date"),
                    opp.get("registration_url"),
                    source_type,
                    source_id,
                    opp.get("source_sender"),
                    opp.get("source_timestamp"),
                    opp.get("evidence_text"),
                    opp.get("confidence", "HIGH"),
                    opp.get("review_status", "confirmed"),
                    1 if opp.get("is_demo") else 0,
                    now_iso,
                    now_iso,
                ),
            )
            opp_id = cur.lastrowid

        conn.commit()
        cur = conn.execute("SELECT * FROM opportunities WHERE id = ?;", (opp_id,))
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        if close_after:
            conn.close()


def list_opportunities(
    student_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    include_demo: bool = True,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict[str, Any]]:
    """List competition opportunities with student's personal status attached."""
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        params: list[Any] = []
        where_clauses: list[str] = []
        if not include_demo:
            where_clauses.append("o.is_demo = 0")

        base_sql = """
            SELECT o.*,
                   COALESCE(s.status, 'discovered') AS student_status,
                   s.evidence_notes AS status_evidence_notes,
                   s.confirmation_source_ref,
                   s.updated_at AS status_updated_at
            FROM opportunities o
            LEFT JOIN student_opportunity_statuses s
              ON o.id = s.opportunity_id
              AND (s.student_id = ? OR ? IS NULL)
        """
        params.extend([student_id, student_id])

        if where_clauses:
            base_sql += " WHERE " + " AND ".join(where_clauses)

        base_sql += " ORDER BY o.registration_deadline ASC NULLS LAST, o.id DESC;"
        cur = conn.execute(base_sql, params)
        rows = [dict(r) for r in cur.fetchall()]

        if status_filter and status_filter.upper() != "ALL":
            clean_sf = status_filter.strip().lower()
            rows = [r for r in rows if r.get("student_status", "").lower() == clean_sf]

        return rows
    finally:
        if close_after:
            conn.close()


ALLOWED_OPPORTUNITY_STATUSES = {
    "discovered",
    "interested",
    "registration_pending",
    "registered",
    "declined",
    "attended",
    "not_attended",
    "expired",
}


def update_student_opportunity_status(
    student_id: str,
    opportunity_id: int,
    status: str,
    evidence_notes: str = "",
    confirmation_ref: str = "",
    updated_by: Optional[str] = None,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Update or insert student's participation status for an opportunity."""
    clean_student = (student_id or "").strip().lower()
    if not clean_student:
        raise ValueError("student_id is required.")
    clean_status = (status or "").strip().lower()
    if clean_status not in ALLOWED_OPPORTUNITY_STATUSES:
        raise ValueError(f"Invalid opportunity status '{clean_status}'. Allowed: {', '.join(sorted(ALLOWED_OPPORTUNITY_STATUSES))}")

    now_iso = datetime.now(timezone.utc).isoformat()
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        conn.execute(
            """
            INSERT INTO student_opportunity_statuses (
                student_id, opportunity_id, status, evidence_notes, confirmation_source_ref, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(student_id, opportunity_id) DO UPDATE SET
                status = excluded.status,
                evidence_notes = COALESCE(excluded.evidence_notes, student_opportunity_statuses.evidence_notes),
                confirmation_source_ref = COALESCE(excluded.confirmation_source_ref, student_opportunity_statuses.confirmation_source_ref),
                updated_by = COALESCE(excluded.updated_by, student_opportunity_statuses.updated_by),
                updated_at = excluded.updated_at;
            """,
            (
                clean_student,
                opportunity_id,
                clean_status,
                evidence_notes,
                confirmation_ref,
                updated_by or clean_student,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()

        cur = conn.execute(
            """
            SELECT s.*, o.name AS opportunity_name, o.registration_deadline
            FROM student_opportunity_statuses s
            JOIN opportunities o ON s.opportunity_id = o.id
            WHERE s.student_id = ? AND s.opportunity_id = ? LIMIT 1;
            """,
            (clean_student, opportunity_id),
        )
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        if close_after:
            conn.close()


def get_teacher_opportunities_overview(
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Retrieve authorized course/class level overview of student opportunity participation."""
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        # Aggregated stats across student participation
        cur = conn.execute(
            """
            SELECT s.status, COUNT(*) AS count
            FROM student_opportunity_statuses s
            GROUP BY s.status;
            """
        )
        status_counts = {r["status"]: r["count"] for r in cur.fetchall()}

        # Detailed participation list (student identity, opportunity, status, updated_at)
        cur = conn.execute(
            """
            SELECT s.id, s.student_id, s.opportunity_id, o.name AS opportunity_name,
                   o.organizer, o.registration_deadline, s.status, s.evidence_notes,
                   s.confirmation_source_ref, s.updated_at
            FROM student_opportunity_statuses s
            JOIN opportunities o ON s.opportunity_id = o.id
            ORDER BY s.updated_at DESC;
            """
        )
        participation_records = [dict(r) for r in cur.fetchall()]

        return {
            "status_counts": status_counts,
            "total_engagements": sum(status_counts.values()),
            "participations": participation_records,
        }
    finally:
        if close_after:
            conn.close()


def save_classroom_course(
    course: dict[str, Any],
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Insert or update Google Classroom course."""
    cid = str(course.get("id") or "").strip()
    name = (course.get("name") or "").strip()
    if not cid or not name:
        raise ValueError("Course id and name are required.")

    now_iso = datetime.now(timezone.utc).isoformat()
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        conn.execute(
            """
            INSERT INTO classroom_courses (
                id, name, section, description_heading, room, owner_id, teacher_email,
                user_role, alternate_link, is_demo, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                section = COALESCE(excluded.section, classroom_courses.section),
                description_heading = COALESCE(excluded.description_heading, classroom_courses.description_heading),
                room = COALESCE(excluded.room, classroom_courses.room),
                owner_id = COALESCE(excluded.owner_id, classroom_courses.owner_id),
                teacher_email = COALESCE(excluded.teacher_email, classroom_courses.teacher_email),
                user_role = COALESCE(excluded.user_role, classroom_courses.user_role),
                alternate_link = COALESCE(excluded.alternate_link, classroom_courses.alternate_link),
                is_demo = excluded.is_demo,
                updated_at = excluded.updated_at;
            """,
            (
                cid,
                name,
                course.get("section"),
                course.get("description_heading"),
                course.get("room"),
                course.get("owner_id"),
                course.get("teacher_email"),
                course.get("user_role", "student"),
                course.get("alternate_link"),
                1 if course.get("is_demo") else 0,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM classroom_courses WHERE id = ?;", (cid,))
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        if close_after:
            conn.close()


def list_classroom_courses(
    role: Optional[str] = None,
    include_demo: bool = True,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict[str, Any]]:
    """List Google Classroom courses accessible to the user."""
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        params: list[Any] = []
        where: list[str] = []
        if role:
            role_clean = role.strip().lower()
            if role_clean == "teacher":
                where.append("(user_role = 'teacher' OR teacher_email IS NOT NULL)")
            elif role_clean == "student":
                where.append("(user_role = 'student' OR is_demo = 1)")
            else:
                where.append("user_role = ?")
                params.append(role_clean)
        if not include_demo:
            where.append("is_demo = 0")

        sql = "SELECT * FROM classroom_courses"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY name ASC;"

        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        if close_after:
            conn.close()


def save_classroom_coursework(
    cw: dict[str, Any],
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Insert or update Google Classroom coursework item."""
    cw_id = str(cw.get("id") or "").strip()
    course_id = str(cw.get("course_id") or "").strip()
    title = (cw.get("title") or "").strip()
    if not cw_id or not course_id or not title:
        raise ValueError("coursework id, course_id, and title are required.")

    now_iso = datetime.now(timezone.utc).isoformat()
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        conn.execute(
            """
            INSERT INTO classroom_coursework (
                id, course_id, title, description, due_date, due_time, max_points,
                work_type, state, alternate_link, is_demo, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                description = COALESCE(excluded.description, classroom_coursework.description),
                due_date = COALESCE(excluded.due_date, classroom_coursework.due_date),
                due_time = COALESCE(excluded.due_time, classroom_coursework.due_time),
                max_points = COALESCE(excluded.max_points, classroom_coursework.max_points),
                work_type = COALESCE(excluded.work_type, classroom_coursework.work_type),
                state = COALESCE(excluded.state, classroom_coursework.state),
                alternate_link = COALESCE(excluded.alternate_link, classroom_coursework.alternate_link),
                is_demo = excluded.is_demo,
                updated_at = excluded.updated_at;
            """,
            (
                cw_id,
                course_id,
                title,
                cw.get("description"),
                cw.get("due_date"),
                cw.get("due_time"),
                cw.get("max_points"),
                cw.get("work_type", "ASSIGNMENT"),
                cw.get("state", "PUBLISHED"),
                cw.get("alternate_link"),
                1 if cw.get("is_demo") else 0,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM classroom_coursework WHERE id = ?;", (cw_id,))
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        if close_after:
            conn.close()


def list_classroom_coursework(
    course_id: Optional[str] = None,
    include_demo: bool = True,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict[str, Any]]:
    """List coursework items, optionally filtered by course."""
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        params: list[Any] = []
        where: list[str] = []
        if course_id:
            where.append("cw.course_id = ?")
            params.append(course_id)
        if not include_demo:
            where.append("cw.is_demo = 0")

        sql = """
            SELECT cw.*, c.name AS course_name
            FROM classroom_coursework cw
            JOIN classroom_courses c ON cw.course_id = c.id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY cw.due_date ASC NULLS LAST, cw.id DESC;"

        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        if close_after:
            conn.close()


def save_classroom_submission(
    sub: dict[str, Any],
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Insert or update Google Classroom student submission."""
    sub_id = str(sub.get("id") or "").strip()
    course_id = str(sub.get("course_id") or "").strip()
    cw_id = str(sub.get("coursework_id") or "").strip()
    student_id = str(sub.get("student_id") or "").strip()
    if not sub_id or not course_id or not cw_id or not student_id:
        raise ValueError("submission id, course_id, coursework_id, and student_id are required.")

    now_iso = datetime.now(timezone.utc).isoformat()
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        conn.execute(
            """
            INSERT INTO classroom_submissions (
                id, course_id, coursework_id, student_id, student_name, state,
                assigned_grade, late, alternate_link, is_demo, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                student_name = COALESCE(excluded.student_name, classroom_submissions.student_name),
                state = excluded.state,
                assigned_grade = COALESCE(excluded.assigned_grade, classroom_submissions.assigned_grade),
                late = excluded.late,
                alternate_link = COALESCE(excluded.alternate_link, classroom_submissions.alternate_link),
                is_demo = excluded.is_demo,
                updated_at = excluded.updated_at;
            """,
            (
                sub_id,
                course_id,
                cw_id,
                student_id,
                sub.get("student_name"),
                sub.get("state", "NEW"),
                sub.get("assigned_grade"),
                1 if sub.get("late") else 0,
                sub.get("alternate_link"),
                1 if sub.get("is_demo") else 0,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM classroom_submissions WHERE id = ?;", (sub_id,))
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        if close_after:
            conn.close()


def list_classroom_submissions(
    course_id: Optional[str] = None,
    student_id: Optional[str] = None,
    include_demo: bool = True,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict[str, Any]]:
    """List coursework submissions with security isolation by student_id or course_id."""
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        params: list[Any] = []
        where: list[str] = []
        if course_id:
            where.append("s.course_id = ?")
            params.append(course_id)
        if student_id:
            where.append("s.student_id = ?")
            params.append(student_id.strip().lower())
        if not include_demo:
            where.append("s.is_demo = 0")

        sql = """
            SELECT s.*, cw.title AS coursework_title, cw.due_date, cw.max_points, c.name AS course_name
            FROM classroom_submissions s
            JOIN classroom_coursework cw ON s.coursework_id = cw.id
            JOIN classroom_courses c ON s.course_id = c.id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY cw.due_date ASC NULLS LAST, s.id DESC;"

        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        if close_after:
            conn.close()


def get_teacher_coursework_overview(
    teacher_email: Optional[str] = None,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict[str, Any]]:
    """Return teacher course progress overview, restricted to explicitly authorized courses."""
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        params: list[Any] = []
        where: list[str] = []
        if teacher_email:
            where.append("(LOWER(c.teacher_email) = ? OR LOWER(c.owner_id) = ? OR c.user_role = 'teacher')")
            params.append(teacher_email.strip().lower())
            params.append(teacher_email.strip().lower())
        else:
            where.append("(c.user_role = 'teacher' OR c.teacher_email IS NOT NULL)")

        sql = f"""
            SELECT c.id AS course_id, c.name AS course_name, c.section, c.is_demo,
                   COUNT(DISTINCT cw.id) AS total_assignments,
                   COUNT(DISTINCT s.id) AS total_submissions,
                   SUM(CASE WHEN s.state = 'TURNED_IN' THEN 1 ELSE 0 END) AS turned_in_count,
                   SUM(CASE WHEN s.state = 'RETURNED' THEN 1 ELSE 0 END) AS graded_count,
                   SUM(CASE WHEN s.state IN ('NEW', 'CREATED') THEN 1 ELSE 0 END) AS pending_count
            FROM classroom_courses c
            LEFT JOIN classroom_coursework cw ON c.id = cw.course_id
            LEFT JOIN classroom_submissions s ON cw.id = s.coursework_id
            {"WHERE " + " AND ".join(where) if where else ""}
            GROUP BY c.id;
        """
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        if close_after:
            conn.close()


def save_study_material(
    mat: dict[str, Any],
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Insert study material record (Gmail attachment or Classroom material)."""
    title = (mat.get("title") or mat.get("file_name") or "").strip()
    file_name = (mat.get("file_name") or title).strip()
    source_type = (mat.get("source_type") or "gmail_attachment").strip()
    if not title or not file_name:
        raise ValueError("Material title and file_name are required.")

    now_iso = datetime.now(timezone.utc).isoformat()
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        cur = conn.execute(
            """
            INSERT INTO study_materials (
                title, file_name, file_type, file_size, file_url, source_type,
                source_id, course_id, course_name, uploaded_by, is_demo, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                title,
                file_name,
                mat.get("file_type"),
                mat.get("file_size"),
                mat.get("file_url"),
                source_type,
                mat.get("source_id"),
                mat.get("course_id"),
                mat.get("course_name"),
                mat.get("uploaded_by"),
                1 if mat.get("is_demo") else 0,
                now_iso,
            ),
        )
        conn.commit()
        mat_id = cur.lastrowid
        cur = conn.execute("SELECT * FROM study_materials WHERE id = ?;", (mat_id,))
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        if close_after:
            conn.close()


def list_study_materials(
    course_id: Optional[str] = None,
    source_type: Optional[str] = None,
    include_demo: bool = True,
    db_path: Optional[Path | str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict[str, Any]]:
    """List study materials, optionally filtered by course or source."""
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        params: list[Any] = []
        where: list[str] = []
        if course_id:
            where.append("course_id = ?")
            params.append(course_id)
        if source_type:
            where.append("source_type = ?")
            params.append(source_type.strip().lower())
        if not include_demo:
            where.append("is_demo = 0")

        sql = "SELECT * FROM study_materials"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC;"

        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        if close_after:
            conn.close()


# Ensure default database schema is safely initialized on import
try:
    init_db()
except Exception:
    pass

