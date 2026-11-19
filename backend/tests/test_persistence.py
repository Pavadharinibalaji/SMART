"""Persistence, task management, and iCalendar export tests for SMART Phase 2."""

from datetime import datetime
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from calendar_export import escape_ics_text, fold_ics_line, generate_ics
from database import (
    get_confirmed_deadline_items,
    get_db_connection,
    init_db,
    save_academic_item,
)
from main import app

client = TestClient(app)


# 1. Database initialization test
def test_database_initialization(tmp_path):
    custom_db = tmp_path / "custom_init.db"
    assert not custom_db.exists()

    init_db(custom_db)
    assert custom_db.exists()

    with get_db_connection(custom_db) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='academic_items';"
        )
        assert cursor.fetchone() is not None

        # Check indexes exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_academic_items%';"
        )
        indexes = {row["name"] for row in cursor.fetchall()}
        assert "idx_academic_items_category" in indexes
        assert "idx_academic_items_status" in indexes
        assert "idx_academic_items_due_date" in indexes


# 2. Saving an academic item
def test_save_academic_item_api():
    payload = {
        "title": "Machine Learning Assignment 1",
        "category": "Assignment",
        "description": "Submit code and report on gradient descent",
        "date_text": "2026-10-30",
        "due_date": "2026-10-30",
        "date_type": "deadline",
        "date_status": "confirmed_explicit",
        "status": "pending",
        "source_sender": "Dr. Andrew",
        "source_timestamp": "2026-10-20 14:30",
        "source_text": "Please submit Assignment 1 on gradient descent by 2026-10-30.",
        "source_filename": "cs_batch.txt",
        "review_required": False,
        "review_reasons": [],
    }

    response = client.post("/api/academic-items", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert data["id"] > 0
    assert data["title"] == payload["title"]
    assert data["category"] == "Assignment"
    assert data["status"] == "pending"
    assert data["due_date"] == "2026-10-30"
    assert data["source_sender"] == "Dr. Andrew"
    assert data["source_filename"] == "cs_batch.txt"
    assert data["created_at"] is not None
    assert data["updated_at"] is not None


# 3. Listing saved items & deterministic ordering
def test_list_saved_items_deterministic_ordering():
    # Insert undated item
    client.post(
        "/api/academic-items",
        json={
            "title": "Undated notice",
            "category": "Announcement",
            "source_text": "Notice without deadline",
            "due_date": None,
        },
    )

    # Insert later deadline
    client.post(
        "/api/academic-items",
        json={
            "title": "Later assignment",
            "category": "Assignment",
            "source_text": "Assignment due Nov 15",
            "due_date": "2026-11-15",
            "date_type": "deadline",
        },
    )

    # Insert earlier deadline
    client.post(
        "/api/academic-items",
        json={
            "title": "Earlier assignment",
            "category": "Assignment",
            "source_text": "Assignment due Oct 28",
            "due_date": "2026-10-28",
            "date_type": "deadline",
        },
    )

    response = client.get("/api/academic-items")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 3

    # Upcoming dated items first chronologically
    assert items[0]["title"] == "Earlier assignment"
    assert items[0]["due_date"] == "2026-10-28"
    assert items[1]["title"] == "Later assignment"
    assert items[1]["due_date"] == "2026-11-15"
    assert items[2]["title"] == "Undated notice"
    assert items[2]["due_date"] is None


# 4. Search and category filters
def test_search_and_category_filters():
    client.post(
        "/api/academic-items",
        json={
            "title": "Operating Systems Midterm",
            "category": "Exam",
            "description": "Hall A seating",
            "source_text": "OS Exam scheduled in Hall A",
            "due_date": "2026-11-05",
        },
    )
    client.post(
        "/api/academic-items",
        json={
            "title": "Hackathon Registration",
            "category": "Opportunity",
            "description": "Register team of 3",
            "source_text": "National level hackathon open for all students",
            "due_date": "2026-11-20",
        },
    )

    # Filter by category Exam
    res = client.get("/api/academic-items?category=Exam")
    assert res.status_code == 200
    exam_items = res.json()
    assert len(exam_items) == 1
    assert exam_items[0]["category"] == "Exam"

    # Search by keyword in title
    res = client.get("/api/academic-items?search=hackathon")
    assert res.status_code == 200
    hack_items = res.json()
    assert len(hack_items) == 1
    assert hack_items[0]["title"] == "Hackathon Registration"

    # Search by keyword in description
    res = client.get("/api/academic-items?search=seating")
    assert res.status_code == 200
    assert len(res.json()) == 1


# 5. Status filters
def test_status_filters():
    res1 = client.post(
        "/api/academic-items",
        json={
            "title": "Task A",
            "category": "Assignment",
            "source_text": "Text A",
            "status": "pending",
        },
    )
    id1 = res1.json()["id"]

    res2 = client.post(
        "/api/academic-items",
        json={
            "title": "Task B",
            "category": "Assignment",
            "source_text": "Text B",
            "status": "pending",
        },
    )
    id2 = res2.json()["id"]

    # Mark id1 as completed
    client.patch(f"/api/academic-items/{id1}", json={"status": "completed"})

    # Filter by pending
    res_pending = client.get("/api/academic-items?status=pending")
    assert res_pending.status_code == 200
    pending_items = res_pending.json()
    assert any(i["id"] == id2 for i in pending_items)
    assert not any(i["id"] == id1 for i in pending_items)

    # Filter by completed
    res_completed = client.get("/api/academic-items?status=completed")
    assert res_completed.status_code == 200
    completed_items = res_completed.json()
    assert any(i["id"] == id1 for i in completed_items)
    assert not any(i["id"] == id2 for i in completed_items)


# 6. Date-range filters
def test_date_range_filters():
    client.post(
        "/api/academic-items",
        json={
            "title": "Oct Item",
            "category": "Assignment",
            "source_text": "Due Oct 25",
            "due_date": "2026-10-25",
        },
    )
    client.post(
        "/api/academic-items",
        json={
            "title": "Nov Item",
            "category": "Assignment",
            "source_text": "Due Nov 10",
            "due_date": "2026-11-10",
        },
    )
    client.post(
        "/api/academic-items",
        json={
            "title": "Dec Item",
            "category": "Assignment",
            "source_text": "Due Dec 05",
            "due_date": "2026-12-05",
        },
    )

    # due_before 2026-11-01
    res = client.get("/api/academic-items?due_before=2026-11-01")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["title"] == "Oct Item"

    # due_after 2026-11-01
    res = client.get("/api/academic-items?due_after=2026-11-01")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    titles = [i["title"] for i in items]
    assert "Nov Item" in titles
    assert "Dec Item" in titles


# 7. Updating task status
def test_update_task_status_lifecycle():
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Project Phase 1",
            "category": "Assignment",
            "source_text": "Submit project phase 1 docs",
            "status": "pending",
        },
    )
    item_id = create_res.json()["id"]
    initial_updated_at = create_res.json()["updated_at"]

    # Change to completed
    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"status": "completed"},
    )
    assert patch_res.status_code == 200
    updated_data = patch_res.json()
    assert updated_data["status"] == "completed"
    assert updated_data["updated_at"] >= initial_updated_at

    # Change to dismissed
    patch_dismissed = client.patch(
        f"/api/academic-items/{item_id}",
        json={"status": "dismissed"},
    )
    assert patch_dismissed.status_code == 200
    assert patch_dismissed.json()["status"] == "dismissed"

    # Change back to pending
    patch_pending = client.patch(
        f"/api/academic-items/{item_id}",
        json={"status": "pending"},
    )
    assert patch_pending.status_code == 200
    assert patch_pending.json()["status"] == "pending"


