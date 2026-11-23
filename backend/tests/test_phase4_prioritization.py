"""Tests for Phase 4.3: Academic Context, Urgency Detection, and Intelligent Prioritization.

Validates:
1. Academic relevance and intent classification across 12 distinct academic categories/intents.
2. Explainable academic importance assessment (HIGH, MEDIUM, LOW, UNASSESSED).
3. Dynamic temporal urgency detection relative to reference dates (CRITICAL, HIGH, MEDIUM, LOW, NO_DEADLINE, NEEDS_REVIEW).
4. Composite explainable prioritization engine combining urgency, importance, actionability, and certainty.
5. Task relationship and lineage validation, including server-side authority over invalid replaces_task_id.
6. Database persistence, additive migrations, API PATCH overrides, and relationship endpoints.
"""

from datetime import date, timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from database import (
    get_academic_item_by_id,
    get_task_relationships,
    init_db,
    list_academic_items,
    save_academic_item,
)
from extractor import extract_academic_items
from main import app
from prioritization import (
    assess_academic_importance,
    assess_task_urgency,
    calculate_priority,
    classify_academic_intent,
    enrich_task_with_prioritization,
)

client = TestClient(app)


# ==============================================================================
# 1. Academic Relevance & Intent Classification Tests
# ==============================================================================

def test_academic_intent_classification():
    """Verify classification of academic intent across various contexts."""
    cases = [
        # (category, title, text, expected_intent)
        ("Assignment", "Assignment 3", "Submit problem set 3 before Friday.", "assignment"),
        ("Exam", "Midterm Schedule", "The semester examination will begin at 10 AM.", "exam"),
        ("Assignment", "Lab Report", "Submit your chemistry lab record and observation sheet.", "laboratory"),
        ("Assignment", "Project Phase 2", "Submit your capstone project final demo and thesis.", "project"),
        ("Event", "Guest Lecture", "Invited talk and departmental seminar on quantum algorithms.", "seminar"),
        ("Announcement", "Attendance Notice", "Students with attendance shortage must apply for condonation.", "attendance"),
        ("Opportunity", "Merit Fellowship", "Apply for the merit scholarship tuition waiver before month end.", "scholarship"),
        ("Opportunity", "Campus Drive", "Google placement drive and recruitment interview round 1.", "placement"),
        ("Opportunity", "Code Jam", "Annual 24-hour hackathon and coding contest registration.", "competition"),
        ("Event", "AI Workshop", "Hands-on workshop on machine learning fundamentals.", "workshop"),
        ("Announcement", "Exam Fee", "Last date for examination fee payment and hall ticket issue.", "administrative"),
        ("Announcement", "Class Rescheduled", "Tomorrow's regular lecture timetable is updated.", "academic_announcement"),
    ]

    for cat, title, text, expected_intent in cases:
        intent, reasons = classify_academic_intent(category=cat, title=title, text=text)
        assert intent == expected_intent, f"Failed for '{title}': expected {expected_intent}, got {intent}"
        assert len(reasons) > 0


# ==============================================================================
# 2. Academic Importance Assessment Tests
# ==============================================================================

def test_academic_importance_assessment():
    """Verify explainable importance determination independent of temporal urgency."""
    # 1. High importance: Major final/semester exam
    imp1, r1 = assess_academic_importance("Exam", "exam", "Semester Examination", "Final end-sem exam for all students.")
    assert imp1 == "HIGH"
    assert any("formal examination" in r.lower() or "major" in r.lower() for r in r1)

    # 2. High importance: Explicit grade weightage
    imp2, r2 = assess_academic_importance("Assignment", "assignment", "Term Paper", "Submission counts for 30% of total grade.")
    assert imp2 == "HIGH"
    assert any("weight" in r.lower() or "grading" in r.lower() for r in r2)

    # 3. High importance: Culminating capstone/thesis
    imp3, r3 = assess_academic_importance("Assignment", "project", "Final Thesis", "Submit your final thesis and capstone presentation.")
    assert imp3 == "HIGH"
    assert any("capstone" in r.lower() or "thesis" in r.lower() for r in r3)

    # 4. High importance: Placement drive
    imp4, r4 = assess_academic_importance("Opportunity", "placement", "Amazon Recruitment", "Campus placement drive interview rounds.")
    assert imp4 == "HIGH"
    assert any("placement" in r.lower() or "recruitment" in r.lower() for r in r4)

    # 5. Medium importance: Routine assignment or quiz
    imp5, r5 = assess_academic_importance("Assignment", "assignment", "Assignment 2", "Complete exercises 4 and 5 from chapter 2.")
    assert imp5 == "MEDIUM"

    # 6. Low importance: Optional activity
    imp6, r6 = assess_academic_importance("Event", "seminar", "Club Meet", "Optional club meeting for interested volunteers.")
    assert imp6 == "LOW"

    # 7. Unassessed: General announcement without grading context
    imp7, r7 = assess_academic_importance("Announcement", "academic_announcement", "Holiday Notice", "College will remain closed on Monday.", is_actionable=False)
    assert imp7 == "UNASSESSED"

    # 8. Cancelled task: Importance reflects inactive status
    imp8, r8 = assess_academic_importance("Assignment", "assignment", "Assignment 1", "Cancelled", status="cancelled")
    assert imp8 == "LOW"
    assert any("inactive" in r.lower() or "cancelled" in r.lower() for r in r8)


