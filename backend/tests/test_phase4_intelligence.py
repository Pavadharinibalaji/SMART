"""Tests for SMART 2.0 — Phase 4.1: Extraction Intelligence.

Validates:
1. Context-aware academic classification and conversational chatter filtering.
2. Actionability detection (action_required vs informational / fyi).
3. Multi-clause extraction and independent task splitting.
4. Update and contradiction awareness (postponement, extension, cancellation, reschedule).
5. Evidence substring integrity, Unicode occurrence offsets, and HMAC candidate provenance.
6. SQLite persistence and API roundtrip for intelligence fields.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from database import (
    get_db_connection,
    init_db,
    save_academic_item,
    update_academic_item,
    get_academic_item_by_id,
)
from extractor import (
    classify_message,
    create_candidate_token,
    detect_actionability,
    detect_update_type,
    extract_academic_items,
    is_conversational_chatter,
    split_message_into_segments,
    verify_candidate_token,
)
from main import app

client = TestClient(app)


# ==============================================================================
# 1. Conversational Chatter & False Positive Prevention Tests
# ==============================================================================

@pytest.mark.parametrize(
    "text",
    [
        "I completed the assignment.",
        "I have submitted the homework.",
        "I've completed the lab manual.",
        "Already submitted the assignment.",
        "Done with the project submission.",
        "We finished the lab record.",
        "Did anyone submit the assignment?",
        "Has anyone completed assignment 1?",
        "Is tomorrow a holiday?",
        "What is the deadline for assignment?",
        "Assignment discussion tomorrow.",
        "Project discussion today at 4pm.",
        "Doubt clearing session for homework.",
    ],
)
def test_chatter_detection_heuristics(text: str):
    """Verify that peer chatter, inquiries, and meetings without deliverables are detected as chatter."""
    assert is_conversational_chatter(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Please submit assignment 1 by Friday 5pm.",
        "Assignment 1 is due on Monday.",
        "Midterm exam on 24th October 2026.",
        "All students must submit the project report before 28/10/2026.",
        "The exam was postponed.",
        "Workshop on Artificial Intelligence this Saturday.",
        "Google internship applications are open.",
    ],
)
def test_valid_academic_statements_not_chatter(text: str):
    """Verify that legitimate academic tasks and announcements are not flagged as chatter."""
    assert is_conversational_chatter(text) is False


def test_pure_chatter_messages_produce_zero_candidates():
    """Verify that pure conversational messages produce zero false-positive candidates."""
    messages = [
        {"message_id": 1, "sender": "Student A", "timestamp_text": "20/11/2026, 10:00", "text": "I completed the assignment."},
        {"message_id": 2, "sender": "Student B", "timestamp_text": "20/11/2026, 10:01", "text": "Did anyone submit the assignment?"},
        {"message_id": 3, "sender": "Student C", "timestamp_text": "20/11/2026, 10:02", "text": "Is tomorrow a holiday?"},
        {"message_id": 4, "sender": "Student D", "timestamp_text": "20/11/2026, 10:03", "text": "Assignment discussion tomorrow."},
        {"message_id": 5, "sender": "Student E", "timestamp_text": "20/11/2026, 10:04", "text": "Already submitted the homework."},
    ]
    extracted = extract_academic_items(messages)
    assert len(extracted) == 0


def test_mixed_chatter_and_directive_message():
    """Verify that chatter prefix is stripped and legitimate directive is extracted."""
    messages = [
        {
            "message_id": 10,
            "sender": "Student Rep",
            "timestamp_text": "20/11/2026, 09:30",
            "text": "I completed the assignment. But remember to attend the workshop on Saturday.",
        }
    ]
    extracted = extract_academic_items(messages)
    assert len(extracted) == 1
    item = extracted[0]
    assert item["category"] == "Event"
    assert "workshop" in item["title"].lower()
    assert item["evidence_text"] in messages[0]["text"]
    assert "I completed the assignment" not in item["evidence_text"]


# ==============================================================================
# 2. Update Type and Postponement / Cancellation Intelligence Tests
# ==============================================================================

def test_exam_postponed_without_date_is_announcement():
    """The exam was postponed.' must be classified as Announcement, not Exam."""
    text = "The exam was postponed."
    cat, matches = classify_message(text)
    assert cat == "Announcement"

    messages = [
        {
            "message_id": 20,
            "sender": "HOD Office",
            "timestamp_text": "20/11/2026, 11:00",
            "text": text,
        }
    ]
    extracted = extract_academic_items(messages)
    assert len(extracted) == 1
    item = extracted[0]
    assert item["category"] == "Announcement"
    assert item["update_type"] == "postponement"
    assert item["is_actionable"] is False
    assert item["actionability_type"] == "informational"
    assert item["evidence_text"] == text