# 8. Invalid statuses and invalid dates
def test_invalid_status_and_dates_rejected():
    # Invalid category on save
    res = client.post(
        "/api/academic-items",
        json={
            "title": "Invalid Cat",
            "category": "NonexistentCategory",
            "source_text": "Text",
        },
    )
    assert res.status_code == 400
    assert "Invalid category" in res.json()["detail"]

    # Invalid status on save
    res = client.post(
        "/api/academic-items",
        json={
            "title": "Invalid Status",
            "category": "Assignment",
            "status": "bogus_status",
            "source_text": "Text",
        },
    )
    assert res.status_code == 400
    assert "Invalid status" in res.json()["detail"]

    # Invalid due_date format on save
    res = client.post(
        "/api/academic-items",
        json={
            "title": "Bad Date",
            "category": "Assignment",
            "source_text": "Text",
            "due_date": "31-10-2026",  # not YYYY-MM-DD
        },
    )
    assert res.status_code == 400
    assert "Invalid due_date format" in res.json()["detail"]

    # Create valid item to test patch
    valid_res = client.post(
        "/api/academic-items",
        json={
            "title": "Valid item",
            "category": "Assignment",
            "source_text": "Valid text",
        },
    )
    item_id = valid_res.json()["id"]

    # Invalid status on patch
    res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"status": "in_progress"},
    )
    assert res.status_code == 400
    assert "Invalid status" in res.json()["detail"]

    # Invalid query filter category
    res = client.get("/api/academic-items?category=Unknown")
    assert res.status_code == 400

    # Invalid query filter status
    res = client.get("/api/academic-items?status=working")
    assert res.status_code == 400

    # Invalid query date filter
    res = client.get("/api/academic-items?due_before=not-a-date")
    assert res.status_code == 400


# 9. Nonexistent item IDs
def test_nonexistent_item_ids_return_404():
    res_get = client.get("/api/academic-items/999999")
    assert res_get.status_code == 404

    res_patch = client.patch(
        "/api/academic-items/999999",
        json={"status": "completed"},
    )
    assert res_patch.status_code == 404

    res_del = client.delete("/api/academic-items/999999")
    assert res_del.status_code == 404


# 10. Deleting saved items
def test_delete_saved_item():
    res = client.post(
        "/api/academic-items",
        json={
            "title": "To be deleted",
            "category": "Assignment",
            "source_text": "Will be removed",
        },
    )
    item_id = res.json()["id"]

    del_res = client.delete(f"/api/academic-items/{item_id}")
    assert del_res.status_code == 200
    assert del_res.json()["id"] == item_id

    # Verify subsequent GET returns 404
    get_res = client.get(f"/api/academic-items/{item_id}")
    assert get_res.status_code == 404


