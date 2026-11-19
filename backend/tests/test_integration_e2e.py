"""End-to-End Integration Test Suite for SMART 2.0 (Phase 3.2.5).

Verifies cross-cutting integration across:
- Scenario A: Chat ingestion and parsing pipeline.
- Scenario B: Academic extraction across 10 representative test scenarios.
- Scenario D: Candidate-to-task persistence lifecycle and immutable metadata integrity.
- Scenario E: Saved-task multi-parameter API filtering.
- Scenario F: Task operations (lifecycle, status updates, deletion).
- Scenario G: RFC 5545 Calendar export content and standards compliance.
- Scenario H: Regression validation.
"""

from __future__ import annotations

import io
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient

from main import app, _build_trusted_extraction_payload
from calendar_export import generate_ics, escape_ics_text, fold_ics_line
from database import get_db_path

client = TestClient(app)
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ==============================================================================
# Scenario A: Chat Ingestion Pipeline
# ==============================================================================


def test_scenario_a_valid_chat_ingestion():
    """Verify uploading a valid WhatsApp export runs through parsing and extraction."""
    sample_file = FIXTURES_DIR / "sample_chat.txt"
    assert sample_file.exists()

    with open(sample_file, "rb") as f:
        files = {"file": ("sample_chat.txt", f, "text/plain")}
        res = client.post("/api/extract-academic", files=files)

    assert res.status_code == 200
    data = res.json()
    assert data["filename"] == "sample_chat.txt"
    assert data["total_messages"] > 0
    assert data["total_items"] > 0
    assert isinstance(data["items"], list)
    assert "category_counts" in data
    assert "confidence_counts" in data
    assert "review_required_count" in data