# ==============================================================================
# 3. Urgency Detection Tests
# ==============================================================================

def test_urgency_detection():
    """Verify dynamic temporal urgency relative to calendar reference date."""
    ref = date(2026, 11, 20)  # Reference today: 2026-11-20

    # 1. Overdue: 2 days in the past (2026-11-18)
    urg_overdue, r_overdue, d_overdue = assess_task_urgency("2026-11-18", "parsed", current_date=ref)
    assert urg_overdue == "CRITICAL"
    assert d_overdue == -2
    assert any("overdue by 2 day(s)" in r.lower() for r in r_overdue)

    # 2. Due Today (2026-11-20)
    urg_today, r_today, d_today = assess_task_urgency("2026-11-20", "parsed", current_date=ref)
    assert urg_today == "CRITICAL"
    assert d_today == 0
    assert any("today" in r.lower() for r in r_today)

    # 3. Due Tomorrow (2026-11-21)
    urg_tomorrow, r_tomorrow, d_tomorrow = assess_task_urgency("2026-11-21", "parsed", current_date=ref)
    assert urg_tomorrow == "CRITICAL"
    assert d_tomorrow == 1
    assert any("tomorrow" in r.lower() for r in r_tomorrow)

    # 4. Approaching: in 3 days (2026-11-23)
    urg_3d, r_3d, d_3d = assess_task_urgency("2026-11-23", "parsed", current_date=ref)
    assert urg_3d == "HIGH"
    assert d_3d == 3

    # 5. Moderate: in 6 days (2026-11-26)
    urg_6d, r_6d, d_6d = assess_task_urgency("2026-11-26", "parsed", current_date=ref)
    assert urg_6d == "MEDIUM"
    assert d_6d == 6

    # 6. Distant: in 14 days (2026-12-04)
    urg_14d, r_14d, d_14d = assess_task_urgency("2026-12-04", "parsed", current_date=ref)
    assert urg_14d == "LOW"
    assert d_14d == 14

    # 7. No deadline
    urg_none, r_none, d_none = assess_task_urgency(None, "not_found", current_date=ref)
    assert urg_none == "NO_DEADLINE"
    assert d_none is None

    # 8. Ambiguous date needing review
    urg_rev, r_rev, d_rev = assess_task_urgency(None, "needs_review", current_date=ref)
    assert urg_rev == "NEEDS_REVIEW"
    assert d_rev is None

    # 9. Cancelled or Superseded task
    urg_canc, r_canc, _ = assess_task_urgency("2026-11-21", "parsed", status="cancelled", current_date=ref)
    assert urg_canc == "LOW"
    assert any("cancelled" in r.lower() for r in r_canc)


# ==============================================================================
# 4. Composite Explainable Prioritization Tests
# ==============================================================================

def test_prioritization_composite_rules():
    """Verify combination of urgency, importance, actionability, and certainty into priority."""
    # 1. Overdue task is always CRITICAL
    p1, r1 = calculate_priority("CRITICAL", "MEDIUM", delta_days=-1)
    assert p1 == "CRITICAL"
    assert any("overdue" in r.lower() for r in r1)

    # 2. Due today/tomorrow is CRITICAL
    p2, r2 = calculate_priority("CRITICAL", "MEDIUM", delta_days=1)
    assert p2 == "CRITICAL"
    assert any("tomorrow" in r.lower() for r in r2)

    # 3. High importance + High urgency (2 days) is CRITICAL
    p3, r3 = calculate_priority("HIGH", "HIGH", delta_days=2)
    assert p3 == "CRITICAL"

    # 4. High importance + Medium urgency (5 days) is HIGH
    p4, r4 = calculate_priority("MEDIUM", "HIGH", delta_days=5)
    assert p4 == "HIGH"

    # 5. Medium importance + High urgency (2 days) is HIGH
    p5, r5 = calculate_priority("HIGH", "MEDIUM", delta_days=2)
    assert p5 == "HIGH"

    # 6. Medium importance + Medium urgency (5 days) is MEDIUM
    p6, r6 = calculate_priority("MEDIUM", "MEDIUM", delta_days=5)
    assert p6 == "MEDIUM"

    # 7. Low importance + Low urgency (12 days) is LOW
    p7, r7 = calculate_priority("LOW", "LOW", delta_days=12)
    assert p7 == "LOW"

    # 8. Informational item (non-actionable) is LOW
    p8, r8 = calculate_priority("HIGH", "HIGH", is_actionable=False)
    assert p8 == "LOW"
    assert any("informational" in r.lower() for r in r8)

    # 9. Inactive status (cancelled / superseded) is LOW
    p9, r9 = calculate_priority("CRITICAL", "HIGH", status="superseded", delta_days=0)
    assert p9 == "LOW"
    assert any("superseded" in r.lower() for r in r9)