# 11. Duplicate-save behavior
def test_duplicate_save_rejected_with_conflict():
    item_payload = {
        "title": "Physics Lab Submission",
        "category": "Assignment",
        "source_sender": "TA Sarah",
        "source_timestamp": "2026-10-21 09:00",
        "source_text": "Please submit your Physics lab records by Friday.",
        "source_filename": "physics_group.txt",
        "due_date": "2026-10-24",
    }

    # First save succeeds
    res1 = client.post("/api/academic-items", json=item_payload)
    assert res1.status_code == 201
    first_id = res1.json()["id"]

    # Second save with identical source provenance is rejected with 409
    res2 = client.post("/api/academic-items", json=item_payload)
    assert res2.status_code == 409
    assert "already been saved" in res2.json()["detail"]
    assert str(first_id) in res2.json()["detail"]

    # Genuinely distinct message with same title is allowed
    distinct_payload = dict(item_payload)
    distinct_payload["source_timestamp"] = "2026-10-22 10:00"
    distinct_payload["source_text"] = "Second call: Please submit your Physics lab records."
    res3 = client.post("/api/academic-items", json=distinct_payload)
    assert res3.status_code == 201
    assert res3.json()["id"] != first_id


# 12. Exporting valid deadline items
def test_export_confirmed_deadlines_ics():
    client.post(
        "/api/academic-items",
        json={
            "title": "Final Project Submission",
            "category": "Assignment",
            "description": "Upload zip file to portal",
            "due_date": "2026-11-20",
            "date_type": "deadline",
            "source_sender": "Prof. Miller",
            "source_timestamp": "2026-10-15",
            "source_text": "Final project is due Nov 20, 2026.",
        },
    )

    response = client.get("/api/academic-items/export-ics")
    assert response.status_code == 200
    assert "text/calendar" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    assert "smart_academic_deadlines.ics" in response.headers["content-disposition"]

    ics_body = response.text
    assert "BEGIN:VCALENDAR" in ics_body
    assert "VERSION:2.0" in ics_body
    assert "PRODID:-//SMART Academic Intelligence//EN" in ics_body
    assert "BEGIN:VEVENT" in ics_body
    assert "UID:smart-deadline-item-" in ics_body
    assert "DTSTAMP:" in ics_body
    assert "DTSTART;VALUE=DATE:20261120" in ics_body
    assert "SUMMARY:Final Project Submission" in ics_body
    assert "END:VEVENT" in ics_body
    assert "END:VCALENDAR" in ics_body


# 13. Excluding mentioned dates and undated items from deadline export
def test_export_excludes_non_deadlines():
    # Mentioned date (not a deadline)
    client.post(
        "/api/academic-items",
        json={
            "title": "Guest Lecture Mention",
            "category": "Event",
            "due_date": "2026-11-12",
            "date_type": "mentioned_date",
            "source_text": "Guest lecture was discussed on 2026-11-12",
        },
    )

    # Undated item
    client.post(
        "/api/academic-items",
        json={
            "title": "No date announcement",
            "category": "Announcement",
            "due_date": None,
            "date_type": "none",
            "source_text": "Some general note without date",
        },
    )

    # When NO items have date_type="deadline", export returns 404
    response = client.get("/api/academic-items/export-ics")
    assert response.status_code == 404
    assert "No confirmed deadlines" in response.json()["detail"]


# 14. Correct iCalendar escaping
def test_icalendar_text_escaping():
    raw_text = 'Assignment: Math & Science; Problem #1, 2\\3\nLine 2 with "quotes"\r\nLine 3'
    escaped = escape_ics_text(raw_text)

    # Backslashes escaped
    assert r"\\" in escaped
    # Semicolons escaped
    assert r"\;" in escaped
    # Commas escaped
    assert r"\," in escaped
    # Newlines converted to \n
    assert r"\n" in escaped
    assert "\r" not in escaped

    # Test folding
    long_line = "DESCRIPTION:" + "A" * 120
    folded = fold_ics_line(long_line)
    lines = folded.split("\r\n")
    assert len(lines) > 1
    # Continuation lines start with space
    for line in lines[1:]:
        assert line.startswith(" ")


# ==============================================================================
# Phase 1: Academic Task Editing Tests
# ==============================================================================

# 15. Update task title
def test_update_task_title():
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Initial Title",
            "category": "Assignment",
            "source_text": "Original message text",
            "due_date": "2026-11-01",
        },
    )
    item_id = create_res.json()["id"]
    initial_updated_at = create_res.json()["updated_at"]

    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"title": "Updated Task Title"},
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["title"] == "Updated Task Title"
    assert data["category"] == "Assignment"
    assert data["due_date"] == "2026-11-01"
    assert data["updated_at"] >= initial_updated_at


# 16. Update task description
def test_update_task_description():
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Task for Description Update",
            "category": "Exam",
            "description": "Old short description",
            "source_text": "Exam text",
        },
    )
    item_id = create_res.json()["id"]

    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"description": "Comprehensive instructions: Bring calculator and ID card."},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["description"] == "Comprehensive instructions: Bring calculator and ID card."
    assert patch_res.json()["title"] == "Task for Description Update"


# 17. Update task category
def test_update_task_category():
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Misclassified Item",
            "category": "Announcement",
            "source_text": "Workshop text",
        },
    )
    item_id = create_res.json()["id"]

    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"category": "Event"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["category"] == "Event"


# 18. Update task due date
def test_update_task_due_date():
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Date Update Task",
            "category": "Assignment",
            "source_text": "Assignment text",
            "due_date": "2026-11-01",
        },
    )
    item_id = create_res.json()["id"]

    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"due_date": "2026-11-15"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["due_date"] == "2026-11-15"


