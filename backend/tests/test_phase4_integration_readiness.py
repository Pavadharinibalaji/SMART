"""Phase 4.5 Integration Readiness Test Suite.

Verifies:
1. Normalized SourceMessage contract, immutability, and serialization.
2. Lightweight SourceAdapter implementations (WhatsApp, Gmail, Google Classroom, Manual).
3. Source adapter registry and extensibility.
4. Extractor integration with source messages and source metadata preservation.
5. Candidate HMAC token binding of source_type and source_id.
6. Server-side authoritative source provenance enforcement during task persistence.
7. Source-aware deduplication (stable source_id matching and fallback matching).
8. Database persistence, retrieval, and source_type filtering.
9. Multi-source extraction API endpoint (POST /api/extract-academic-source).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest
from fastapi.testclient import TestClient

from database import (
    get_db_connection,
    init_db,
    list_academic_items,
    save_academic_item,
    find_duplicate_item,
    get_academic_item_by_id,
)
from extractor import (
    create_candidate_token,
    extract_academic_items,
    verify_candidate_token,
)
from main import app
from source_adapters import (
    SourceMessage,
    SourceAdapter,
    WhatsAppAdapter,
    GmailAdapter,
    GoogleClassroomAdapter,
    ManualAdapter,
    get_source_adapter,
    register_source_adapter,
    ALLOWED_SOURCE_TYPES,
)


@pytest.fixture
def temp_db(tmp_path: Path):
    """Provide a fresh isolated SQLite database fixture."""
    db_file = tmp_path / "test_integration_readiness.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def client(temp_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide a FastAPI TestClient configured with isolated database."""
    monkeypatch.setenv("SMART_DB_PATH", str(temp_db))
    return TestClient(app)


# ==============================================================================
# 1. SourceMessage Contract & Adapter Architecture
# ==============================================================================


def test_source_message_contract():
    """Verify SourceMessage fields, defaults, and conversion methods."""
    msg = SourceMessage(
        source_type="gmail",
        source_id="msg-101",
        source_sender="prof@university.edu",
        source_timestamp="2026-11-23T10:00:00Z",
        source_text="Final project submission is due on 2026-12-05.",
        source_filename="inbox.json",
        source_metadata={"thread_id": "th-99", "labels": ["INBOX", "UNREAD"]},
    )
    assert msg.source_type == "gmail"
    assert msg.source_id == "msg-101"
    assert msg.source_sender == "prof@university.edu"
    assert msg.source_timestamp == "2026-11-23T10:00:00Z"
    assert "Final project" in msg.source_text
    assert msg.source_filename == "inbox.json"
    assert msg.source_metadata["thread_id"] == "th-99"

    d = msg.to_dict()
    assert d["source_type"] == "gmail"
    assert d["source_id"] == "msg-101"
    assert d["text"] == msg.source_text
    assert d["sender"] == msg.source_sender
    assert d["timestamp_text"] == msg.source_timestamp

    reconstructed = SourceMessage.from_dict(d)
    assert reconstructed.source_type == msg.source_type
    assert reconstructed.source_id == msg.source_id
    assert reconstructed.source_text == msg.source_text
    assert reconstructed.source_sender == msg.source_sender


def test_source_adapters_registry():
    """Verify registry retrieval and unknown adapter rejection."""
    assert isinstance(get_source_adapter("whatsapp"), WhatsAppAdapter)
    assert isinstance(get_source_adapter("gmail"), GmailAdapter)
    assert isinstance(get_source_adapter("google_classroom"), GoogleClassroomAdapter)
    assert isinstance(get_source_adapter("manual"), ManualAdapter)

    with pytest.raises(ValueError, match="Unsupported source_type"):
        get_source_adapter("moodle")


def test_whatsapp_adapter_parsing():
    """Verify WhatsAppAdapter parses WhatsApp chat text into SourceMessages."""
    adapter = WhatsAppAdapter()
    raw = (
        "20/11/2026, 14:30 - Dr. Smith: Assignment 3 is due on 27/11/2026.\n"
        "20/11/2026, 14:32 - Alice: Thank you Dr. Smith.\n"
    )
    messages = adapter.parse(raw, filename="cs101_chat.txt")
    assert len(messages) >= 2
    assert messages[0].source_type == "whatsapp"
    assert messages[0].source_sender == "Dr. Smith"
    assert "Assignment 3" in messages[0].source_text
    assert messages[0].source_filename == "cs101_chat.txt"