def test_deadline_extension_update():
    """Verify deadline extension retains Assignment category with extension update_type."""
    text = "Assignment 1 deadline extended to Friday 5pm."
    up_type = detect_update_type(text)
    assert up_type == "extension"

    messages = [
        {
            "message_id": 21,
            "sender": "Course Instructor",
            "timestamp_text": "20/11/2026, 11:30",
            "text": text,
        }
    ]
    extracted = extract_academic_items(messages)
    assert len(extracted) == 1
    item = extracted[0]
    assert item["category"] == "Assignment"
    assert item["update_type"] == "extension"
    assert item["is_actionable"] is True
    assert item["actionability_type"] == "action_required"


def test_cancellation_announcement():
    """Verify cancellation announcement is classified as Announcement with cancellation update_type."""
    text = "Classes are suspended tomorrow due to heavy rain."
    messages = [
        {
            "message_id": 22,
            "sender": "Principal",
            "timestamp_text": "20/11/2026, 12:00",
            "text": text,
        }
    ]
    extracted = extract_academic_items(messages)
    assert len(extracted) == 1
    item = extracted[0]
    assert item["category"] == "Announcement"
    assert item["update_type"] == "cancellation"
    assert item["is_actionable"] is False
    assert item["actionability_type"] == "informational"


def test_rescheduled_exam():
    """Verify rescheduled exam with explicit date."""
    text = "Midterm exam rescheduled to 28/10/2026."
    up_type = detect_update_type(text)
    assert up_type == "rescheduled"

    messages = [
        {
            "message_id": 23,
            "sender": "Exam Cell",
            "timestamp_text": "20/10/2026, 09:00",
            "text": text,
        }
    ]
    extracted = extract_academic_items(messages)
    assert len(extracted) == 1
    item = extracted[0]
    assert item["category"] == "Exam"
    assert item["update_type"] == "rescheduled"
    assert item["due_date"] == "2026-10-28"
    assert item["is_actionable"] is True


# ==============================================================================
# 3. Multi-Clause Extraction Tests
# ==============================================================================

def test_multi_clause_assignment_and_workshop():
    """'Submit your assignment by Thursday and register for the workshop before Saturday.' -> 2 items."""
    text = "Submit your assignment by Thursday and register for the workshop before Saturday."
    messages = [
        {
            "message_id": 30,
            "sender": "Prof. Smith",
            "timestamp_text": "20/11/2026, 08:00",
            "text": text,
        }
    ]
    extracted = extract_academic_items(messages)
    assert len(extracted) == 2

    assign_item = extracted[0]
    workshop_item = extracted[1]

    assert assign_item["category"] == "Assignment"
    assert assign_item["due_date"] == "2026-11-26"
    assert assign_item["evidence_text"] in text
    assert text[assign_item["evidence_start_index"]:assign_item["evidence_end_index"]] == assign_item["evidence_text"]

    assert workshop_item["category"] == "Event"
    assert workshop_item["due_date"] == "2026-11-20"
    assert workshop_item["evidence_text"] in text
    assert text[workshop_item["evidence_start_index"]:workshop_item["evidence_end_index"]] == workshop_item["evidence_text"]

    # Verify non-overlapping evidence spans
    assert assign_item["evidence_end_index"] <= workshop_item["evidence_start_index"]