# 19. Partial update preserving unsupplied fields
def test_partial_update_preserves_other_fields():
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Preserve Fields Task",
            "category": "Assignment",
            "description": "Important project description",
            "due_date": "2026-11-20",
            "date_text": "Nov 20",
            "date_type": "deadline",
            "status": "pending",
            "source_sender": "Prof. Miller",
            "source_timestamp": "2026-10-15 10:00",
            "source_text": "Original verbatim chat message",
            "source_filename": "chat_export.txt",
        },
    )
    item_id = create_res.json()["id"]

    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"title": "Renamed Title Only"},
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["title"] == "Renamed Title Only"
    assert data["category"] == "Assignment"
    assert data["description"] == "Important project description"
    assert data["due_date"] == "2026-11-20"
    assert data["date_text"] == "Nov 20"
    assert data["date_type"] == "deadline"
    assert data["status"] == "pending"
    assert data["source_sender"] == "Prof. Miller"
    assert data["source_timestamp"] == "2026-10-15 10:00"
    assert data["source_text"] == "Original verbatim chat message"
    assert data["source_filename"] == "chat_export.txt"


# 20. Multiple fields updated together
def test_multiple_fields_updated_together():
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Multi Update Task",
            "category": "Announcement",
            "description": "Initial text",
            "due_date": "2026-11-05",
            "status": "pending",
            "source_text": "Some text",
        },
    )
    item_id = create_res.json()["id"]

    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={
            "title": "Software Engineering Hackathon",
            "category": "Opportunity",
            "description": "Register teams of 4 on the portal",
            "due_date": "2026-12-01",
            "date_type": "deadline",
            "status": "completed",
        },
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["title"] == "Software Engineering Hackathon"
    assert data["category"] == "Opportunity"
    assert data["description"] == "Register teams of 4 on the portal"
    assert data["due_date"] == "2026-12-01"
    assert data["date_type"] == "deadline"
    assert data["status"] == "completed"


# 21. Explicit null handling
def test_update_explicit_null_handling():
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Task with Date to Clear",
            "category": "Assignment",
            "due_date": "2026-11-10",
            "date_text": "10th Nov",
            "description": "Has description",
            "source_text": "Assignment text",
        },
    )
    item_id = create_res.json()["id"]

    # Explicit null due_date clears the due_date
    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"due_date": None},
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["due_date"] is None
    assert data["title"] == "Task with Date to Clear"
    assert data["category"] == "Assignment"

    # Explicit null description clears to empty string
    patch_desc = client.patch(
        f"/api/academic-items/{item_id}",
        json={"description": None},
    )
    assert patch_desc.status_code == 200
    assert patch_desc.json()["description"] == ""


# 22. Invalid category rejected with 422
def test_update_invalid_category_rejected():
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Category Validation Test",
            "category": "Assignment",
            "source_text": "Test text",
        },
    )
    item_id = create_res.json()["id"]

    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"category": "NonexistentCategory"},
    )
    assert patch_res.status_code == 422


# 23. Invalid date rejected with 422
def test_update_invalid_date_rejected():
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Date Validation Test",
            "category": "Assignment",
            "source_text": "Test text",
        },
    )
    item_id = create_res.json()["id"]

    # Non-date string
    patch_bad_str = client.patch(
        f"/api/academic-items/{item_id}",
        json={"due_date": "not-a-real-date"},
    )
    assert patch_bad_str.status_code == 422

    # Non-ISO format (DD/MM/YYYY)
    patch_non_iso = client.patch(
        f"/api/academic-items/{item_id}",
        json={"due_date": "25/11/2026"},
    )
    assert patch_non_iso.status_code == 422


# 24. Nonexistent task ID returns 404
def test_update_nonexistent_task_id_returns_404():
    patch_res = client.patch(
        "/api/academic-items/999999",
        json={"title": "Ghost Task"},
    )
    assert patch_res.status_code == 404
    assert "not found" in patch_res.json()["detail"].lower()


# 25. Immutable provenance fields cannot be modified (rejected with 422)
def test_immutable_provenance_fields_cannot_be_modified():
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Provenance Security Test",
            "category": "Assignment",
            "source_sender": "Authentic Sender",
            "source_timestamp": "2026-10-20 09:00",
            "source_text": "Original unaltered text",
            "source_filename": "authentic.txt",
        },
    )
    item_id = create_res.json()["id"]

    # Attempt to tamper with source_text
    res_text = client.patch(
        f"/api/academic-items/{item_id}",
        json={"source_text": "Tampered source text"},
    )
    assert res_text.status_code == 422

    # Attempt to tamper with source_sender
    res_sender = client.patch(
        f"/api/academic-items/{item_id}",
        json={"source_sender": "Malicious Impersonator"},
    )
    assert res_sender.status_code == 422

    # Attempt to tamper with source_timestamp
    res_ts = client.patch(
        f"/api/academic-items/{item_id}",
        json={"source_timestamp": "1999-01-01 00:00"},
    )
    assert res_ts.status_code == 422

    # Attempt to tamper with source_filename
    res_fn = client.patch(
        f"/api/academic-items/{item_id}",
        json={"source_filename": "fake.txt"},
    )
    assert res_fn.status_code == 422

    # Attempt to tamper with created_at
    res_created = client.patch(
        f"/api/academic-items/{item_id}",
        json={"created_at": "2000-01-01T00:00:00"},
    )
    assert res_created.status_code == 422

    # Attempt to tamper with id
    res_id = client.patch(
        f"/api/academic-items/{item_id}",
        json={"id": 9999},
    )
    assert res_id.status_code == 422

    # Verify original record remained completely unmodified
    item_res = client.get(f"/api/academic-items/{item_id}")
    assert item_res.status_code == 200
    record = item_res.json()
    assert record["source_sender"] == "Authentic Sender"
    assert record["source_timestamp"] == "2026-10-20 09:00"
    assert record["source_text"] == "Original unaltered text"
    assert record["source_filename"] == "authentic.txt"