def test_gmail_adapter_parsing():
    """Verify GmailAdapter parses both structured payloads and raw text."""
    adapter = GmailAdapter()

    # Case A: Structured JSON payload mimicking Gmail API message
    payload = {
        "id": "18c2a9f1b2c",
        "threadId": "18c2a9f1b2c",
        "sender": "prof.alan@univ.edu",
        "subject": "Midterm Exam Notice",
        "snippet": "The midterm exam will take place on 2026-12-01.",
        "internalDate": "2026-11-20T09:00:00Z",
    }
    msgs = adapter.parse(payload)
    assert len(msgs) == 1
    assert msgs[0].source_type == "gmail"
    assert msgs[0].source_id == "18c2a9f1b2c"
    assert msgs[0].source_sender == "prof.alan@univ.edu"
    assert "Midterm Exam Notice" in msgs[0].source_text
    assert msgs[0].source_metadata.get("subject") == "Midterm Exam Notice"

    # Case B: Raw email string with RFC headers
    email_text = (
        "From: registrar@univ.edu\n"
        "Date: 2026-11-20 10:00:00\n"
        "Subject: Spring Registration\n\n"
        "Course registration starts on Monday."
    )
    raw_msgs = adapter.parse(email_text)
    assert len(raw_msgs) == 1
    assert raw_msgs[0].source_type == "gmail"
    assert raw_msgs[0].source_sender == "registrar@univ.edu"
    assert "Course registration" in raw_msgs[0].source_text


def test_google_classroom_adapter_parsing():
    """Verify GoogleClassroomAdapter parses coursework and announcement objects."""
    adapter = GoogleClassroomAdapter()
    coursework = [
        {
            "id": "cw-7788",
            "title": "Machine Learning Lab 4",
            "description": "Implement backpropagation. Submission deadline: 2026-11-30.",
            "creatorUserId": "teacher-42",
            "creationTime": "2026-11-20T08:00:00Z",
            "dueDate": {"year": 2026, "month": 11, "day": 30},
            "dueTime": {"hours": 23, "minutes": 59},
            "alternateLink": "https://classroom.google.com/c/123/a/456",
        }
    ]
    msgs = adapter.parse(coursework)
    assert len(msgs) == 1
    assert msgs[0].source_type == "google_classroom"
    assert msgs[0].source_id == "cw-7788"
    assert msgs[0].source_sender == "teacher-42"
    assert "Machine Learning Lab 4" in msgs[0].source_text
    assert msgs[0].source_metadata.get("item_type") == "coursework"


def test_manual_adapter_parsing():
    """Verify ManualAdapter handles raw student pasted text."""
    adapter = ManualAdapter()
    text = "Prof announced that CS201 project report is due on Friday Nov 28."
    msgs = adapter.parse(text, sender="Student Note")
    assert len(msgs) == 1
    assert msgs[0].source_type == "manual"
    assert msgs[0].source_sender == "Student Note"
    assert "CS201 project report" in msgs[0].source_text
    assert msgs[0].source_id is not None  # Auto-generated manual-UUID


# ==============================================================================
# 2. Extractor Integration & HMAC Token Binding
# ==============================================================================


def test_extractor_preserves_source_provenance():
    """Verify extract_academic_items propagates source_type and source_id into candidates."""
    msg = SourceMessage(
        source_type="gmail",
        source_id="gmail-msg-999",
        source_sender="math_dept@univ.edu",
        source_timestamp="2026-11-20T10:00:00Z",
        source_text="Calculus Assignment 5 is due on 2026-11-28.",
    )
    items = extract_academic_items([msg.to_dict()])
    assert len(items) >= 1
    item = items[0]
    assert item["source_type"] == "gmail"
    assert item["source_id"] == "gmail-msg-999"
    assert "candidate_token" in item

    # Verify token embeds source_type and source_id
    verified = verify_candidate_token(item["candidate_token"])
    assert verified is not None
    assert verified["source_type"] == "gmail"
    assert verified["source_id"] == "gmail-msg-999"


