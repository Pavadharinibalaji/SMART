"""Phase 4.2.1: Relative Date Intelligence Test Suite for SMART.

Verifies reliable relative date interpretation for academic announcements,
assignments, examination schedules, submission deadlines, and institutional events.

Tests evaluate:
1. Basic relative date expressions (today, tomorrow, day after tomorrow, yesterday, tonight, this morning, this evening)
2. Weekday interpretation (this Friday, next Monday, coming Wednesday, by Sunday, before Monday)
3. Relative durations (within 3 days, in two weeks, after 5 days, within one week, after 10 days, written numbers)
4. Boundary conditions (month transition, year transition, leap year, December to January, month-end expressions)
5. Reliability and ambiguity (missing timestamp, malformed timestamp, timezone handling, ambiguous phrases, Unicode/emojis)
6. Date range handling (from Monday to Wednesday, between Friday and Sunday, Monday through Thursday)
7. Provenance integrity & candidate token security (binding due_date, client tampering rejection, backward compatibility)
8. Confidence model preservation & calendar export compatibility
"""

from __future__ import annotations

import base64
from datetime import date
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from calendar_export import generate_ics
from database import get_db_connection, init_db
from extractor import (
    create_candidate_token,
    detect_date,
    extract_academic_items,
    get_provenance_secret,
    verify_candidate_token,
)
from main import app
from temporal_parser import (
    detect_all_dates,
    extract_time,
    parse_reference_timestamp,
    resolve_weekday,
)

client = TestClient(app)

# Fixed reference dates for testing
# 2026-11-20 is a Friday (weekday 4)
FRIDAY_REF_TIMESTAMP = "20/11/2026, 09:00 am"
FRIDAY_REF_DATE = date(2026, 11, 20)

# 2026-10-19 is a Monday (weekday 0)
MONDAY_REF_TIMESTAMP = "19/10/2026, 10:30 am"
MONDAY_REF_DATE = date(2026, 10, 19)


# ==============================================================================
# 1. Basic Relative Date Expressions
# ==============================================================================

def test_basic_relative_today():
    """Verify 'today', 'tonight', 'this morning', 'this evening' resolve to anchor date."""
    for phrase in ("today", "tonight", "this morning", "this evening"):
        text = f"Submit your report {phrase}."
        res = detect_date(text, FRIDAY_REF_TIMESTAMP)
        assert res["date_status"] == "resolved_from_message_date"
        assert res["due_date"] == "2026-11-20"


def test_basic_relative_tomorrow():
    """Verify 'tomorrow' resolves to anchor date + 1 day."""
    text = "Submit the assignment tomorrow."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-21"


def test_basic_relative_day_after_tomorrow():
    """Verify 'day after tomorrow' resolves to anchor date + 2 days."""
    text = "Project demo is scheduled for day after tomorrow."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-22"


def test_basic_relative_yesterday():
    """Verify 'yesterday' resolves to anchor date - 1 day."""
    text = "The guest lecture was held yesterday."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-19"


# ==============================================================================
# 2. Weekday Interpretation
# ==============================================================================

def test_weekday_this_friday_on_friday():
    """Verify 'this Friday' on Friday resolves to today (anchor date)."""
    text = "Submit this Friday."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-20"


def test_weekday_next_monday_from_friday():
    """Verify 'next Monday' from Friday resolves to the coming Monday (+3 days)."""
    text = "Submit next Monday."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-23"


def test_weekday_coming_wednesday_from_friday():
    """Verify 'coming Wednesday' from Friday resolves to the next Wednesday (+5 days)."""
    text = "Internal assessment on coming Wednesday."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-25"


def test_weekday_by_sunday_from_friday():
    """Verify 'by Sunday' from Friday resolves to the upcoming Sunday (+2 days)."""
    text = "Upload the draft by Sunday."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-22"


def test_weekday_before_monday_from_friday():
    """Verify 'before Monday' from Friday resolves to Sunday (2026-11-22), strictly prior to Monday."""
    text = "Complete the survey before Monday."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-22"


def test_weekday_this_monday_on_friday_requires_review():
    """Verify 'this Monday' said on a Friday refers to a past day and flags review."""
    text = "Assignment was due this Monday."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "needs_review"
    assert res["due_date"] is None
    assert any("already passed" in r for r in res["date_reasons"])


# ==============================================================================
# 3. Relative Durations
# ==============================================================================

def test_duration_within_3_days():
    """Verify 'within 3 days' resolves to anchor date + 3 days."""
    text = "Submit within 3 days."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-23"


def test_duration_in_two_weeks_written_number():
    """Verify 'in two weeks' with written number resolves to anchor date + 14 days."""
    text = "Final project presentations will take place in two weeks."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-12-04"


def test_duration_after_5_days():
    """Verify 'after 5 days' resolves to anchor date + 5 days."""
    text = "Portal opens after 5 days."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-25"


def test_duration_within_one_week():
    """Verify 'within one week' resolves to anchor date + 7 days."""
    text = "Please register within one week."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-27"


def test_duration_after_10_days():
    """Verify 'after 10 days' resolves across month boundary to 2026-11-30."""
    text = "Evaluation will begin after 10 days."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-11-30"


# ==============================================================================
# 4. Boundary Conditions
# ==============================================================================

def test_boundary_month_transition():
    """Verify month transition across October 31 to November 1."""
    halloween_ts = "31/10/2026, 11:00 am"
    res = detect_date("Assignment due tomorrow.", halloween_ts)
    assert res["due_date"] == "2026-11-01"


def test_boundary_year_transition_december_to_january():
    """Verify year transition across December 31 to January 1."""
    nye_ts = "31/12/2026, 05:00 pm"
    res = detect_date("Submit your work tomorrow.", nye_ts)
    assert res["due_date"] == "2027-01-01"


def test_boundary_leap_year_february_2028():
    """Verify leap year handling in February 2028 (2028-02-28 + 1 day = 2028-02-29)."""
    leap_ts = "28/02/2028, 08:00 am"
    res = detect_date("Lab record submission is tomorrow.", leap_ts)
    assert res["due_date"] == "2028-02-29"

    # From Feb 29 to March 1
    leap_ts2 = "29/02/2028, 08:00 am"
    res2 = detect_date("Next class is tomorrow.", leap_ts2)
    assert res2["due_date"] == "2028-03-01"