# 26. Existing task creation and deduplication remain unaffected
def test_existing_creation_and_deduplication_unaffected():
    payload = {
        "title": "Deduplication Verification",
        "category": "Exam",
        "source_sender": "Coordinator",
        "source_timestamp": "2026-10-22 14:00",
        "source_text": "Semester Midterm exam is on 2026-11-25.",
        "source_filename": "exam_schedule.txt",
        "due_date": "2026-11-25",
        "date_type": "deadline",
    }

    # Task creation succeeds
    create_res = client.post("/api/academic-items", json=payload)
    assert create_res.status_code == 201
    item_id = create_res.json()["id"]

    # Update title
    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"title": "Midterm Exam - Distributed Systems"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Midterm Exam - Distributed Systems"

    # Duplicate creation with identical source provenance still rejected with 409
    dup_res = client.post("/api/academic-items", json=payload)
    assert dup_res.status_code == 409
    assert str(item_id) in dup_res.json()["detail"]


# 27. Database layer update method direct unit tests
def test_database_update_academic_item_direct():
    from database import get_academic_item_by_id, save_academic_item, update_academic_item

    created = save_academic_item({
        "title": "Direct DB Test",
        "category": "Assignment",
        "source_text": "Direct DB source text",
        "due_date": "2026-11-01",
    })
    item_id = created["id"]

    # Safe partial update
    updated = update_academic_item(item_id, {"title": "Direct DB Updated", "due_date": "2026-11-10"})
    assert updated is not None
    assert updated["title"] == "Direct DB Updated"
    assert updated["due_date"] == "2026-11-10"
    assert updated["source_text"] == "Direct DB source text"

    # Nonexistent ID returns None
    assert update_academic_item(999999, {"title": "Ghost"}) is None
    assert update_academic_item(-1, {"title": "Negative"}) is None

    # Immutable fields raise ValueError at DB level
    with pytest.raises(ValueError, match="immutable provenance data"):
        update_academic_item(item_id, {"source_text": "Changed"})

    # Empty update returns existing item
    same = update_academic_item(item_id, {})
    assert same is not None
    assert same["title"] == "Direct DB Updated"


# ==============================================================================
# Phase 3: Confidence Scoring & Evidence Intelligence Persistence Tests
# ==============================================================================


# 28. Persistence of trusted pipeline confidence and evidence metadata
def test_persistence_confidence_and_evidence_metadata(tmp_path):
    """Confidence and evidence_text are persisted correctly when supplied via the
    trusted extraction-pipeline path (_trusted_confidence / _trusted_evidence)."""
    from database import get_academic_item_by_id, save_academic_item

    custom_db = tmp_path / "metadata_test.db"
    init_db(custom_db)

    # Simulate the extraction pipeline using trusted sentinel keys
    payload = {
        "title": "Machine Learning Lab 1",
        "category": "Assignment",
        "due_date": "2026-11-15",
        "date_type": "deadline",
        "date_status": "parsed",
        "source_text": "Machine Learning Lab 1 is due on 15/11/2026. Submit code on portal.",
        "evidence_text": "Machine Learning Lab 1 is due on 15/11/2026.",
        # Trusted pipeline path: sentinel keys bypass client-trust restriction
        "_trusted_confidence": "HIGH",
        "_trusted_confidence_reasons": ["Unambiguous academic category with validated explicit calendar date."],
        "_trusted_evidence": True,
    }

    saved = save_academic_item(payload, db_path=custom_db)
    assert saved["id"] is not None
    assert saved["confidence"] == "HIGH"
    assert saved["confidence_reasons"] == ["Unambiguous academic category with validated explicit calendar date."]
    assert saved["evidence_text"] == "Machine Learning Lab 1 is due on 15/11/2026."

    retrieved = get_academic_item_by_id(saved["id"], db_path=custom_db)
    assert retrieved is not None
    assert retrieved["confidence"] == "HIGH"
    assert retrieved["confidence_reasons"] == ["Unambiguous academic category with validated explicit calendar date."]
    assert retrieved["evidence_text"] == "Machine Learning Lab 1 is due on 15/11/2026."

    # Via REST API (manual POST): confidence is UNASSESSED, evidence must be substring of source_text
    api_res = client.post(
        "/api/academic-items",
        json={
            "title": "API ML Lab",
            "category": "Assignment",
            "source_text": "API ML Lab is due on 15/11/2026.",
            # evidence_text is a substring of source_text: allowed
            "evidence_text": "API ML Lab is due on 15/11/2026.",
            # NOTE: confidence and confidence_reasons are silently ignored by the API
        },
    )
    assert api_res.status_code == 201
    created = api_res.json()
    # Manual POST receives UNASSESSED — not client-supplied confidence
    assert created["confidence"] == "UNASSESSED"
    # evidence_text is preserved (it is a valid substring of source_text)
    assert created["evidence_text"] == "API ML Lab is due on 15/11/2026."