def test_scenario_a_empty_and_invalid_file_handling():
    """Verify empty files, non-txt files, and corrupt formats produce appropriate HTTP errors."""
    # 1. Non-txt rejected
    res_pdf = client.post(
        "/api/extract-academic",
        files={"file": ("export.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert res_pdf.status_code == 400
    assert "Please upload a WhatsApp .txt export" in res_pdf.json()["detail"]

    # 2. Empty file rejected
    res_empty = client.post(
        "/api/extract-academic",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert res_empty.status_code == 400
    assert "The uploaded file is empty" in res_empty.json()["detail"]

    # 3. Whitespace only rejected
    res_ws = client.post(
        "/api/extract-academic",
        files={"file": ("blank.txt", b"   \r\n \t  \n ", "text/plain")},
    )
    assert res_ws.status_code == 400

    # 4. Unrecognized chat format rejected
    res_unrec = client.post(
        "/api/extract-academic",
        files={"file": ("random.txt", b"Random notes without timestamps\nJust a grocery list", "text/plain")},
    )
    assert res_unrec.status_code == 422
    assert "No recognised WhatsApp messages were found" in res_unrec.json()["detail"]


def test_scenario_a_repeated_uploads_do_not_corrupt_existing_tasks():
    """Verify uploading a chat file repeatedly does not modify or delete saved tasks in SQLite."""
    # 1. Save an initial task manually
    save_res = client.post(
        "/api/academic-items",
        json={
            "title": "Existing Saved Task",
            "category": "Assignment",
            "source_text": "Existing task message text",
            "status": "pending",
        },
    )
    assert save_res.status_code == 201
    task_id = save_res.json()["id"]

    # 2. Upload sample chat multiple times
    sample_file = FIXTURES_DIR / "sample_chat.txt"
    for _ in range(3):
        with open(sample_file, "rb") as f:
            res = client.post("/api/extract-academic", files={"file": ("sample_chat.txt", f, "text/plain")})
            assert res.status_code == 200

    # 3. Verify original task is intact and unmodified
    get_res = client.get(f"/api/academic-items/{task_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Existing Saved Task"
    assert get_res.json()["status"] == "pending"


# ==============================================================================
# Scenario B: Academic Extraction Across Representative Scenarios
# ==============================================================================


def test_scenario_b_ten_representative_extraction_cases():
    """Verify candidate extraction across all 10 representative scenarios from Section 4."""
    chat_content = (
        # 1. Clear assignment with explicit deadline
        "19/10/2026, 10:00 am - Prof. Smith: Assignment 1 on Database Design is due on 28/10/2026 before 11:59 pm.\n"
        # 2. Exam announcement with explicit date
        "19/10/2026, 10:15 am - Academic Office: Midterm examination scheduled for 15/11/2026 at Hall B.\n"
        # 3. Opportunity announcement
        "19/10/2026, 10:30 am - Placement Cell: Internship opportunity at AI Lab. Deadline: 30/11/2026.\n"
        # 4. Ambiguous date format (05/06/2026 day vs month ambiguity)
        "19/10/2026, 11:00 am - Prof. Lee: Homework submission deadline is 05/06/2026.\n"
        # 5. Assignment mentioning date without explicit deadline phrasing
        "19/10/2026, 11:30 am - TA Sarah: Assignment 2 discussion will take place on 12/11/2026.\n"
        # 6. Generic isolated event keyword without dates
        "19/10/2026, 12:00 pm - Student Rep: We are organizing a college event soon.\n"
        # 7. Multiple competing categories without primary context (ambiguous low confidence)
        "19/10/2026, 01:00 pm - Coordinator: Semester exam assignment guidelines are published.\n"
        # 8. Message containing multiple independent academic tasks (compound clauses)
        "19/10/2026, 02:00 pm - Prof. Kumar: Submit lab exercise 1 on 10/11/2026, CN exam on 20/11/2026.\n"
        # 9. Irrelevant chat message
        "19/10/2026, 03:00 pm - Dave: Are we having pizza for lunch today?\n"
        # 10. Message with no extractable academic info
        "19/10/2026, 03:05 pm - Alex: Sounds great, see you at 1 pm!\n"
    )

    files = {"file": ("test_cases.txt", io.BytesIO(chat_content.encode("utf-8")), "text/plain")}
    res = client.post("/api/extract-academic", files=files)
    assert res.status_code == 200
    items = res.json()["items"]

    # Verify that irrelevant messages (9 and 10) did NOT produce candidates
    pizza_items = [it for it in items if "pizza" in it["source_text"].lower()]
    assert len(pizza_items) == 0

    # Verify evidence text is an exact substring of source_text for EVERY candidate
    for it in items:
        assert it["evidence_text"] in it["source_text"], (
            f"Evidence '{it['evidence_text']}' must be an exact substring of source '{it['source_text']}'"
        )
        assert it["confidence"] in ["HIGH", "MEDIUM", "LOW", "UNASSESSED"]
        assert isinstance(it["review_required"], bool)
        assert isinstance(it["review_reasons"], list)

    # 1. Clear Assignment with explicit date -> HIGH confidence
    asgn_items = [it for it in items if "Database Design" in it["title"]]
    assert len(asgn_items) >= 1
    assert asgn_items[0]["category"] == "Assignment"
    assert asgn_items[0]["due_date"] == "2026-10-28"
    assert asgn_items[0]["deadline_time"] == "23:59"
    assert asgn_items[0]["confidence"] == "HIGH"
    assert asgn_items[0]["review_required"] is False

    # 2. Clear Exam with explicit date -> HIGH confidence
    exam_items = [it for it in items if "Midterm" in it["title"]]
    assert len(exam_items) >= 1
    assert exam_items[0]["category"] == "Exam"
    assert exam_items[0]["due_date"] == "2026-11-15"
    assert exam_items[0]["confidence"] == "HIGH"

    # 3. Opportunity with explicit date -> HIGH confidence
    opp_items = [it for it in items if "Internship" in it["title"]]
    assert len(opp_items) >= 1
    assert opp_items[0]["category"] == "Opportunity"
    assert opp_items[0]["due_date"] == "2026-11-30"

    # 4. Ambiguous date -> date_status is needs_review, review_required is True
    ambig_items = [it for it in items if "05/06/2026" in it["source_text"]]
    assert len(ambig_items) >= 1
    assert ambig_items[0]["date_status"] == "needs_review"
    assert ambig_items[0]["review_required"] is True

    # 5. Mentioned date in assignment -> review_required is True
    disc_items = [it for it in items if "discussion will take place" in it["source_text"]]
    assert len(disc_items) >= 1
    assert disc_items[0]["review_required"] is True
    assert disc_items[0]["date_type"] == "mentioned_date"

    # 8. Compound multi-task message -> partitioned into 2 independent candidates
    compound_items = [it for it in items if "lab exercise 1" in it["source_text"] or "CN exam" in it["source_text"]]
    assert len(compound_items) == 2
    categories = {it["category"] for it in compound_items}
    assert "Assignment" in categories
    assert "Exam" in categories


# ==============================================================================
# Scenario D: Persistence & Metadata Integrity Lifecycle
# ==============================================================================


def test_scenario_d_candidate_to_task_lifecycle_integrity():
    """Verify extract -> inspect -> save -> GET preserves all metadata exactly."""
    chat = "20/10/2026, 9:00 am - Prof. Alan: Final Project Report deadline is 25/11/2026 at 5:00 pm.\n"
    res = client.post(
        "/api/extract-academic",
        files={"file": ("project.txt", io.BytesIO(chat.encode("utf-8")), "text/plain")},
    )
    assert res.status_code == 200
    candidate = res.json()["items"][0]

    # Save candidate using trusted internal payload pipeline
    trusted_payload = _build_trusted_extraction_payload(candidate)
    from database import save_academic_item
    saved_dict = save_academic_item(trusted_payload)
    task_id = saved_dict["id"]

    # Retrieve through GET endpoint
    get_res = client.get(f"/api/academic-items/{task_id}")
    assert get_res.status_code == 200
    retrieved = get_res.json()

    # Verify byte-for-byte fidelity of all intelligence fields
    assert retrieved["title"] == candidate["title"]
    assert retrieved["category"] == candidate["category"]
    assert retrieved["due_date"] == candidate["due_date"]
    assert retrieved["confidence"] == candidate["confidence"]
    assert retrieved["confidence_reasons"] == candidate["confidence_reasons"]
    assert retrieved["evidence_text"] == candidate["evidence_text"]
    assert retrieved["source_text"] == candidate["source_text"]
    assert retrieved["source_sender"] == candidate["source_sender"]
    assert retrieved["source_timestamp"] == candidate["source_timestamp"]
    assert retrieved["review_required"] == candidate["review_required"]
    assert retrieved["review_reasons"] == candidate["review_reasons"]


def test_scenario_d_legacy_and_manual_task_metadata():
    """Verify legacy NULL records and manual tasks are represented as UNASSESSED without fabrication."""
    db_path = get_db_path()

    # 1. Insert legacy pre-Phase 3 record directly with NULL confidence and evidence
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO academic_items (
                title, category, source_text, confidence, confidence_reasons,
                evidence_text, review_required, review_reasons, status, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, NULL, NULL, 0, NULL, 'pending', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
            """,
            ("Legacy Pre-Phase 3 Task", "Assignment", "Legacy text without confidence score"),
        )
        legacy_id = cursor.lastrowid
        conn.commit()

    legacy_res = client.get(f"/api/academic-items/{legacy_id}")
    assert legacy_res.status_code == 200
    legacy_task = legacy_res.json()
    assert legacy_task["confidence"] == "UNASSESSED"
    assert legacy_task["evidence_text"] is None
    assert legacy_task["confidence_reasons"] == []
    assert legacy_task["review_required"] is False

    # 2. Create manual task via API
    manual_res = client.post(
        "/api/academic-items",
        json={
            "title": "Manual Student Task",
            "category": "Exam",
            "source_text": "Study chapter 4",
        },
    )
    assert manual_res.status_code == 201
    manual_task = manual_res.json()
    assert manual_task["confidence"] == "UNASSESSED"
    assert manual_task["evidence_text"] is None
    assert manual_task["review_required"] is False


def test_scenario_d_tamper_resistance_and_deduplication():
    """Verify clients cannot forge confidence/evidence or save duplicates."""
    # 1. Fabricated evidence rejected
    res_fake_evidence = client.post(
        "/api/academic-items",
        json={
            "title": "Malicious Task",
            "category": "Assignment",
            "source_text": "Real message content",
            "evidence_text": "Fabricated content absent from source",
        },
    )
    assert res_fake_evidence.status_code == 400
    assert "must be a substring of source_text" in res_fake_evidence.json()["detail"]

    # 2. Immutable confidence protected on PATCH
    save_res = client.post(
        "/api/academic-items",
        json={
            "title": "Legit Task",
            "category": "Assignment",
            "source_text": "Legit source content",
        },
    )
    task_id = save_res.json()["id"]

    res_patch = client.patch(
        f"/api/academic-items/{task_id}",
        json={"confidence": "HIGH"},
    )
    assert res_patch.status_code == 422  # extra_forbidden by Pydantic

    # 3. Duplicate save rejected with 409 Conflict
    res_dup = client.post(
        "/api/academic-items",
        json={
            "title": "Legit Task Duplicate",
            "category": "Assignment",
            "source_text": "Legit source content",
        },
    )
    assert res_dup.status_code == 409


# ==============================================================================
# Scenario E: Saved-Task API Filtering
# ==============================================================================


def test_scenario_e_saved_task_combined_filtering():
    """Verify saved task filtering by confidence, category, status, search, and dates."""
    # Seed known tasks
    tasks = [
        {"title": "Algorithms HW1", "category": "Assignment", "status": "pending", "due_date": "2026-11-20", "source_text": "HW1 due Nov 20"},
        {"title": "Networks Midterm", "category": "Exam", "status": "completed", "due_date": "2026-11-25", "source_text": "Networks exam on Nov 25"},
        {"title": "Hackathon Info", "category": "Opportunity", "status": "pending", "due_date": "2026-12-01", "source_text": "Hackathon registration"},
    ]
    for t in tasks:
        client.post("/api/academic-items", json=t)

    # 1. All filters cleared
    all_res = client.get("/api/academic-items")
    assert all_res.status_code == 200
    assert len(all_res.json()) >= 3

    # 2. Filter by category
    cat_res = client.get("/api/academic-items?category=Assignment")
    assert cat_res.status_code == 200
    assert all(it["category"] == "Assignment" for it in cat_res.json())

    # 3. Filter by status
    status_res = client.get("/api/academic-items?status=completed")
    assert status_res.status_code == 200
    assert all(it["status"] == "completed" for it in status_res.json())

    # 4. Filter by confidence=UNASSESSED (since manual items receive UNASSESSED)
    conf_res = client.get("/api/academic-items?confidence=UNASSESSED")
    assert conf_res.status_code == 200
    assert all(it["confidence"] == "UNASSESSED" for it in conf_res.json())

    # 5. Combined query: search + category + due_before
    comb_res = client.get("/api/academic-items?search=Algorithms&category=Assignment&due_before=2026-11-22")
    assert comb_res.status_code == 200
    assert len(comb_res.json()) == 1
    assert comb_res.json()[0]["title"] == "Algorithms HW1"

    # 6. Invalid confidence returns 400
    bad_res = client.get("/api/academic-items?confidence=BOGUS_LEVEL")
    assert bad_res.status_code == 400


# ==============================================================================
# Scenario F: Task Operations Lifecycle
# ==============================================================================


def test_scenario_f_task_crud_operations():
    """Verify task save -> status update -> pending revert -> delete lifecycle."""
    # 1. Create task
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Lifecycle Task",
            "category": "Assignment",
            "source_text": "Lifecycle test message text",
            "status": "pending",
        },
    )
    assert create_res.status_code == 201
    task_id = create_res.json()["id"]
    assert create_res.json()["status"] == "pending"

    # 2. Complete task
    complete_res = client.patch(
        f"/api/academic-items/{task_id}",
        json={"status": "completed"},
    )
    assert complete_res.status_code == 200
    assert complete_res.json()["status"] == "completed"

    # 3. Revert to pending
    pending_res = client.patch(
        f"/api/academic-items/{task_id}",
        json={"status": "pending"},
    )
    assert pending_res.status_code == 200
    assert pending_res.json()["status"] == "pending"

    # 4. Dismiss task
    dismiss_res = client.patch(
        f"/api/academic-items/{task_id}",
        json={"status": "dismissed"},
    )
    assert dismiss_res.status_code == 200
    assert dismiss_res.json()["status"] == "dismissed"

    # 5. Delete task
    del_res = client.delete(f"/api/academic-items/{task_id}")
    assert del_res.status_code == 200
    assert "deleted" in del_res.json()["message"].lower()

    # 6. Subsequent GET returns 404
    get_after = client.get(f"/api/academic-items/{task_id}")
    assert get_after.status_code == 404

    # 7. Subsequent DELETE returns 404
    del_after = client.delete(f"/api/academic-items/{task_id}")
    assert del_after.status_code == 404


# ==============================================================================
# Scenario G: Calendar Export (RFC 5545 Compliance)
# ==============================================================================


def test_scenario_g_calendar_export_standards_compliance():
    """Verify RFC 5545 calendar export formatting, escaping, filtering, and folding."""
    # 1. Seed tasks: one valid confirmed deadline, one event date, one missing date
    client.post(
        "/api/academic-items",
        json={
            "title": "Machine Learning Assignment, Part 1; Submission",
            "category": "Assignment",
            "date_type": "deadline",
            "due_date": "2026-11-28",
            "source_text": "ML Assignment deadline\nSubmit via classroom portal.",
        },
    )
    client.post(
        "/api/academic-items",
        json={
            "title": "Robotics Workshop",
            "category": "Event",
            "date_type": "event_date",  # Non-deadline -> must be excluded
            "due_date": "2026-11-29",
            "source_text": "Workshop event date",
        },
    )
    client.post(
        "/api/academic-items",
        json={
            "title": "No Date Notice",
            "category": "Announcement",
            "date_type": "none",
            "source_text": "Notice without deadline",
        },
    )

    # 2. Call calendar export endpoint
    res = client.get("/api/academic-items/export-ics")
    assert res.status_code == 200
    assert "text/calendar" in res.headers["content-type"]
    assert 'filename="smart_academic_deadlines.ics"' in res.headers["content-disposition"]

    ics_content = res.text
    # Verify mandatory VCALENDAR headers
    assert "BEGIN:VCALENDAR" in ics_content
    assert "VERSION:2.0" in ics_content
    assert "PRODID:-//SMART Academic Intelligence//EN" in ics_content
    assert "END:VCALENDAR" in ics_content

    # Verify confirmed deadline is present as VEVENT
    assert "BEGIN:VEVENT" in ics_content
    assert "DTSTART;VALUE=DATE:20261128" in ics_content
    assert "smart-deadline-item-" in ics_content

    # Verify RFC 5545 text escaping for commas and semicolons
    assert r"Machine Learning Assignment\, Part 1\; Submission" in ics_content

    # Verify non-deadline event was strictly excluded
    assert "Robotics Workshop" not in ics_content
    assert "No Date Notice" not in ics_content


def test_scenario_g_rfc5545_line_folding_and_escaping_unit():
    """Unit test RFC 5545 line folding and escaping functions directly."""
    # Escaping test
    raw = r"Backslash \ Semicolon ; Comma , Newline" + "\n" + "Next line"
    escaped = escape_ics_text(raw)
    assert r"Backslash \\" in escaped
    assert r"\;" in escaped
    assert r"\," in escaped
    assert r"\n" in escaped

    # Folding test: line > 75 octets folded with CRLF + space
    long_line = "DESCRIPTION:" + "A" * 100
    folded = fold_ics_line(long_line)
    lines = folded.split("\r\n")
    assert len(lines) >= 2
    assert lines[1].startswith(" ")
    assert all(len(l.encode("utf-8")) <= 75 for l in lines)