def test_multi_clause_comma_with_connecting_adverbs():
    """'Please submit assignment 1 by Friday, also register for the hackathon before Sunday.' -> 2 items."""
    text = "Please submit assignment 1 by Friday, also register for the hackathon before Sunday."
    messages = [
        {
            "message_id": 31,
            "sender": "Class Rep",
            "timestamp_text": "20/11/2026, 08:30",
            "text": text,
        }
    ]
    extracted = extract_academic_items(messages)
    assert len(extracted) == 2

    assert extracted[0]["category"] == "Assignment"
    assert extracted[1]["category"] == "Opportunity"
    for item in extracted:
        assert item["evidence_text"] in text
        assert text[item["evidence_start_index"]:item["evidence_end_index"]] == item["evidence_text"]


def test_multi_clause_as_well_as():
    """'Complete your lab manual by tomorrow as well as attend the quiz on Monday.' -> 2 items."""
    text = "Complete your lab manual by tomorrow as well as attend the quiz on Monday."
    messages = [
        {
            "message_id": 32,
            "sender": "Lab Instructor",
            "timestamp_text": "20/11/2026, 08:45",
            "text": text,
        }
    ]
    extracted = extract_academic_items(messages)
    assert len(extracted) == 2

    assert extracted[0]["category"] == "Assignment"
    assert extracted[1]["category"] == "Exam"
    for item in extracted:
        assert item["evidence_text"] in text
        assert text[item["evidence_start_index"]:item["evidence_end_index"]] == item["evidence_text"]


# ==============================================================================
# 4. Actionability & Intelligence Heuristics Tests
# ==============================================================================

def test_detect_actionability_matrix():
    """Verify actionability classification across categories and directives."""
    # Assignment -> actionable
    act, act_type = detect_actionability("Assignment", "Submit lab report", "deadline", "parsed", None)
    assert act is True
    assert act_type == "action_required"

    # Exam -> actionable
    act, act_type = detect_actionability("Exam", "Midterm exam on Monday", "event_date", "parsed", None)
    assert act is True
    assert act_type == "action_required"

    # Postponement without date -> informational
    act, act_type = detect_actionability("Announcement", "Exam postponed", "none", "not_found", "postponement")
    assert act is False
    assert act_type == "informational"

    # Cancellation -> informational
    act, act_type = detect_actionability("Announcement", "Classes cancelled", "none", "not_found", "cancellation")
    assert act is False
    assert act_type == "informational"

    # Pure informational announcement
    act, act_type = detect_actionability("Announcement", "Library timing notice", "none", "not_found", None)
    assert act is False
    assert act_type == "informational"

    # Actionable announcement
    act, act_type = detect_actionability("Announcement", "All students must submit identity forms", "deadline", "parsed", None)
    assert act is True
    assert act_type == "action_required"


# ==============================================================================
# 5. Unicode and HMAC Provenance Integrity
# ==============================================================================

def test_unicode_and_emoji_provenance_binding():
    """Verify that messages with emojis retain exact code-point offsets and token verification."""
    text = "📢 Alert: 🚀 Submit project demo by Friday 5pm and 💻 attend the workshop on Saturday!"
    messages = [
        {
            "message_id": 40,
            "sender": "Coordinator",
            "timestamp_text": "20/11/2026, 14:00",
            "text": text,
        }
    ]
    extracted = extract_academic_items(messages)
    assert len(extracted) == 2

    for item in extracted:
        token = item["candidate_token"]
        assert token is not None
        verified = verify_candidate_token(token)
        assert verified is not None
        assert verified["source_text"] == text
        assert verified["category"] == item["category"]
        assert verified["is_actionable"] == item["is_actionable"]
        assert verified["actionability_type"] == item["actionability_type"]
        assert verified["update_type"] == item["update_type"]
        # Exact Unicode substring verification
        assert text[item["evidence_start_index"]:item["evidence_end_index"]] == item["evidence_text"]