# 29. Legacy database records without confidence metadata
def test_persistence_legacy_records_without_confidence(tmp_path):
    from database import get_academic_item_by_id

    custom_db = tmp_path / "legacy_test.db"
    init_db(custom_db)

    # Insert a legacy row using raw SQL with NULL for new Phase 3 columns
    with get_db_connection(custom_db) as conn:
        conn.execute(
            """
            INSERT INTO academic_items (
                title, category, source_text, confidence, confidence_reasons, evidence_text, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?);
            """,
            ("Legacy Item", "Assignment", "Legacy source text", "2026-11-18T00:00:00", "2026-11-18T00:00:00"),
        )
        cursor = conn.execute("SELECT last_insert_rowid();")
        legacy_id = cursor.fetchone()[0]
        conn.commit()

    retrieved = get_academic_item_by_id(legacy_id, db_path=custom_db)
    assert retrieved is not None
    assert retrieved["title"] == "Legacy Item"
    # Phase 3.1 correction: legacy NULL confidence is UNASSESSED, not falsely promoted to MEDIUM
    assert retrieved["confidence"] == "UNASSESSED"
    assert retrieved["confidence_reasons"] == []
    # Legacy NULL evidence_text remains None — not backfilled from source_text
    assert retrieved["evidence_text"] is None


# 30. Database migration idempotency
def test_database_migration_idempotency(tmp_path):
    from database import get_academic_item_by_id, save_academic_item

    custom_db = tmp_path / "idempotency_test.db"

    # Call init_db multiple times
    init_db(custom_db)
    init_db(custom_db)
    init_db(custom_db)

    # Save an item via the trusted pipeline path
    saved = save_academic_item({
        "title": "Idempotent Task",
        "category": "Exam",
        "source_text": "Idempotent source text",
        "_trusted_confidence": "HIGH",
        "_trusted_confidence_reasons": [],
    }, db_path=custom_db)

    # Call init_db again after data exists
    init_db(custom_db)
    init_db(custom_db)

    # Verify data is undisturbed
    retrieved = get_academic_item_by_id(saved["id"], db_path=custom_db)
    assert retrieved is not None
    assert retrieved["title"] == "Idempotent Task"
    assert retrieved["confidence"] == "HIGH"


# 31. Immutable evidence text cannot be modified
def test_immutable_evidence_text_cannot_be_modified():
    from database import get_academic_item_by_id, update_academic_item

    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Evidence Test Task",
            "category": "Assignment",
            "source_text": "Original message text with authentic evidence.",
            # evidence_text is a valid substring of source_text
            "evidence_text": "authentic evidence",
        },
    )
    assert create_res.status_code == 201
    item_id = create_res.json()["id"]

    # Attempt to tamper with evidence_text via PATCH endpoint -> HTTP 422 extra_forbidden
    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"evidence_text": "Fabricated evidence"},
    )
    assert patch_res.status_code == 422
    assert "extra_forbidden" in patch_res.text

    # Attempt to tamper via direct DB update -> ValueError
    with pytest.raises(ValueError, match="immutable provenance data"):
        update_academic_item(item_id, {"evidence_text": "Fabricated evidence"})

    # Verify DB still has authentic evidence
    db_item = get_academic_item_by_id(item_id)
    assert db_item is not None
    assert db_item["evidence_text"] == "authentic evidence"


# 32. Filtering items by confidence (including UNASSESSED)
def test_filter_items_by_confidence():
    # Manual items receive UNASSESSED automatically
    client.post(
        "/api/academic-items",
        json={
            "title": "Unassessed Task",
            "category": "Assignment",
            "source_text": "Unassessed conf source text",
        },
    )

    # Filter UNASSESSED — retrieves manually created tasks
    res_unassessed = client.get("/api/academic-items?confidence=UNASSESSED")
    assert res_unassessed.status_code == 200
    for it in res_unassessed.json():
        assert it["confidence"] == "UNASSESSED"

    # Invalid confidence filter -> HTTP 400
    res_bad = client.get("/api/academic-items?confidence=UNKNOWN")
    assert res_bad.status_code == 400
    assert "Invalid confidence" in res_bad.json()["detail"]


# ==============================================================================
# Phase 3.1: Integrity Corrections — New Regression Tests
# ==============================================================================


# 33. PATCH cannot modify confidence
def test_patch_cannot_modify_confidence():
    """confidence is an immutable system-generated field; PATCH with confidence must return 422."""
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Confidence Lock Test",
            "category": "Assignment",
            "source_text": "Confidence lock test source text.",
        },
    )
    assert create_res.status_code == 201
    item_id = create_res.json()["id"]

    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"confidence": "HIGH"},
    )
    # AcademicItemUpdate forbids confidence (extra="forbid") -> HTTP 422
    assert patch_res.status_code == 422


# 34. PATCH cannot modify confidence_reasons
def test_patch_cannot_modify_confidence_reasons():
    """confidence_reasons is an immutable system-generated field; PATCH must return 422."""
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Confidence Reasons Lock Test",
            "category": "Exam",
            "source_text": "Confidence reasons lock test source text.",
        },
    )
    assert create_res.status_code == 201
    item_id = create_res.json()["id"]

    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={"confidence_reasons": ["Injected reason"]},
    )
    assert patch_res.status_code == 422


# 35. POST cannot inject arbitrary machine confidence
def test_post_cannot_inject_arbitrary_confidence():
    """REST POST silently ignores client-supplied confidence; manually created items are UNASSESSED."""
    res = client.post(
        "/api/academic-items",
        json={
            "title": "Injected Confidence Task",
            "category": "Assignment",
            "source_text": "Injected confidence test source text.",
            # Client attempts to supply an arbitrary confidence — should be ignored
            "confidence": "HIGH",
            "confidence_reasons": ["I am definitely accurate"],
        },
    )
    assert res.status_code == 201
    created = res.json()
    # Confidence must be UNASSESSED regardless of what the client supplied
    assert created["confidence"] == "UNASSESSED"
    # confidence_reasons not present on the schema, so they are silently discarded