def test_candidate_token_source_tamper_proofing(client: TestClient):
    """Verify server overrides or rejects client-altered source_type/source_id."""
    msg = SourceMessage(
        source_type="google_classroom",
        source_id="gc-coursework-3344",
        source_sender="instructor@univ.edu",
        source_timestamp="2026-11-20T12:00:00Z",
        source_text="Physics Lab Quiz 2 is scheduled for 2026-11-27.",
    )
    items = extract_academic_items([msg.to_dict()])
    assert len(items) >= 1
    candidate = items[0]

    # Attempt client spoofing: client changes source_type to 'manual' and source_id to 'fake-id'
    spoofed_save_req = dict(candidate)
    spoofed_save_req["source_type"] = "manual"
    spoofed_save_req["source_id"] = "fake-spoofed-id"

    resp = client.post("/api/academic-items", json=spoofed_save_req)
    assert resp.status_code == 201
    saved = resp.json()

    # The backend must authoritatively restore the HMAC-certified source_type and source_id
    assert saved["source_type"] == "google_classroom"
    assert saved["source_id"] == "gc-coursework-3344"


# ==============================================================================
# 3. Source-Aware Deduplication & Database Persistence
# ==============================================================================


def test_stable_source_id_deduplication(temp_db: Path):
    """Verify deduplication detects identical source_id across edited titles/descriptions."""
    item_1 = {
        "title": "History Essay Outline",
        "category": "Assignment",
        "source_text": "Submit outline by 2026-12-01.",
        "source_type": "google_classroom",
        "source_id": "hist-essay-001",
        "due_date": "2026-12-01",
    }
    saved_1 = save_academic_item(item_1, db_path=temp_db)
    assert saved_1["id"] is not None

    # Duplicate check by source_id: even if text has minor changes, source_id match flags duplicate
    dup = find_duplicate_item(
        source_text="Submit outline revised by 2026-12-01.",
        source_timestamp=None,
        source_sender=None,
        category="Assignment",
        source_type="google_classroom",
        source_id="hist-essay-001",
        db_path=temp_db,
    )
    assert dup is not None
    assert dup["id"] == saved_1["id"]


def test_fallback_deduplication_different_sources(temp_db: Path):
    """Verify fallback deduplication differentiates identical text from different sources."""
    text = "Team meeting on 2026-11-25."
    # Save WhatsApp item
    save_academic_item(
        {
            "title": "Team Meeting",
            "category": "Announcement",
            "source_text": text,
            "source_type": "whatsapp",
            "source_id": None,
        },
        db_path=temp_db,
    )

    # Check duplicate for Manual source with same text
    dup_manual = find_duplicate_item(
        source_text=text,
        source_timestamp=None,
        source_sender=None,
        category="Announcement",
        source_type="manual",
        source_id=None,
        db_path=temp_db,
    )
    assert dup_manual is None

    # Check duplicate for WhatsApp source
    dup_wa = find_duplicate_item(
        source_text=text,
        source_timestamp=None,
        source_sender=None,
        category="Announcement",
        source_type="whatsapp",
        source_id=None,
        db_path=temp_db,
    )
    assert dup_wa is not None


def test_list_academic_items_source_type_filter(temp_db: Path):
    """Verify list_academic_items filters by source_type."""
    save_academic_item(
        {
            "title": "WA Task",
            "category": "Assignment",
            "source_text": "WA Task text",
            "source_type": "whatsapp",
        },
        db_path=temp_db,
    )
    save_academic_item(
        {
            "title": "Gmail Task",
            "category": "Assignment",
            "source_text": "Gmail Task text",
            "source_type": "gmail",
        },
        db_path=temp_db,
    )
    save_academic_item(
        {
            "title": "Manual Task",
            "category": "Assignment",
            "source_text": "Manual Task text",
            "source_type": "manual",
        },
        db_path=temp_db,
    )

    wa_items = list_academic_items(source_type="whatsapp", db_path=temp_db)
    assert len(wa_items) == 1
    assert wa_items[0]["title"] == "WA Task"

    gmail_items = list_academic_items(source_type="gmail", db_path=temp_db)
    assert len(gmail_items) == 1
    assert gmail_items[0]["title"] == "Gmail Task"

    manual_items = list_academic_items(source_type="manual", db_path=temp_db)
    assert len(manual_items) == 1
    assert manual_items[0]["title"] == "Manual Task"