# ==============================================================================
# 5. Task Relationship & Lineage Validation Tests
# ==============================================================================

def test_task_relationships_and_server_authority():
    """Verify task relationship hierarchy and server-side validation of replaces_task_id."""
    # 1. Create base task
    resp1 = client.post("/api/academic-items", json={
        "title": "Internal Exam 1",
        "category": "Exam",
        "due_date": "2026-11-24",
        "date_type": "deadline",
        "status": "pending",
        "source_text": "Internal exam 1 is scheduled for 24 November 2026.",
        "source_sender": "Prof. Smith",
    })
    assert resp1.status_code == 201
    task1 = resp1.json()
    task1_id = task1["id"]

    # 2. Create replacement task (postponement)
    resp2 = client.post("/api/academic-items", json={
        "title": "Internal Exam 1 Postponed",
        "category": "Exam",
        "due_date": "2026-11-28",
        "date_type": "deadline",
        "status": "pending",
        "replaces_task_id": task1_id,
        "update_type": "postponement",
        "source_text": "Internal exam 1 has been postponed to 28 November 2026.",
        "source_sender": "Prof. Smith",
    })
    assert resp2.status_code == 201
    task2 = resp2.json()
    task2_id = task2["id"]

    # Verify task 1 is now superseded
    t1_check = client.get(f"/api/academic-items/{task1_id}").json()
    assert t1_check["status"] == "superseded"

    # Verify relationships endpoint for task 2
    rel_resp = client.get(f"/api/academic-items/{task2_id}/relationships")
    assert rel_resp.status_code == 200
    rel = rel_resp.json()
    assert rel["found"] is True
    assert rel["parent"]["id"] == task1_id
    assert any(h["task_id"] == task1_id for h in rel["history"])
    assert any(h["task_id"] == task2_id for h in rel["history"])

    # 3. Server-side authority: attempt to supply a fabricated, non-existent replaces_task_id
    bogus_id = 999999
    resp_bogus = client.post("/api/academic-items", json={
        "title": "Suspicious Assignment",
        "category": "Assignment",
        "replaces_task_id": bogus_id,
        "source_text": "Submit task replacing task 999999.",
        "source_sender": "Unknown",
    })
    assert resp_bogus.status_code == 201
    bogus_task = resp_bogus.json()
    # Server must clear invalid replaces_task_id and flag for review
    assert bogus_task["replaces_task_id"] is None
    assert bogus_task["review_required"] is True
    assert any("not found" in r.lower() for r in bogus_task["review_reasons"])


# ==============================================================================
# 6. Database Persistence, Migration & API Override Tests
# ==============================================================================

def test_importance_persistence_and_patch_override():
    """Verify importance persistence and user override via PATCH."""
    # Create an item with default importance
    resp = client.post("/api/academic-items", json={
        "title": "Physics Assignment 1",
        "category": "Assignment",
        "due_date": "2026-11-29",
        "date_type": "deadline",
        "source_text": "Physics assignment 1 due on 29 November 2026.",
        "source_sender": "Prof. Newton",
    })
    assert resp.status_code == 201
    item = resp.json()
    item_id = item["id"]
    assert item["importance"] in ("MEDIUM", "HIGH")
    assert item["priority"] in ("HIGH", "MEDIUM", "LOW")

    # User overrides importance to HIGH via PATCH
    patch_resp = client.patch(f"/api/academic-items/{item_id}", json={
        "importance": "HIGH",
    })
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["importance"] == "HIGH"

    # User attempts invalid importance
    bad_patch = client.patch(f"/api/academic-items/{item_id}", json={
        "importance": "INVALID_LEVEL",
    })
    assert bad_patch.status_code == 422


def test_api_filtering_by_priority_and_urgency():
    """Verify GET /api/academic-items supports filtering by priority and urgency."""
    resp = client.get("/api/academic-items?priority=CRITICAL")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    for it in items:
        assert it["priority"] == "CRITICAL"

    resp_urg = client.get("/api/academic-items?urgency=LOW")
    assert resp_urg.status_code == 200
    urg_items = resp_urg.json()
    assert isinstance(urg_items, list)
    for it in urg_items:
        assert it["urgency"] == "LOW"