def test_boundary_month_end_expressions():
    """Verify 'by the end of the month' resolves to last day of month in leap vs non-leap years."""
    # November 2026 -> 30 days
    res_nov = detect_date("Submit the report by the end of the month.", FRIDAY_REF_TIMESTAMP)
    assert res_nov["due_date"] == "2026-11-30"

    # February 2028 (leap year) -> 29 days
    res_feb_leap = detect_date("Clear dues before the end of the month.", "10/02/2028, 10:00 am")
    assert res_feb_leap["due_date"] == "2028-02-29"

    # February 2027 (non-leap year) -> 28 days
    res_feb_norm = detect_date("Submit report by end of this month.", "10/02/2027, 10:00 am")
    assert res_feb_norm["due_date"] == "2027-02-28"


# ==============================================================================
# 5. Reliability & Ambiguity
# ==============================================================================

def test_reliability_missing_timestamp():
    """Verify that a missing message timestamp leaves relative date unresolved without guessing system date."""
    res = detect_date("Submit tomorrow.", "")
    assert res["due_date"] is None
    assert res["date_status"] == "needs_review"
    assert any("could not be parsed" in r or "missing" in r for r in res["date_reasons"])


def test_reliability_malformed_timestamp():
    """Verify that a malformed message timestamp is safely flagged for review."""
    res = detect_date("Submit next Monday.", "invalid-date-format")
    assert res["due_date"] is None
    assert res["date_status"] == "needs_review"


def test_reliability_timezone_aware_timestamp():
    """Verify that ISO timezone-aware timestamps preserve the original calendar date without shift."""
    iso_tz_ts = "2026-11-20T14:30:00+05:30"
    res = detect_date("Submit tomorrow.", iso_tz_ts)
    assert res["due_date"] == "2026-11-21"

    iso_utc_ts = "2026-11-20T10:00:00Z"
    res_utc = detect_date("Submit within 3 days.", iso_utc_ts)
    assert res_utc["due_date"] == "2026-11-23"


def test_reliability_ambiguous_relative_expression():
    """Verify ambiguous phrases like 'soon' or 'within a few days' are flagged for review."""
    for phrase in ("soon", "within a few days", "in a couple of days", "later this week"):
        text = f"The test will be conducted {phrase}."
        res = detect_date(text, FRIDAY_REF_TIMESTAMP)
        assert res["date_status"] == "needs_review"
        assert res["due_date"] is None
        assert any("Ambiguous" in r for r in res["date_reasons"])


def test_reliability_unicode_and_emojis():
    """Verify relative date extraction works with emojis and surrounding Unicode characters."""
    emoji_text = "🎉 Important Reminder: Submit your assignment tomorrow! 🚀"
    res = detect_date(emoji_text, FRIDAY_REF_TIMESTAMP)
    assert res["due_date"] == "2026-11-21"
    assert res["date_status"] == "resolved_from_message_date"


# ==============================================================================
# 6. Date Range Handling
# ==============================================================================

def test_date_range_from_monday_to_wednesday():
    """Verify 'from Monday to Wednesday' is not arbitrarily collapsed into a single deadline."""
    text = "The annual tech symposium is scheduled from Monday to Wednesday."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["due_date"] is None
    assert res["date_status"] == "needs_review"
    assert res.get("is_range") is True
    assert any("Date range detected" in r for r in res["date_reasons"])


def test_date_range_between_friday_and_sunday():
    """Verify 'between Friday and Sunday' is flagged as a multi-day range."""
    text = "Hackathon will take place between Friday and Sunday."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["due_date"] is None
    assert res["date_status"] == "needs_review"
    assert res.get("is_range") is True


def test_date_range_through_thursday():
    """Verify 'Monday through Thursday' is flagged as a multi-day range."""
    text = "Workshops will run Monday through Thursday."
    res = detect_date(text, FRIDAY_REF_TIMESTAMP)
    assert res["due_date"] is None
    assert res["date_status"] == "needs_review"
    assert res.get("is_range") is True


# ==============================================================================
# 7. Candidate Provenance Integrity & Tampering Tests
# ==============================================================================

def test_candidate_token_binds_due_date_and_date_status():
    """Verify that create_candidate_token binds due_date and date_status in HMAC payload."""
    candidate = {
        "source_text": "Submit assignment tomorrow.",
        "category": "Assignment",
        "evidence_text": "Submit assignment tomorrow.",
        "evidence_start_index": 0,
        "evidence_end_index": 27,
        "confidence": "MEDIUM",
        "confidence_reasons": ["Relative date resolved"],
        "is_actionable": True,
        "actionability_type": "action_required",
        "update_type": None,
        "due_date": "2026-11-21",
        "date_status": "resolved_from_message_date",
    }
    token = create_candidate_token(candidate)
    decoded = verify_candidate_token(token)
    assert decoded is not None
    assert decoded["due_date"] == "2026-11-21"
    assert decoded["date_status"] == "resolved_from_message_date"


def test_client_cannot_tamper_with_token_resolved_date(tmp_path: Path, monkeypatch):
    """Verify server authoritatively enforces token due_date over client-supplied tampered date."""
    db_file = tmp_path / "test_date_tamper.db"
    init_db(db_file)
    monkeypatch.setenv("SMART_DB_PATH", str(db_file))

    source_text = "Submit the term report tomorrow."
    cand = {
        "source_text": source_text,
        "category": "Assignment",
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "confidence": "MEDIUM",
        "confidence_reasons": ["Relative date resolved"],
        "is_actionable": True,
        "actionability_type": "action_required",
        "update_type": None,
        "due_date": "2026-11-21",
        "date_status": "resolved_from_message_date",
    }
    token = create_candidate_token(cand)

    # Malicious client attempts to forge due_date to next year
    tampered_payload = {
        "title": "Term Report",
        "category": "Assignment",
        "source_text": source_text,
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "due_date": "2027-12-31",
        "candidate_token": token,
    }

    resp = client.post("/api/academic-items", json=tampered_payload)
    assert resp.status_code == 201
    persisted = resp.json()

    # Server must authoritatively enforce verified token date over client tampering
    assert persisted["due_date"] == "2026-11-21"
    assert persisted["date_status"] == "resolved_from_message_date"