# 36. POST cannot inject fabricated extraction evidence
def test_post_cannot_inject_fabricated_evidence():
    """evidence_text that is not a substring of source_text must be rejected."""
    res = client.post(
        "/api/academic-items",
        json={
            "title": "Fabricated Evidence Task",
            "category": "Assignment",
            "source_text": "Actual message text without evidence.",
            # This evidence does NOT appear in source_text -> should be rejected
            "evidence_text": "Completely fabricated extraction evidence",
        },
    )
    # HTTP 400: evidence_text must be a substring of source_text
    assert res.status_code == 400
    assert "fabricated" in res.json()["detail"].lower() or "substring" in res.json()["detail"].lower()


# 37. Trusted pipeline evidence is persisted correctly
def test_trusted_extraction_evidence_persists_correctly(tmp_path):
    """The extraction pipeline can persist confidence and evidence via trusted sentinel keys."""
    from database import get_academic_item_by_id, save_academic_item

    custom_db = tmp_path / "trusted_test.db"
    init_db(custom_db)

    source = "CN assignment is due on 25/11/2026. Please submit before midnight."
    evidence = "CN assignment is due on 25/11/2026."

    saved = save_academic_item({
        "title": "CN Assignment",
        "category": "Assignment",
        "source_text": source,
        "evidence_text": evidence,
        "_trusted_confidence": "HIGH",
        "_trusted_confidence_reasons": ["Unambiguous academic category with validated explicit calendar date."],
        "_trusted_evidence": True,
    }, db_path=custom_db)

    assert saved["confidence"] == "HIGH"
    assert saved["evidence_text"] == evidence
    retrieved = get_academic_item_by_id(saved["id"], db_path=custom_db)
    assert retrieved["evidence_text"] == evidence
    assert retrieved["confidence"] == "HIGH"


# 38. Manual task creation is correctly represented as UNASSESSED
def test_manual_task_creation_is_unassessed():
    """Manually created tasks via POST have UNASSESSED confidence and no fabricated evidence."""
    res = client.post(
        "/api/academic-items",
        json={
            "title": "Manual Task Entry",
            "category": "Announcement",
            "source_text": "Student posted this manually without WhatsApp extraction.",
        },
    )
    assert res.status_code == 201
    item = res.json()
    assert item["confidence"] == "UNASSESSED"
    # evidence_text was not supplied; should be None
    assert item["evidence_text"] is None