def test_tampered_actionability_fails_token_verification():
    """Verify that tampering with candidate metadata invalidates candidate token."""
    cand = {
        "source_text": "Submit lab manual by tomorrow.",
        "category": "Assignment",
        "evidence_text": "Submit lab manual by tomorrow.",
        "evidence_start_index": 0,
        "evidence_end_index": 30,
        "confidence": "HIGH",
        "confidence_reasons": ["Explicit date"],
        "is_actionable": True,
        "actionability_type": "action_required",
        "update_type": None,
    }
    token = create_candidate_token(cand)
    assert verify_candidate_token(token) is not None

    # Tamper with token payload
    parts = token.split(".", 1)
    raw_json = json.loads(__import__("base64").urlsafe_b64decode(parts[0].encode("ascii")).decode("utf-8"))
    raw_json["is_actionable"] = False
    tampered_b64 = __import__("base64").urlsafe_b64encode(json.dumps(raw_json).encode("utf-8")).decode("ascii")
    tampered_token = f"{tampered_b64}.{parts[1]}"

    assert verify_candidate_token(tampered_token) is None


# ==============================================================================
# 6. SQLite Persistence & API Endpoints
# ==============================================================================

def test_persistence_of_actionability_and_update_fields(tmp_path: Path):
    """Verify that is_actionable, actionability_type, and update_type are stored and retrieved."""
    db_file = tmp_path / "test_phase4.db"
    init_db(db_file)

    source_text = "Midterm exam postponed until further notice."
    item_data = {
        "title": "Postponed Exam Announcement",
        "category": "Announcement",
        "source_text": source_text,
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "is_actionable": False,
        "actionability_type": "informational",
        "update_type": "postponement",
        "_trusted_confidence": "HIGH",
        "_trusted_confidence_reasons": ["Validated postponement"],
        "_trusted_evidence": True,
    }

    saved = save_academic_item(item_data, db_path=db_file)
    assert saved["id"] is not None
    assert saved["is_actionable"] is False
    assert saved["actionability_type"] == "informational"
    assert saved["update_type"] == "postponement"

    # Test update
    updated = update_academic_item(
        saved["id"],
        {"is_actionable": True, "actionability_type": "action_required", "update_type": "rescheduled"},
        db_path=db_file,
    )
    assert updated["is_actionable"] is True
    assert updated["actionability_type"] == "action_required"
    assert updated["update_type"] == "rescheduled"