# ==============================================================================
# 8. Confidence Model Preservation & Calendar Export
# ==============================================================================

def test_relative_date_does_not_promote_confidence_to_high():
    """Verify relative date resolution preserves MEDIUM confidence rather than inflating to HIGH."""
    messages = [
        {
            "message_id": 1,
            "sender": "Prof. Smith",
            "timestamp_text": FRIDAY_REF_TIMESTAMP,
            "text": "Submit assignment 2 tomorrow.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    assert items[0]["due_date"] == "2026-11-21"
    assert items[0]["confidence"] == "MEDIUM"
    assert any("relative date resolved" in r for r in items[0]["confidence_reasons"])


def test_calendar_export_with_relative_resolved_deadlines():
    """Verify calendar export correctly formats confirmed deadlines resolved from relative expressions."""
    items = [
        {
            "title": "Assignment 2",
            "category": "Assignment",
            "due_date": "2026-11-21",
            "date_type": "deadline",
            "status": "pending",
            "source_text": "Submit assignment 2 tomorrow.",
            "source_sender": "Prof. Smith",
            "source_timestamp": FRIDAY_REF_TIMESTAMP,
            "created_at": "2026-11-20T10:00:00Z",
        }
    ]
    ics_content = generate_ics(items)
    assert "BEGIN:VCALENDAR" in ics_content
    assert "SUMMARY:Assignment 2" in ics_content
    assert "DTSTART;VALUE=DATE:20261121" in ics_content
    assert "END:VCALENDAR" in ics_content


# ==============================================================================
# 9. Phase 4.2.1.1: Temporal Semantics & Deadline Integrity Audit Tests
# ==============================================================================

def test_weekday_audit_before_vs_by_specification_table():
    """Verify specification table from Friday, 20 November 2026 for before vs by."""
    ref_ts = FRIDAY_REF_TIMESTAMP  # 2026-11-20 (Friday)

    # by Monday -> 2026-11-23
    res_by = detect_date("Submit the project by Monday.", ref_ts)
    assert res_by["due_date"] == "2026-11-23"

    # before Monday -> 2026-11-22
    res_before = detect_date("Submit the project before Monday.", ref_ts)
    assert res_before["due_date"] == "2026-11-22"

    # on Monday -> 2026-11-23
    res_on = detect_date("Internal test on Monday.", ref_ts)
    assert res_on["due_date"] == "2026-11-23"

    # next Monday -> 2026-11-23
    res_next = detect_date("Final submission next Monday.", ref_ts)
    assert res_next["due_date"] == "2026-11-23"


def test_all_weekdays_before_vs_by_from_friday():
    """Verify 'before' vs 'by' for all 7 weekdays from Friday, 20 November 2026."""
    ref_ts = FRIDAY_REF_TIMESTAMP

    # Monday: by=2026-11-23, before=2026-11-22 (Sunday)
    assert detect_date("by Monday", ref_ts)["due_date"] == "2026-11-23"
    assert detect_date("before Monday", ref_ts)["due_date"] == "2026-11-22"

    # Tuesday: by=2026-11-24, before=2026-11-23 (Monday)
    assert detect_date("by Tuesday", ref_ts)["due_date"] == "2026-11-24"
    assert detect_date("before Tuesday", ref_ts)["due_date"] == "2026-11-23"

    # Wednesday: by=2026-11-25, before=2026-11-24 (Tuesday)
    assert detect_date("by Wednesday", ref_ts)["due_date"] == "2026-11-25"
    assert detect_date("before Wednesday", ref_ts)["due_date"] == "2026-11-24"

    # Thursday: by=2026-11-26, before=2026-11-25 (Wednesday)
    assert detect_date("by Thursday", ref_ts)["due_date"] == "2026-11-26"
    assert detect_date("before Thursday", ref_ts)["due_date"] == "2026-11-25"

    # Friday: by=2026-11-27, before=2026-11-26 (Thursday)
    assert detect_date("by Friday", ref_ts)["due_date"] == "2026-11-27"
    assert detect_date("before Friday", ref_ts)["due_date"] == "2026-11-26"

    # Saturday: by=2026-11-21, before=2026-11-20 (Friday / today)
    assert detect_date("by Saturday", ref_ts)["due_date"] == "2026-11-21"
    assert detect_date("before Saturday", ref_ts)["due_date"] == "2026-11-20"

    # Sunday: by=2026-11-22, before=2026-11-21 (Saturday)
    assert detect_date("by Sunday", ref_ts)["due_date"] == "2026-11-22"
    assert detect_date("before Sunday", ref_ts)["due_date"] == "2026-11-21"


def test_historical_dates_case_a_internal_exam_conducted_yesterday():
    """Test Case A: 'The internal exam was conducted yesterday.'

    Expected: Historical event date, not an automatically created pending deadline.
    - due_date is None (historical event date, not a deadline)
    - date_type is 'event_date'
    - is_actionable is False, actionability_type is 'informational'
    """
    messages = [
        {
            "message_id": 101,
            "sender": "Prof. Davis",
            "timestamp_text": FRIDAY_REF_TIMESTAMP,
            "text": "The internal exam was conducted yesterday.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["category"] == "Exam"
    assert item["due_date"] is None
    assert item["date_text"] == "yesterday"
    assert item["date_type"] == "event_date"
    assert item["is_actionable"] is False
    assert item["actionability_type"] == "informational"


def test_historical_dates_case_b_assignment_deadline_was_yesterday():
    """Test Case B: 'The assignment deadline was yesterday.'

    Expected: Past deadline, not an invented future deadline.
    - due_date is '2026-11-19' (yesterday's date preserved, not bumped forward)
    - date_type is 'deadline'
    - is_actionable is False, actionability_type is 'informational'
    - date_status is 'needs_review', review_required is True
    """
    messages = [
        {
            "message_id": 102,
            "sender": "TA Sarah",
            "timestamp_text": FRIDAY_REF_TIMESTAMP,
            "text": "The assignment deadline was yesterday.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["category"] == "Assignment"
    assert item["due_date"] == "2026-11-19"
    assert item["date_type"] == "deadline"
    assert item["is_actionable"] is False
    assert item["actionability_type"] == "informational"
    assert item["review_required"] is True
    assert item["date_status"] == "needs_review"
    assert any("past" in r for r in item["review_reasons"])


def test_historical_dates_case_c_assignment_must_be_submitted_tomorrow():
    """Test Case C: 'The assignment must be submitted tomorrow.'

    Expected: Future deadline resolved from the message timestamp.
    - due_date is '2026-11-21'
    - date_type is 'deadline'
    - is_actionable is True, actionability_type is 'action_required'
    """
    messages = [
        {
            "message_id": 103,
            "sender": "Prof. Davis",
            "timestamp_text": FRIDAY_REF_TIMESTAMP,
            "text": "The assignment must be submitted tomorrow.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["category"] == "Assignment"
    assert item["due_date"] == "2026-11-21"
    assert item["date_type"] == "deadline"
    assert item["is_actionable"] is True
    assert item["actionability_type"] == "action_required"


def test_historical_dates_case_d_workshop_happened_yesterday():
    """Test Case D: 'The workshop happened yesterday.'

    Expected: Historical event, not a pending task.
    - due_date is None (historical event date, not a task deadline)
    - date_type is 'event_date'
    - is_actionable is False, actionability_type is 'informational'
    """
    messages = [
        {
            "message_id": 104,
            "sender": "Coordinator",
            "timestamp_text": FRIDAY_REF_TIMESTAMP,
            "text": "The workshop happened yesterday.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["category"] == "Event"
    assert item["due_date"] is None
    assert item["date_text"] == "yesterday"
    assert item["date_type"] == "event_date"
    assert item["is_actionable"] is False
    assert item["actionability_type"] == "informational"


def test_time_of_day_expressions_do_not_invent_clock_time():
    """Verify that 'tonight', 'this morning', 'this evening' do not invent 6 PM or 11:59 PM."""
    from extractor import extract_time

    for phrase in ("tonight", "this morning", "this evening"):
        text = f"Submit the assignment {phrase}."
        time_res = extract_time(text)
        assert time_res["time_text"] is None, f"Clock time was invented for '{phrase}'!"
        assert time_res["deadline_time"] is None, f"Clock time was invented for '{phrase}'!"

        date_res = detect_date(text, FRIDAY_REF_TIMESTAMP)
        assert date_res["due_date"] == "2026-11-20"
        assert date_res["date_text"].lower() == phrase.lower()


def test_temporal_provenance_tampering_new_fields(tmp_path: Path, monkeypatch):
    """Verify that candidate token authoritatively binds date_text and date_type against tampering."""
    db_file = tmp_path / "test_tamper_fields.db"
    init_db(db_file)
    monkeypatch.setenv("SMART_DB_PATH", str(db_file))

    source_text = "Submit the term paper tomorrow."
    cand = {
        "source_text": source_text,
        "category": "Assignment",
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "confidence": "MEDIUM",
        "confidence_reasons": ["Relative date resolved"],
        "is_actionable": True,
        "actionability_type": "action_required",
        "update_type": None,
        "due_date": "2026-11-21",
        "date_status": "resolved_from_message_date",
        "date_text": "tomorrow",
        "date_type": "deadline",
        "is_range": False,
    }
    token = create_candidate_token(cand)

    # Malicious client attempts to tamper with date_text, date_type, and due_date
    tampered_payload = {
        "title": "Term Paper",
        "category": "Assignment",
        "source_text": source_text,
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "due_date": "2028-01-01",
        "date_text": "tampered_date_text",
        "date_type": "event_date",
        "candidate_token": token,
    }

    resp = client.post("/api/academic-items", json=tampered_payload)
    assert resp.status_code == 201
    persisted = resp.json()

    # Server must authoritatively enforce verified token fields over client-supplied values
    assert persisted["due_date"] == "2026-11-21"
    assert persisted["date_text"] == "tomorrow"
    assert persisted["date_type"] == "deadline"



# ==============================================================================
# Phase 4.2.1.2 & Phase 4.2.2 Tests: Explicit Dates, Times, & is_range Integrity
# ==============================================================================

def test_is_range_authoritative_enforcement_and_persistence(tmp_path: Path, monkeypatch):
    """Verify is_range is authoritatively enforced from verified token data and persisted to DB."""
    db_file = tmp_path / "test_is_range_tamper.db"
    init_db(db_file)
    monkeypatch.setenv("SMART_DB_PATH", str(db_file))

    source_text = "Annual symposium is from Monday to Wednesday."
    cand = {
        "source_text": source_text,
        "category": "Event",
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "confidence": "MEDIUM",
        "confidence_reasons": ["Date range detected"],
        "is_actionable": False,
        "actionability_type": "informational",
        "update_type": None,
        "due_date": None,
        "date_status": "needs_review",
        "date_text": "from Monday to Wednesday",
        "date_type": "event_date",
        "is_range": True,
    }
    token = create_candidate_token(cand)

    # Malicious client attempts to tamper with is_range and forge a single due_date
    tampered_payload = {
        "title": "Annual Symposium",
        "category": "Event",
        "source_text": source_text,
        "evidence_text": source_text,
        "evidence_start_index": 0,
        "evidence_end_index": len(source_text),
        "due_date": "2026-11-25",
        "date_status": "parsed",
        "is_range": False,
        "candidate_token": token,
    }

    client = TestClient(app)
    resp = client.post("/api/academic-items", json=tampered_payload)
    assert resp.status_code == 201
    persisted = resp.json()

    # Server must authoritatively enforce verified token fields: is_range=True, due_date=None, date_status=needs_review
    assert persisted["is_range"] is True
    assert persisted["due_date"] is None
    assert persisted["date_status"] == "needs_review"

    # Verify directly in SQLite that is_range was persisted as 1
    with get_db_connection(db_file) as conn:
        cursor = conn.execute("SELECT is_range, due_date, date_status FROM academic_items WHERE id = ?;", (persisted["id"],))
        row = cursor.fetchone()
        assert row["is_range"] == 1
        assert row["due_date"] is None
        assert row["date_status"] == "needs_review"

    # Test PATCH update to is_range
    patch_resp = client.patch(f"/api/academic-items/{persisted['id']}", json={"is_range": False})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_range"] is False


def test_is_range_legacy_token_and_manual_persistence(tmp_path: Path, monkeypatch):
    """Verify backward compatibility for legacy tokens without is_range and manual task creation."""
    db_file = tmp_path / "test_legacy_is_range.db"
    init_db(db_file)
    monkeypatch.setenv("SMART_DB_PATH", str(db_file))

    # 1. Simulate legacy candidate token lacking 'is_range' key
    secret = get_provenance_secret()
    legacy_provenance = {
        "source_text": "Submit assignment tomorrow.",
        "category": "Assignment",
        "evidence_text": "Submit assignment tomorrow.",
        "evidence_start_index": 0,
        "evidence_end_index": 27,
        "confidence": "MEDIUM",
        "confidence_reasons": ["Legacy token"],
        "is_actionable": True,
        "actionability_type": "action_required",
        "update_type": None,
        "due_date": "2026-11-21",
        "date_status": "resolved_from_message_date",
        "date_text": "tomorrow",
        "date_type": "deadline",
    }
    raw_json = json.dumps(legacy_provenance, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(raw_json).decode("ascii")
    sig = hmac.new(secret, raw_json, hashlib.sha256).hexdigest()
    legacy_token = f"{payload_b64}.{sig}"

    client = TestClient(app)
    resp = client.post("/api/academic-items", json={
        "title": "Legacy Assignment",
        "category": "Assignment",
        "source_text": "Submit assignment tomorrow.",
        "evidence_text": "Submit assignment tomorrow.",
        "evidence_start_index": 0,
        "evidence_end_index": 27,
        "candidate_token": legacy_token,
    })
    assert resp.status_code == 201
    assert resp.json()["is_range"] is False

    # 2. Manual task creation with explicit is_range
    manual_resp = client.post("/api/academic-items", json={
        "title": "Manual Workshop Series",
        "category": "Event",
        "source_text": "Workshop series spans multiple days.",
        "is_range": True,
    })
    assert manual_resp.status_code == 201
    assert manual_resp.json()["is_range"] is True


def test_phase4_2_2_explicit_dates_and_formats():
    """Verify Example 1 ('25 November 2026') and Example 2 ('25/11/2026') and alternate date formats."""
    # Example 1: 'Assignment submission is on 25 November 2026.'
    msgs1 = [{
        "message_id": 101,
        "sender": "Prof. Smith",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "Assignment submission is on 25 November 2026.",
    }]
    cand1 = extract_academic_items(msgs1)[0]
    assert cand1["category"] == "Assignment"
    assert cand1["due_date"] == "2026-11-25"
    assert cand1["date_text"] == "25 November 2026"
    assert cand1["date_status"] == "parsed"
    assert cand1["date_type"] == "deadline"
    assert cand1["is_actionable"] is True
    assert cand1["actionability_type"] == "action_required"

    # Example 2: 'Submit the record by 25/11/2026.'
    msgs2 = [{
        "message_id": 102,
        "sender": "Lab Admin",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "Submit the record by 25/11/2026.",
    }]
    cand2 = extract_academic_items(msgs2)[0]
    assert cand2["category"] == "Assignment"
    assert cand2["due_date"] == "2026-11-25"
    assert cand2["date_text"] == "25/11/2026"
    assert cand2["date_status"] == "parsed"
    assert cand2["date_type"] == "deadline"
    assert cand2["is_actionable"] is True

    # Alternate formats: Month Day Year and ISO YYYY-MM-DD
    msgs3 = [{
        "message_id": 103,
        "sender": "Prof. Jones",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "Assignment 2 is due on November 25, 2026.",
    }]
    cand3 = extract_academic_items(msgs3)[0]
    assert cand3["due_date"] == "2026-11-25"
    assert cand3["date_status"] == "parsed"

    msgs4 = [{
        "message_id": 104,
        "sender": "Prof. Jones",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "Submit project proposal by 2026-11-28.",
    }]
    cand4 = extract_academic_items(msgs4)[0]
    assert cand4["due_date"] == "2026-11-28"
    assert cand4["date_status"] == "parsed"


def test_phase4_2_2_date_and_time_together():
    """Verify Example 3 ('10:30 AM on 26 November') and Example 4 ('14:00 on 27-11-2026')."""
    # Example 3: 'Internal exam starts at 10:30 AM on 26 November.'
    msgs3 = [{
        "message_id": 105,
        "sender": "Exam Cell",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "Internal exam starts at 10:30 AM on 26 November.",
    }]
    cand3 = extract_academic_items(msgs3)[0]
    assert cand3["category"] == "Exam"
    assert cand3["time_text"] == "10:30 AM"
    assert cand3["deadline_time"] == "10:30"
    assert cand3["date_text"] == "26 November"
    assert cand3["due_date"] is None  # Day and month without year -> SMART does not invent year
    assert cand3["date_status"] == "needs_review"
    assert cand3["date_type"] == "event_date"
    assert cand3["review_required"] is True

    # Example 4: 'Lab examination is scheduled for 14:00 on 27-11-2026.'
    msgs4 = [{
        "message_id": 106,
        "sender": "Exam Cell",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "Lab examination is scheduled for 14:00 on 27-11-2026.",
    }]
    cand4 = extract_academic_items(msgs4)[0]
    assert cand4["category"] == "Exam"
    assert cand4["time_text"] == "14:00"
    assert cand4["deadline_time"] == "14:00"
    assert cand4["date_text"] == "27-11-2026"
    assert cand4["due_date"] == "2026-11-27"
    assert cand4["date_status"] == "parsed"
    assert cand4["date_type"] == "event_date"
    assert cand4["is_actionable"] is True

    # Period clock time variant: '10.30 AM'
    time_info_dot = extract_time("Meeting at 10.30 AM.")
    assert time_info_dot["time_text"] == "10.30 AM"
    assert time_info_dot["deadline_time"] == "10:30"


def test_phase4_2_2_historical_event_versus_deadline():
    """Verify Example 5 ('Workshop was conducted on 18 November.') does not create pending deadline."""
    # Example 5: Historical event without year
    msgs5 = [{
        "message_id": 107,
        "sender": "HOD Office",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "Workshop was conducted on 18 November.",
    }]
    cand5 = extract_academic_items(msgs5)[0]
    assert cand5["category"] == "Event"
    assert cand5["due_date"] is None  # Historical event never forced into due_date
    assert cand5["date_text"] == "18 November"
    assert cand5["date_type"] == "event_date"
    assert cand5["is_actionable"] is False
    assert cand5["actionability_type"] == "informational"
    assert cand5["date_status"] == "needs_review"

    # Historical event with explicit year:
    msgs5_year = [{
        "message_id": 108,
        "sender": "HOD Office",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "The symposium concluded on 18 November 2026.",
    }]
    cand5_year = extract_academic_items(msgs5_year)[0]
    assert cand5_year["category"] == "Event"
    assert cand5_year["due_date"] is None
    assert cand5_year["date_type"] == "event_date"
    assert cand5_year["is_actionable"] is False
    assert cand5_year["actionability_type"] == "informational"


def test_phase4_2_2_numeric_dates_without_year():
    """Verify Example 6 ('Assignment deadline is 25/11.') and ambiguous numeric ('05/11')."""
    # Unambiguous day-first numeric without year: 25/11
    msgs6 = [{
        "message_id": 109,
        "sender": "Class Rep",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "Assignment deadline is 25/11.",
    }]
    cand6 = extract_academic_items(msgs6)[0]
    assert cand6["category"] == "Assignment"
    assert cand6["date_text"] == "25/11"
    assert cand6["due_date"] is None  # No year invented
    assert cand6["date_status"] == "needs_review"
    assert cand6["date_type"] == "deadline"
    assert cand6["review_required"] is True

    # Ambiguous numeric without year: 05/11 (May 11 vs Nov 5)
    res_ambig = detect_date("Project demo is scheduled for 05/11.", "20/11/2026, 09:00")
    assert res_ambig["date_text"] == "05/11"
    assert res_ambig["due_date"] is None
    assert res_ambig["date_status"] == "needs_review"
    assert "ambiguous" in res_ambig["date_reasons"][0].lower()


def test_phase4_2_2_unspecified_date():
    """Verify Example 7 ('Submit it on an unspecified date.') does not fabricate dates or times."""
    msgs7 = [{
        "message_id": 110,
        "sender": "Teacher",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "Submit it on an unspecified date.",
    }]
    cand7 = extract_academic_items(msgs7)[0]
    assert cand7["due_date"] is None
    assert cand7["date_text"] is None
    assert cand7["date_status"] == "not_found"
    assert cand7["time_text"] is None
    assert cand7["deadline_time"] is None
    assert cand7["confidence"] == "MEDIUM"
    assert any("no deadline or event date was specified" in r for r in cand7["confidence_reasons"])


def test_phase4_2_2_multi_clause_date_and_time_association():
    """Verify date and time association across distinct clauses in a compound announcement."""
    text = "Internal exam starts at 10:30 AM on 26 November, and lab exam is scheduled for 14:00 on 27-11-2026."
    msgs = [{
        "message_id": 111,
        "sender": "Exam Controller",
        "timestamp_text": "20/11/2026, 09:00",
        "text": text,
    }]
    extracted = extract_academic_items(msgs)
    assert len(extracted) == 2

    exam1 = extracted[0]
    exam2 = extracted[1]

    # First exam clause
    assert exam1["time_text"] == "10:30 AM"
    assert exam1["deadline_time"] == "10:30"
    assert exam1["date_text"] == "26 November"
    assert exam1["due_date"] is None
    assert exam1["date_status"] == "needs_review"

    # Second exam clause
    assert exam2["time_text"] == "14:00"
    assert exam2["deadline_time"] == "14:00"
    assert exam2["date_text"] == "27-11-2026"
    assert exam2["due_date"] == "2026-11-27"
    assert exam2["date_status"] == "parsed"

    # Evidence non-overlapping and verified
    assert exam1["evidence_text"] in text
    assert exam2["evidence_text"] in text
    assert exam1["evidence_end_index"] <= exam2["evidence_start_index"]


# ==============================================================================
# 11. Phase 4.2.3: Deadline Modification Intelligence Tests
# ==============================================================================

def test_phase4_2_3_eight_modification_types_extraction():
    """Verify all 8 modification update types are accurately recognized by extraction."""
    ref_ts = "20/11/2026, 09:00"

    # 1. Extension
    cand1 = extract_academic_items([{
        "message_id": 201, "sender": "Prof. A", "timestamp_text": ref_ts,
        "text": "Assignment 1 deadline is extended to 25 November 2026.",
    }])[0]
    assert cand1["update_type"] == "extension"
    assert cand1["due_date"] == "2026-11-25"

    # 2. Postponement
    cand2 = extract_academic_items([{
        "message_id": 202, "sender": "Prof. B", "timestamp_text": ref_ts,
        "text": "Internal exam 1 has been postponed to 30 November 2026.",
    }])[0]
    assert cand2["update_type"] == "postponement"
    assert cand2["due_date"] == "2026-11-30"

    # 3. Rescheduled with previous date transition
    cand3 = extract_academic_items([{
        "message_id": 203, "sender": "Prof. C", "timestamp_text": ref_ts,
        "text": "Assignment 1 previously due 20 November 2026 is rescheduled to 28 November 2026.",
    }])[0]
    assert cand3["update_type"] == "rescheduled"
    assert cand3["previous_due_date"] == "2026-11-20"
    assert cand3["due_date"] == "2026-11-28"

    # 4. Cancellation
    cand4 = extract_academic_items([{
        "message_id": 204, "sender": "Prof. D", "timestamp_text": ref_ts,
        "text": "Assignment 1 submission is cancelled.",
    }])[0]
    assert cand4["update_type"] == "cancellation"
    assert cand4["is_actionable"] is False

    # 5. Revision
    cand5 = extract_academic_items([{
        "message_id": 205, "sender": "Prof. E", "timestamp_text": ref_ts,
        "text": "Project proposal due date revised to 27 November 2026.",
    }])[0]
    assert cand5["update_type"] == "revision"
    assert cand5["due_date"] == "2026-11-27"

    # 6. Confirmation
    cand6 = extract_academic_items([{
        "message_id": 206, "sender": "Prof. F", "timestamp_text": ref_ts,
        "text": "This confirms Assignment 1 deadline remains 20 November 2026.",
    }])[0]
    assert cand6["update_type"] == "confirmation"
    assert cand6["is_actionable"] is False

    # 7. Window Change
    cand7 = extract_academic_items([{
        "message_id": 207, "sender": "Prof. G", "timestamp_text": ref_ts,
        "text": "Project submission window changed from 20 November 2026 to 25 November 2026.",
    }])[0]
    assert cand7["update_type"] == "window_change"
    assert cand7["previous_due_date"] == "2026-11-20"
    assert cand7["due_date"] == "2026-11-25"

    # 8. Replacement
    cand8 = extract_academic_items([{
        "message_id": 208, "sender": "Prof. H", "timestamp_text": ref_ts,
        "text": "Project proposal replaces the previous assignment deadline with 29 November 2026.",
    }])[0]
    assert cand8["update_type"] == "replacement"
    assert cand8["due_date"] == "2026-11-29"


def test_phase4_2_3_task_association_and_superseding():
    """Verify update candidate supersedes existing task and captures previous_due_date."""
    # 1. Create initial task
    resp1 = client.post("/api/academic-items", json={
        "title": "Assignment 1",
        "category": "Assignment",
        "due_date": "2026-11-20",
        "date_type": "deadline",
        "source_text": "Assignment 1 due on 20 November 2026.",
        "source_sender": "Prof. X",
        "source_timestamp": "15/11/2026, 10:00",
    })
    assert resp1.status_code == 201
    task1 = resp1.json()
    task1_id = task1["id"]
    assert task1["status"] == "pending"

    # 2. Create extension update candidate
    msgs = [{
        "message_id": 210,
        "sender": "Prof. X",
        "timestamp_text": "18/11/2026, 10:00",
        "text": "Assignment 1 deadline is extended to 25 November 2026.",
    }]
    cand = extract_academic_items(msgs)[0]
    cand_resp = client.post("/api/academic-items", json={
        "title": cand["title"],
        "category": cand["category"],
        "due_date": cand["due_date"],
        "date_type": cand["date_type"],
        "date_status": cand["date_status"],
        "source_text": cand["source_text"],
        "source_sender": cand["source_sender"],
        "source_timestamp": cand["source_timestamp"],
        "candidate_token": cand["candidate_token"],
        "evidence_text": cand["evidence_text"],
        "evidence_start_index": cand["evidence_start_index"],
        "evidence_end_index": cand["evidence_end_index"],
        "update_type": cand["update_type"],
    })
    assert cand_resp.status_code == 201
    task2 = cand_resp.json()

    # New task should link to old task and carry previous due date
    assert task2["replaces_task_id"] == task1_id
    assert task2["previous_due_date"] == "2026-11-20"
    assert task2["due_date"] == "2026-11-25"
    assert task2["status"] == "pending"

    # Old task should now be superseded
    task1_updated = client.get(f"/api/academic-items/{task1_id}").json()
    assert task1_updated["status"] == "superseded"


def test_phase4_2_3_cancellation_marks_existing_task_cancelled():
    """Verify cancellation announcement marks associated task as cancelled with reason."""
    # 1. Create initial task
    resp1 = client.post("/api/academic-items", json={
        "title": "Quiz 2",
        "category": "Exam",
        "due_date": "2026-11-24",
        "date_type": "deadline",
        "source_text": "Quiz 2 is scheduled for 24 November 2026.",
        "source_sender": "HOD Office",
        "source_timestamp": "15/11/2026, 11:00",
    })
    assert resp1.status_code == 201
    quiz_id = resp1.json()["id"]

    # 2. Post cancellation candidate
    msgs = [{
        "message_id": 211,
        "sender": "HOD Office",
        "timestamp_text": "19/11/2026, 11:00",
        "text": "Quiz 2 submission is cancelled.",
    }]
    cand = extract_academic_items(msgs)[0]
    cand_resp = client.post("/api/academic-items", json={
        "title": cand["title"],
        "category": cand["category"],
        "source_text": cand["source_text"],
        "source_sender": cand["source_sender"],
        "source_timestamp": cand["source_timestamp"],
        "candidate_token": cand["candidate_token"],
        "evidence_text": cand["evidence_text"],
        "evidence_start_index": cand["evidence_start_index"],
        "evidence_end_index": cand["evidence_end_index"],
        "update_type": cand["update_type"],
    })
    assert cand_resp.status_code == 201
    cancel_task = cand_resp.json()

    assert cancel_task["replaces_task_id"] == quiz_id
    assert cancel_task["status"] == "cancelled"

    # Old task should also be cancelled and flagged
    old_quiz = client.get(f"/api/academic-items/{quiz_id}").json()
    assert old_quiz["status"] == "cancelled"
    assert old_quiz["review_required"] is True
    assert any("cancelled" in r.lower() for r in old_quiz["review_reasons"])


def test_phase4_2_3_unassociated_update_flags_review():
    """Verify an update with no matching existing task is saved with review_required."""
    msgs = [{
        "message_id": 212,
        "sender": "Prof. Mystery",
        "timestamp_text": "19/11/2026, 12:00",
        "text": "Assignment 99 deadline is extended to 30 November 2026.",
    }]
    cand = extract_academic_items(msgs)[0]
    resp = client.post("/api/academic-items", json={
        "title": cand["title"],
        "category": cand["category"],
        "due_date": cand["due_date"],
        "date_type": cand["date_type"],
        "date_status": cand["date_status"],
        "source_text": cand["source_text"],
        "source_sender": cand["source_sender"],
        "source_timestamp": cand["source_timestamp"],
        "candidate_token": cand["candidate_token"],
        "evidence_text": cand["evidence_text"],
        "evidence_start_index": cand["evidence_start_index"],
        "evidence_end_index": cand["evidence_end_index"],
        "update_type": cand["update_type"],
    })
    assert resp.status_code == 201
    persisted = resp.json()
    assert persisted["review_required"] is True
    assert persisted["replaces_task_id"] is None
    assert any("without a confirmed existing task association" in r for r in persisted["review_reasons"])


# ==============================================================================
# 12. Phase 4.2.4: Temporal Ambiguity & Confidence Tests
# ==============================================================================

def test_phase4_2_4_weekday_date_contradiction():
    """Verify weekday-calendar contradiction (e.g. 'Monday, 24 November 2026' where 24 Nov is Tuesday)."""
    # 24 Nov 2026 is Tuesday, not Monday
    msgs = [{
        "message_id": 220,
        "sender": "Coordinator",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "Internal test on Monday, 24 November 2026.",
    }]
    items = extract_academic_items(msgs)
    assert len(items) == 1
    item = items[0]
    assert item["due_date"] is None
    assert item["date_status"] == "needs_review"
    assert item["confidence"] == "LOW"
    assert item["review_required"] is True
    assert any("contradiction" in r.lower() or "conflict" in r.lower() for r in item["confidence_reasons"])


def test_phase4_2_4_incomplete_temporal_expressions():
    """Verify unanchored/incomplete temporal expressions (asap, tba, before lunch, next week)."""
    ref_ts = "20/11/2026, 09:00"

    test_cases = [
        ("Submit the lab assignment asap.", "asap"),
        ("Final exam schedule will be announced later.", "announced later"),
        ("Submit your assignment before lunch.", "before lunch"),
        ("Project demo is scheduled for next week.", "next week"),
    ]

    for text, expected_snippet in test_cases:
        res = detect_date(text, ref_ts)
        assert res["due_date"] is None
        assert res["date_status"] == "needs_review"
        assert expected_snippet in res["date_text"].lower()

        # In candidate extraction:
        msgs = [{"message_id": 225, "sender": "Staff", "timestamp_text": ref_ts, "text": text}]
        items = extract_academic_items(msgs)
        assert len(items) == 1
        assert items[0]["due_date"] is None
        assert items[0]["date_status"] == "needs_review"
        assert items[0]["confidence"] == "LOW"
        assert items[0]["review_required"] is True


def test_phase4_2_4_timezone_preservation_without_day_shifting():
    """Verify timestamp with timezone offset preserves message calendar date without shifting."""
    # 2026-11-20 at 23:30 in +05:30 (India) is 2026-11-20 in local time, but 18:00 UTC.
    # The relative day 'tomorrow' must resolve to 2026-11-21 in local context.
    ts_with_tz = "2026-11-20T23:30:00+05:30"
    res = detect_date("Assignment 3 due tomorrow.", ts_with_tz)
    assert res["due_date"] == "2026-11-21"


# ==============================================================================
# 13. Phase 4.2.5: Temporal Integration & Calendar Export Filtering Tests
# ==============================================================================

def test_phase4_2_5_calendar_export_excludes_superseded_and_cancelled():
    """Verify .ics calendar export excludes cancelled, superseded, and dismissed tasks."""
    # Create 3 tasks: 1 active, 1 superseded, 1 cancelled
    # 1. Active task
    client.post("/api/academic-items", json={
        "title": "Active Deadline",
        "category": "Assignment",
        "due_date": "2026-11-25",
        "date_type": "deadline",
        "status": "pending",
        "source_text": "Active deadline on 25 November 2026.",
    })

    # 2. Superseded task
    client.post("/api/academic-items", json={
        "title": "Old Superseded Deadline",
        "category": "Assignment",
        "due_date": "2026-11-22",
        "date_type": "deadline",
        "status": "superseded",
        "source_text": "Old deadline on 22 November 2026.",
    })

    # 3. Cancelled task
    client.post("/api/academic-items", json={
        "title": "Cancelled Deadline",
        "category": "Assignment",
        "due_date": "2026-11-23",
        "date_type": "deadline",
        "status": "cancelled",
        "source_text": "Cancelled deadline on 23 November 2026.",
    })

    # Export calendar
    resp = client.get("/api/academic-items/export-ics")
    assert resp.status_code == 200
    ics_text = resp.text

    assert "Active Deadline" in ics_text
    assert "20261125" in ics_text

    # Excluded
    assert "Old Superseded Deadline" not in ics_text
    assert "Cancelled Deadline" not in ics_text


def test_phase4_2_5_candidate_token_hmac_tamper_proofing():
    """Verify HMAC candidate token rejects tampering with previous_due_date and update_type."""
    msgs = [{
        "message_id": 230,
        "sender": "Dean",
        "timestamp_text": "20/11/2026, 09:00",
        "text": "Assignment 1 previously due 20 November 2026 is rescheduled to 28 November 2026.",
    }]
    cand = extract_academic_items(msgs)[0]

    # Tamper with previous_due_date in client payload without changing token
    tampered_payload = {
        "title": cand["title"],
        "category": cand["category"],
        "due_date": cand["due_date"],
        "date_type": cand["date_type"],
        "date_status": cand["date_status"],
        "source_text": cand["source_text"],
        "source_sender": cand["source_sender"],
        "source_timestamp": cand["source_timestamp"],
        "candidate_token": cand["candidate_token"],
        "evidence_text": cand["evidence_text"],
        "evidence_start_index": cand["evidence_start_index"],
        "evidence_end_index": cand["evidence_end_index"],
        "previous_due_date": "1999-01-01",  # Client forged previous due date
    }

    resp = client.post("/api/academic-items", json=tampered_payload)
    assert resp.status_code == 201
    persisted = resp.json()
    # Server-authoritative token must override client forgery
    assert persisted["previous_due_date"] == "2026-11-20"