# 39. Legacy NULL confidence is represented as UNASSESSED (not MEDIUM)
def test_legacy_null_confidence_is_unassessed(tmp_path):
    """Legacy rows with NULL confidence must be surfaced as UNASSESSED, not MEDIUM."""
    from database import get_academic_item_by_id

    custom_db = tmp_path / "legacy_unassessed.db"
    init_db(custom_db)

    with get_db_connection(custom_db) as conn:
        conn.execute(
            """
            INSERT INTO academic_items (
                title, category, source_text, confidence, confidence_reasons,
                evidence_text, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?);
            """,
            ("Pre-Phase3 Item", "Exam", "Exam on Monday morning.", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        cursor = conn.execute("SELECT last_insert_rowid();")
        legacy_id = cursor.fetchone()[0]
        conn.commit()

    item = get_academic_item_by_id(legacy_id, db_path=custom_db)
    assert item is not None
    assert item["confidence"] == "UNASSESSED"
    assert item["confidence_reasons"] == []


# 40. Legacy NULL evidence remains None (not backfilled from source_text)
def test_legacy_null_evidence_remains_none(tmp_path):
    """Legacy rows with NULL evidence_text must remain None, not be backfilled with source_text."""
    from database import get_academic_item_by_id

    custom_db = tmp_path / "legacy_evidence.db"
    init_db(custom_db)

    with get_db_connection(custom_db) as conn:
        conn.execute(
            """
            INSERT INTO academic_items (
                title, category, source_text, evidence_text, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, NULL, ?, ?);
            """,
            ("Old Item", "Event", "Some old source text.", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        cursor = conn.execute("SELECT last_insert_rowid();")
        legacy_id = cursor.fetchone()[0]
        conn.commit()

    item = get_academic_item_by_id(legacy_id, db_path=custom_db)
    assert item is not None
    # Must be None — not "Some old source text." (which would be false backfill)
    assert item["evidence_text"] is None
    # source_text itself is preserved correctly
    assert item["source_text"] == "Some old source text."


# 41. UNASSESSED filtering works via API
def test_unassessed_confidence_filter_works():
    """GET /api/academic-items?confidence=UNASSESSED returns manually created tasks."""
    client.post(
        "/api/academic-items",
        json={
            "title": "Filter Unassessed Task",
            "category": "Announcement",
            "source_text": "Filter unassessed test source text.",
        },
    )

    res = client.get("/api/academic-items?confidence=UNASSESSED")
    assert res.status_code == 200
    items = res.json()
    assert len(items) > 0
    for it in items:
        assert it["confidence"] == "UNASSESSED"


# 42. Assignment contextualized by workshop is NOT a genuine category conflict
def test_assignment_workshop_context_not_a_conflict():
    """
    'Submit your lab exercise report for the robotics workshop' should produce
    Assignment category without being penalised for the workshop keyword.
    The word 'workshop' here is prepositional context, not a conflicting Event task.
    """
    from extractor import extract_academic_items

    msg = "Submit your lab exercise report for the robotics workshop on 28/10/2026."
    results = extract_academic_items([{
        "text": msg,
        "sender": "Prof. Kumar",
        "timestamp_text": "2026-10-19 10:00",
    }])
    assert len(results) == 1
    item = results[0]
    # Must still be Assignment
    assert item["category"] == "Assignment"
    # Confidence should NOT be LOW solely because "workshop" is in the text
    # (it is contextual context for the submission, not an Event intent)
    assert item["confidence"] in ("HIGH", "MEDIUM")
    # Explicit date with deadline language -> HIGH
    assert item["confidence"] == "HIGH"


# 43. Genuine multiple academic intents produce separate candidates
def test_genuine_multiple_intents_produces_separate_candidates():
    """
    'Submit the assignment and prepare for the semester examination.'
    Contains two genuinely distinct academic intents (Assignment + Exam);
    they should be extracted as separate candidates.
    """
    from extractor import extract_academic_items

    msg = "Submit the assignment and prepare for the semester examination."
    results = extract_academic_items([{
        "text": msg,
        "sender": "Prof. Kumar",
        "timestamp_text": "2026-10-19 10:00",
    }])
    # Two distinct intents -> two candidates
    assert len(results) == 2
    cats = {r["category"] for r in results}
    assert "Assignment" in cats
    assert "Exam" in cats
    # Neither should be falsely HIGH without a date
    for r in results:
        assert r["confidence"] in ("MEDIUM", "LOW")


# 44. Comma-separated independent tasks have isolated evidence
def test_comma_separated_tasks_have_isolated_evidence():
    """
    'Submit assignment 1 on 10/11/2026, CN exam on 12/11/2026.'
    Should produce separate candidates with non-overlapping evidence.
    """
    from extractor import extract_academic_items

    msg = "Submit assignment 1 on 10/11/2026, CN exam on 12/11/2026."
    results = extract_academic_items([{
        "text": msg,
        "sender": "Prof. Kumar",
        "timestamp_text": "2026-10-19 10:00",
    }])
    assert len(results) == 2
    cats = {r["category"] for r in results}
    assert "Assignment" in cats
    assert "Exam" in cats

    # Evidence for the assignment must NOT contain the exam clause and vice versa
    assign_item = next(r for r in results if r["category"] == "Assignment")
    exam_item = next(r for r in results if r["category"] == "Exam")

    # source_text is shared (the full message)
    assert assign_item["source_text"] == msg
    assert exam_item["source_text"] == msg

    # evidence_text is isolated per task
    assert "exam" not in assign_item["evidence_text"].lower()
    assert "assignment" not in exam_item["evidence_text"].lower()


# 45. Multi-sentence evidence isolation remains intact (Phase 2 regression)
def test_multi_sentence_evidence_isolation_regression():
    """Regression: multi-sentence messages still isolate evidence per task correctly."""
    from extractor import extract_academic_items

    msg = "DBMS assignment due Friday. CN exam on Monday."
    results = extract_academic_items([{
        "text": msg,
        "sender": "Prof. Kumar",
        "timestamp_text": "2026-11-14 10:00",  # Friday
    }])
    assert len(results) == 2
    assign_item = next(r for r in results if r["category"] == "Assignment")
    exam_item = next(r for r in results if r["category"] == "Exam")
    # Evidence must stay in its own clause
    assert "exam" not in assign_item["evidence_text"].lower()
    assert "assignment" not in exam_item["evidence_text"].lower()


# 46. Phase 1 editing behavior remains intact (regression)
def test_phase1_editing_behavior_regression():
    """Regression: title, category, description, and due_date can still be edited via PATCH."""
    create_res = client.post(
        "/api/academic-items",
        json={
            "title": "Original Phase1 Title",
            "category": "Assignment",
            "source_text": "Original Phase1 source text.",
        },
    )
    assert create_res.status_code == 201
    item_id = create_res.json()["id"]

    patch_res = client.patch(
        f"/api/academic-items/{item_id}",
        json={
            "title": "Updated Phase1 Title",
            "category": "Exam",
            "due_date": "2026-12-01",
        },
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["title"] == "Updated Phase1 Title"
    assert updated["category"] == "Exam"
    assert updated["due_date"] == "2026-12-01"
    # Confidence and evidence must remain unchanged
    assert updated["confidence"] == "UNASSESSED"
    assert updated["evidence_text"] is None


# 47. Phase 2 date and time extraction regression
def test_phase2_date_time_extraction_regression():
    """Regression: date and time extraction from messages still works correctly."""
    from extractor import extract_academic_items

    msg = "Assignment due on 28th October 2026 by 11:59 PM."
    results = extract_academic_items([{
        "text": msg,
        "sender": "Prof. Kumar",
        "timestamp_text": "2026-10-19 10:00",
    }])
    assert len(results) == 1
    item = results[0]
    assert item["due_date"] == "2026-10-28"
    assert item["deadline_time"] == "23:59"
    assert item["confidence"] == "HIGH"


# 48. Phase 3 deterministic confidence behavior regression
def test_phase3_deterministic_confidence_regression():
    """Regression: calculate_confidence remains deterministic across repeated calls."""
    from extractor import extract_academic_items

    msg = "Assignment 1 on Distributed Systems is due on 28/10/2026."
    for _ in range(5):
        results = extract_academic_items([{
            "text": msg,
            "sender": "Prof. Kumar",
            "timestamp_text": "2026-10-19 10:00",
        }])
        assert len(results) == 1
        assert results[0]["confidence"] == "HIGH"
        assert results[0]["confidence_reasons"] == [
            "Unambiguous academic category with validated explicit calendar date."
        ]