def test_api_save_candidate_restores_token_actionability(tmp_path: Path, monkeypatch):
    """Verify that POST /api/academic-items restores certified actionability and update_type from token."""
    db_file = tmp_path / "test_api_phase4.db"
    init_db(db_file)
    monkeypatch.setenv("SMART_DB_PATH", str(db_file))

    source_text = "Assignment 1 deadline extended to Friday 5pm."
    cand = {
        "source_text": source_text,
        "category": "Assignment",
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "confidence": "HIGH",
        "confidence_reasons": ["Explicit deadline"],
        "is_actionable": True,
        "actionability_type": "action_required",
        "update_type": "extension",
    }
    token = create_candidate_token(cand)

    payload = {
        "title": "Extended Assignment 1",
        "category": "Assignment",
        "source_text": source_text,
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "candidate_token": token,
    }

    resp = client.post("/api/academic-items", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["is_actionable"] is True
    assert data["actionability_type"] == "action_required"
    assert data["update_type"] == "extension"
    assert data["confidence"] == "HIGH"


# ==============================================================================
# 7. Phase 4.1.1 Audit: Clause-Level Extraction & Legacy Database Compatibility
# ==============================================================================

def test_clause_level_audit_cases_a_through_f():
    """Verify all 6 clause-level audit cases specified in Phase 4.1.1."""
    timestamp = "20/11/2026, 09:00"

    # Case A: Postponement announcement + independent actionable assignment
    case_a_text = "The exam has been postponed. Please submit your assignment by Friday."
    items_a = extract_academic_items([{"message_id": 1, "sender": "Prof", "timestamp_text": timestamp, "text": case_a_text}])
    assert len(items_a) == 2
    assert items_a[0]["category"] == "Announcement"
    assert items_a[0]["is_actionable"] is False
    assert items_a[0]["update_type"] == "postponement"
    assert items_a[0]["evidence_text"] in case_a_text
    assert items_a[1]["category"] == "Assignment"
    assert items_a[1]["is_actionable"] is True
    assert items_a[1]["due_date"] == "2026-11-27"
    assert items_a[1]["evidence_text"] in case_a_text
    assert items_a[0]["evidence_end_index"] <= items_a[1]["evidence_start_index"]

    # Case B: Completed assignment chatter filtered; workshop instruction extracted
    case_b_text = "I completed the assignment, but please register for the workshop by Saturday."
    items_b = extract_academic_items([{"message_id": 2, "sender": "Student", "timestamp_text": timestamp, "text": case_b_text}])
    assert len(items_b) == 1
    assert items_b[0]["category"] == "Event"
    assert items_b[0]["is_actionable"] is True
    assert items_b[0]["due_date"] == "2026-11-21"
    assert "completed the assignment" not in items_b[0]["evidence_text"]
    assert items_b[0]["evidence_text"] in case_b_text

    # Case C: Examination postponed; assignment deadline Friday -> Friday NOT assigned to exam
    case_c_text = "The examination was postponed. The assignment deadline is Friday."
    items_c = extract_academic_items([{"message_id": 3, "sender": "Exam Officer", "timestamp_text": timestamp, "text": case_c_text}])
    assert len(items_c) == 2
    assert items_c[0]["category"] == "Announcement"
    assert items_c[0]["due_date"] is None
    assert items_c[0]["update_type"] == "postponement"
    assert items_c[1]["category"] == "Assignment"
    assert items_c[1]["due_date"] == "2026-11-27"
    assert items_c[1]["is_actionable"] is True
    assert items_c[0]["evidence_end_index"] <= items_c[1]["evidence_start_index"]

    # Case D: Assignment deadline extended to Friday + independent project report upload by Sunday
    case_d_text = "Assignment deadline extended to Friday. Also upload the project report by Sunday."
    items_d = extract_academic_items([{"message_id": 4, "sender": "Instructor", "timestamp_text": timestamp, "text": case_d_text}])
    assert len(items_d) == 2
    assert items_d[0]["category"] == "Assignment"
    assert items_d[0]["update_type"] == "extension"
    assert items_d[0]["due_date"] == "2026-11-27"
    assert items_d[0]["is_actionable"] is True
    assert items_d[1]["category"] == "Assignment"
    assert items_d[1]["due_date"] == "2026-11-22"
    assert items_d[1]["is_actionable"] is True
    assert items_d[0]["evidence_end_index"] <= items_d[1]["evidence_start_index"]

    # Case E: Classes cancelled tomorrow + independent online assignment submission open until Monday
    case_e_text = "Classes are cancelled tomorrow, but the online assignment submission remains open until Monday."
    items_e = extract_academic_items([{"message_id": 5, "sender": "Admin", "timestamp_text": timestamp, "text": case_e_text}])
    assert len(items_e) == 2
    assert items_e[0]["category"] == "Announcement"
    assert items_e[0]["update_type"] == "cancellation"
    assert items_e[0]["is_actionable"] is False
    assert items_e[1]["category"] == "Assignment"
    assert items_e[1]["due_date"] == "2026-11-23"
    assert items_e[1]["is_actionable"] is True
    assert items_e[0]["evidence_end_index"] <= items_e[1]["evidence_start_index"]

    # Case F: Negative instruction (do not submit) filtered; revised assignment instruction extracted
    case_f_text = "Do not submit the old assignment. Submit the revised assignment by Thursday."
    items_f = extract_academic_items([{"message_id": 6, "sender": "TA", "timestamp_text": timestamp, "text": case_f_text}])
    assert len(items_f) == 1
    assert items_f[0]["category"] == "Assignment"
    assert items_f[0]["due_date"] == "2026-11-26"
    assert items_f[0]["is_actionable"] is True
    assert "Do not submit the old assignment" not in items_f[0]["evidence_text"]
    assert items_f[0]["evidence_text"] in case_f_text


def test_legacy_pre_41_database_migration(tmp_path: Path):
    """Verify that migrating a pre-Phase-4.1 database safely classifies legacy informational announcements."""
    import sqlite3
    from database import list_academic_items

    legacy_db_file = tmp_path / "legacy_pre_41.db"

    # Set up exact Phase 3 schema without Phase 4.1 columns
    with sqlite3.connect(str(legacy_db_file)) as conn:
        conn.execute("""
            CREATE TABLE academic_items (
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
                review_required INTEGER NOT NULL DEFAULT 0,
                review_reasons TEXT,
                evidence_text TEXT,
                evidence_start_index INTEGER,
                evidence_end_index INTEGER,
                confidence TEXT DEFAULT 'MEDIUM',
                confidence_reasons TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        # Insert legacy rows pre-Phase-4.1
        conn.execute("""
            INSERT INTO academic_items (title, category, source_text, created_at, updated_at)
            VALUES ('Holiday Circular', 'Announcement', 'College will remain closed tomorrow.', '2026-10-01T00:00:00Z', '2026-10-01T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO academic_items (title, category, source_text, created_at, updated_at)
            VALUES ('Math Assignment', 'Assignment', 'Submit problems 1-10.', '2026-10-01T00:00:00Z', '2026-10-01T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO academic_items (title, category, source_text, created_at, updated_at)
            VALUES ('Midterm Examination', 'Exam', 'Exam scheduled next week.', '2026-10-01T00:00:00Z', '2026-10-01T00:00:00Z');
        """)
        conn.commit()

    # Apply additive migration
    init_db(legacy_db_file)

    # Inspect migrated rows
    items = list_academic_items(db_path=legacy_db_file)
    assert len(items) == 3

    announcement_item = next(it for it in items if it["category"] == "Announcement")
    assignment_item = next(it for it in items if it["category"] == "Assignment")
    exam_item = next(it for it in items if it["category"] == "Exam")

    # Critical requirement: legacy announcement must NOT be converted to action_required!
    assert announcement_item["is_actionable"] is False
    assert announcement_item["actionability_type"] == "informational"

    # Legacy assignments and exams remain actionable tasks
    assert assignment_item["is_actionable"] is True
    assert assignment_item["actionability_type"] == "action_required"
    assert exam_item["is_actionable"] is True
    assert exam_item["actionability_type"] == "action_required"


def test_client_cannot_override_token_intelligence_fields(tmp_path: Path, monkeypatch):
    """Verify that client attempting to alter is_actionable or update_type is overridden by server token."""
    db_file = tmp_path / "test_api_tamper.db"
    init_db(db_file)
    monkeypatch.setenv("SMART_DB_PATH", str(db_file))

    source_text = "The exam was postponed."
    cand = {
        "source_text": source_text,
        "category": "Announcement",
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "confidence": "HIGH",
        "confidence_reasons": ["Validated postponement"],
        "is_actionable": False,
        "actionability_type": "informational",
        "update_type": "postponement",
    }
    token = create_candidate_token(cand)

    # Client attempts to maliciously flip is_actionable to True and change update_type
    tampered_client_payload = {
        "title": "Postponed Exam",
        "category": "Announcement",
        "source_text": source_text,
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "is_actionable": True,
        "actionability_type": "action_required",
        "update_type": "extension",
        "candidate_token": token,
    }

    resp = client.post("/api/academic-items", json=tampered_client_payload)
    assert resp.status_code == 201
    persisted = resp.json()

    # Server must authoritatively enforce verified token values over client-supplied values
    assert persisted["is_actionable"] is False
    assert persisted["actionability_type"] == "informational"
    assert persisted["update_type"] == "postponement"


def test_pre_41_token_backward_compatibility(tmp_path: Path, monkeypatch):
    """Verify that candidate tokens generated under Phase 3 schema are securely accepted with safe defaults."""
    import base64
    import hashlib
    import hmac
    from extractor import get_provenance_secret

    db_file = tmp_path / "test_api_pre41_token.db"
    init_db(db_file)
    monkeypatch.setenv("SMART_DB_PATH", str(db_file))

    # Phase 3 schema: 7 fields (no is_actionable, actionability_type, or update_type)
    source_text = "Submit the term paper by 24/11/2026."
    pre_41_provenance = {
        "source_text": source_text,
        "category": "Assignment",
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "confidence": "HIGH",
        "confidence_reasons": ["Explicit date"],
    }
    raw_json = json.dumps(pre_41_provenance, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(raw_json).decode("ascii")
    sig = hmac.new(get_provenance_secret(), raw_json, hashlib.sha256).hexdigest()
    pre_41_token = f"{payload_b64}.{sig}"

    save_payload = {
        "title": "Term Paper",
        "category": "Assignment",
        "source_text": source_text,
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "candidate_token": pre_41_token,
    }

    resp = client.post("/api/academic-items", json=save_payload)
    assert resp.status_code == 201
    persisted = resp.json()
    assert persisted["category"] == "Assignment"
    assert persisted["confidence"] == "HIGH"
    # Derived safely from category
    assert persisted["is_actionable"] is True
    assert persisted["actionability_type"] == "action_required"


# ==============================================================================
# Phase 4.1.2: Database Migration Idempotency & Legacy Classification Tests
# ==============================================================================


def _create_pre_41_database(db_file: Path):
    """Helper to create a SQLite database mimicking the Phase 3.3.2 schema."""
    import sqlite3

    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE academic_items (
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
            review_required INTEGER NOT NULL DEFAULT 0,
            review_reasons TEXT,
            evidence_text TEXT,
            evidence_start_index INTEGER,
            evidence_end_index INTEGER,
            confidence TEXT DEFAULT 'MEDIUM',
            confidence_reasons TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO academic_items (
            title, category, source_text, created_at, updated_at, confidence
        ) VALUES
        ('Old Announcement', 'Announcement', 'Classes suspended tomorrow.', '2026-11-01T10:00:00Z', '2026-11-01T10:00:00Z', 'HIGH'),
        ('Old Assignment', 'Assignment', 'Submit assignment 1 by Friday.', '2026-11-01T10:00:00Z', '2026-11-01T10:00:00Z', 'HIGH'),
        ('Old Exam', 'Exam', 'Midterm exam next Monday.', '2026-11-01T10:00:00Z', '2026-11-01T10:00:00Z', 'HIGH'),
        ('Manual Task', 'Announcement', '', '2026-11-01T10:00:00Z', '2026-11-01T10:00:00Z', 'UNASSESSED');
        """
    )
    conn.commit()
    conn.close()


def test_phase4_1_2_test_a_legacy_migration(tmp_path: Path):
    """Test A: Pre-Phase-4.1 DB migration applies correctly."""
    from database import init_db, list_academic_items

    db_file = tmp_path / "legacy_migration.db"
    _create_pre_41_database(db_file)

    init_db(db_file)

    items = list_academic_items(db_path=db_file)
    items_by_title = {item["title"]: item for item in items}

    # Announcement: informational
    assert items_by_title["Old Announcement"]["is_actionable"] is False
    assert items_by_title["Old Announcement"]["actionability_type"] == "informational"

    # Assignment: actionable
    assert items_by_title["Old Assignment"]["is_actionable"] is True
    assert items_by_title["Old Assignment"]["actionability_type"] == "action_required"

    # Exam: actionable
    assert items_by_title["Old Exam"]["is_actionable"] is True
    assert items_by_title["Old Exam"]["actionability_type"] == "action_required"

    # Manual task: announcement with empty source_text -> informational
    assert items_by_title["Manual Task"]["is_actionable"] is False
    assert items_by_title["Manual Task"]["actionability_type"] == "informational"

    # Verify schema_migrations table exists and has record
    import sqlite3

    conn = sqlite3.connect(db_file)
    row = conn.execute(
        "SELECT migration_name FROM schema_migrations WHERE migration_name = 'phase_4_1_legacy_classification'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_phase4_1_2_test_b_idempotency(tmp_path: Path):
    """Test B: Running init_db multiple times is strictly idempotent."""
    from database import init_db, list_academic_items

    db_file = tmp_path / "idempotent.db"
    _create_pre_41_database(db_file)

    # Run init_db 3 times
    init_db(db_file)
    init_db(db_file)
    init_db(db_file)

    items = list_academic_items(db_path=db_file)
    items_by_title = {item["title"]: item for item in items}

    assert items_by_title["Old Announcement"]["is_actionable"] is False
    assert items_by_title["Old Announcement"]["actionability_type"] == "informational"
    assert items_by_title["Old Assignment"]["is_actionable"] is True
    assert items_by_title["Old Exam"]["is_actionable"] is True

    import sqlite3

    conn = sqlite3.connect(db_file)
    count = conn.execute(
        "SELECT COUNT(*) FROM schema_migrations WHERE migration_name = 'phase_4_1_legacy_classification'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_phase4_1_2_test_c_new_actionable_announcement(tmp_path: Path):
    """Test C: New Phase 4.1 actionable Announcement remains actionable across repeated init_db calls."""
    from database import get_academic_item_by_id, init_db, save_academic_item

    db_file = tmp_path / "actionable_announcement.db"
    init_db(db_file)

    # Save a new Phase 4.1 actionable announcement
    saved_item = save_academic_item(
        {
            "title": "Mandatory Meeting",
            "category": "Announcement",
            "source_text": "All team members must attend the meeting at 4 PM.",
            "is_actionable": True,
            "actionability_type": "action_required",
            "confidence": "HIGH",
        },
        db_path=db_file,
    )
    item_id = saved_item["id"]

    saved = get_academic_item_by_id(item_id, db_path=db_file)
    assert saved["is_actionable"] is True
    assert saved["actionability_type"] == "action_required"

    # Simulate restart / multiple init_db runs
    init_db(db_file)
    init_db(db_file)

    reloaded = get_academic_item_by_id(item_id, db_path=db_file)
    assert reloaded["is_actionable"] is True, "Actionable announcement was improperly flipped to False!"
    assert reloaded["actionability_type"] == "action_required", "Actionability type was improperly changed!"


def test_phase4_1_2_test_d_informational_announcement(tmp_path: Path):
    """Test D: New Phase 4.1 informational Announcement remains informational across repeated init_db calls."""
    from database import get_academic_item_by_id, init_db, save_academic_item

    db_file = tmp_path / "informational_announcement.db"
    init_db(db_file)

    saved_item = save_academic_item(
        {
            "title": "Campus Closed",
            "category": "Announcement",
            "source_text": "The campus will be closed for the holiday.",
            "is_actionable": False,
            "actionability_type": "informational",
            "confidence": "HIGH",
        },
        db_path=db_file,
    )
    item_id = saved_item["id"]

    saved = get_academic_item_by_id(item_id, db_path=db_file)
    assert saved["is_actionable"] is False
    assert saved["actionability_type"] == "informational"

    # Simulate restart
    init_db(db_file)

    reloaded = get_academic_item_by_id(item_id, db_path=db_file)
    assert reloaded["is_actionable"] is False
    assert reloaded["actionability_type"] == "informational"


def test_phase4_1_2_test_e_partial_migration_recovery(tmp_path: Path):
    """Test E: Database with columns added but migration record missing recovers gracefully."""
    import sqlite3
    from database import init_db, list_academic_items

    db_file = tmp_path / "partial_recovery.db"
    _create_pre_41_database(db_file)

    # Manually add columns without updating data and without schema_migrations table
    conn = sqlite3.connect(db_file)
    conn.execute("ALTER TABLE academic_items ADD COLUMN is_actionable INTEGER;")
    conn.execute("ALTER TABLE academic_items ADD COLUMN actionability_type TEXT;")
    conn.execute("ALTER TABLE academic_items ADD COLUMN update_type TEXT;")
    conn.commit()
    conn.close()

    # Run init_db - should apply migration cleanly and create schema_migrations table
    init_db(db_file)

    items = list_academic_items(db_path=db_file)
    items_by_title = {item["title"]: item for item in items}

    assert items_by_title["Old Announcement"]["is_actionable"] is False
    assert items_by_title["Old Assignment"]["is_actionable"] is True

    # Run again - verify idempotency
    init_db(db_file)
    items_again = list_academic_items(db_path=db_file)
    items_again_by_title = {item["title"]: item for item in items_again}
    assert items_again_by_title["Old Announcement"]["is_actionable"] is False


