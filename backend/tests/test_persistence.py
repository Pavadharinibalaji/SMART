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