# ==============================================================================
# 4. Multi-Source Extraction Endpoint (POST /api/extract-academic-source)
# ==============================================================================


def test_api_extract_academic_source_manual(client: TestClient):
    """Verify POST /api/extract-academic-source with manual raw text."""
    req = {
        "source_type": "manual",
        "raw_text": "Submit the Software Engineering report on 2026-11-29.",
        "sender": "Self Note",
    }
    resp = client.post("/api/extract-academic-source", json=req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "manual"
    assert data["total_messages"] == 1
    assert data["total_items"] >= 1
    item = data["items"][0]
    assert item["source_type"] == "manual"
    assert item["category"] == "Assignment"
    assert item["due_date"] == "2026-11-29"


def test_api_extract_academic_source_classroom(client: TestClient):
    """Verify POST /api/extract-academic-source with Google Classroom payload."""
    req = {
        "source_type": "google_classroom",
        "payload": [
            {
                "id": "gc-coursework-99",
                "title": "Algorithms Problem Set 3",
                "description": "Due on 2026-12-02 at 5 PM.",
                "creatorUserId": "prof_turing",
                "creationTime": "2026-11-20T10:00:00Z",
            }
        ],
    }
    resp = client.post("/api/extract-academic-source", json=req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "google_classroom"
    assert data["total_items"] >= 1
    item = data["items"][0]
    assert item["source_type"] == "google_classroom"
    assert item["source_id"] == "gc-coursework-99"


# ==============================================================================
# 5. Phase 4.6 Quality & Production Readiness Regressions
# ==============================================================================


def test_multi_task_deduplication_same_gmail_message(client: TestClient):
    """Verify multiple independent tasks extracted from one Gmail message can both be persisted."""
    email_text = (
        "Assignment 1 on Sorting is due on 2026-11-28. "
        "Also, Assignment 2 on Graph Search is due on 2026-12-05."
    )
    msg = SourceMessage(
        source_type="gmail",
        source_id="gmail-batch-001",
        source_sender="prof.algo@univ.edu",
        source_timestamp="2026-11-20T10:00:00Z",
        source_text=email_text,
    )
    items = extract_academic_items([msg.to_dict()])
    assert len(items) == 2, f"Expected 2 extracted candidates, got {len(items)}"

    # Save Candidate 1
    resp1 = client.post("/api/academic-items", json=items[0])
    assert resp1.status_code == 201
    task1 = resp1.json()
    assert task1["id"] is not None

    # Save Candidate 2 (same source_id, same source_type, same category 'Assignment')
    resp2 = client.post("/api/academic-items", json=items[1])
    assert resp2.status_code == 201
    task2 = resp2.json()
    assert task2["id"] is not None
    assert task2["id"] != task1["id"]
    assert task2["title"] != task1["title"]

    # Re-saving Candidate 1 must be rejected as duplicate (HTTP 409)
    resp1_dup = client.post("/api/academic-items", json=items[0])
    assert resp1_dup.status_code == 409
    assert f"Task #{task1['id']}" in resp1_dup.json()["detail"]

    # Re-saving Candidate 2 must be rejected as duplicate (HTTP 409)
    resp2_dup = client.post("/api/academic-items", json=items[1])
    assert resp2_dup.status_code == 409
    assert f"Task #{task2['id']}" in resp2_dup.json()["detail"]


def test_multi_task_deduplication_same_whatsapp_message(client: TestClient):
    """Verify independent tasks extracted from one WhatsApp message can both be persisted."""
    wa_text = "Assignment 1 due on 2026-11-27. Additionally, Assignment 2 due on 2026-12-04."
    items = extract_academic_items([{"text": wa_text, "sender": "Class Rep", "timestamp_text": "20/11/2026, 10:00"}])
    assert len(items) == 2

    resp1 = client.post("/api/academic-items", json=items[0])
    assert resp1.status_code == 201
    saved1 = resp1.json()

    resp2 = client.post("/api/academic-items", json=items[1])
    assert resp2.status_code == 201
    saved2 = resp2.json()
    assert saved2["id"] != saved1["id"]

    # Duplicate check on Candidate 1
    resp1_dup = client.post("/api/academic-items", json=items[0])
    assert resp1_dup.status_code == 409


def test_security_untrusted_manual_cannot_forge_platform_provenance(client: TestClient):
    """Verify client cannot claim external platform provenance without candidate token."""
    spoofed_req = {
        "title": "Forged Midterm",
        "category": "Exam",
        "source_text": "Midterm Exam on 2026-12-01.",
        "source_type": "gmail",  # Spoofed platform without token
        "source_id": "forged-id-123",
    }
    resp = client.post("/api/academic-items", json=spoofed_req)
    assert resp.status_code == 400
    assert "External source provenance" in resp.json()["detail"]


def test_security_candidate_token_source_metadata_cannot_be_overridden(client: TestClient):
    """Verify client-supplied source_metadata cannot override pipeline token metadata."""
    msg = SourceMessage(
        source_type="gmail",
        source_id="gmail-meta-test",
        source_sender="official@univ.edu",
        source_text="Final project submission is due on 2026-12-10.",
        source_metadata={"subject": "Official Notice", "verified_sender": True},
    )
    items = extract_academic_items([msg.to_dict()])
    candidate = items[0]

    tampered_req = dict(candidate)
    tampered_req["source_metadata"] = {"subject": "Hacked Title", "verified_sender": False, "attacker": "evil"}

    resp = client.post("/api/academic-items", json=tampered_req)
    assert resp.status_code == 201
    saved = resp.json()

    # The server authoritatively restores the certified metadata from the token
    assert saved["source_metadata"]["subject"] == "Official Notice"
    assert saved["source_metadata"]["verified_sender"] is True
    assert "attacker" not in saved["source_metadata"]


def test_transactional_association_safety(client: TestClient, temp_db: Path):
    """Verify association replacement executes atomically and does not leave partial state."""
    # 1. Create original task
    item = {
        "title": "Initial Lab Report",
        "category": "Assignment",
        "due_date": "2026-11-25",
        "source_text": "Lab report due on 2026-11-25.",
    }
    saved_orig = save_academic_item(item, db_path=temp_db)
    orig_id = saved_orig["id"]

    # 2. Extract an extension announcement targeting this task
    msg = {
        "text": f"The deadline for assignment #{orig_id} is postponed to 2026-11-30.",
        "sender": "Prof",
        "timestamp_text": "20/11/2026, 12:00",
    }
    candidates = extract_academic_items([msg])
    assert len(candidates) >= 1
    ext_candidate = candidates[0]
    ext_candidate["replaces_task_id"] = orig_id

    # 3. Save extension task
    resp = client.post("/api/academic-items", json=ext_candidate)
    assert resp.status_code == 201
    ext_task = resp.json()
    assert ext_task["replaces_task_id"] == orig_id

    # Verify original task is marked superseded
    orig_updated = get_academic_item_by_id(orig_id, db_path=temp_db)
    assert orig_updated["status"] == "superseded"

    # 4. Attempting to save the extension task AGAIN triggers HTTP 409
    # and MUST NOT alter or corrupt the target task state
    dup_resp = client.post("/api/academic-items", json=ext_candidate)
    assert dup_resp.status_code == 409
    orig_after_dup = get_academic_item_by_id(orig_id, db_path=temp_db)
    assert orig_after_dup["status"] == "superseded"


def test_adapter_empty_and_malformed_resilience():
    """Verify adapters handle empty and malformed payloads gracefully without crashing."""
    wa = get_source_adapter("whatsapp")
    assert wa.parse("") == []
    assert wa.parse(None) == []
    assert wa.parse("Not a whatsapp format message") == []

    gmail = get_source_adapter("gmail")
    assert gmail.parse("") == []
    assert gmail.parse("{}") == []
    assert gmail.parse([]) == []
    assert gmail.parse({"messages": []}) == []
    assert gmail.parse({"subject": "", "body": ""}) == []

    gc = get_source_adapter("google_classroom")
    assert gc.parse("") == []
    assert gc.parse("{}") == []
    assert gc.parse([]) == []
    assert gc.parse({"announcements": []}) == []
    assert gc.parse({"title": "", "description": ""}) == []

    manual = get_source_adapter("manual")
    assert manual.parse("") == []
    assert manual.parse("   ") == []
    assert manual.parse(None) == []

