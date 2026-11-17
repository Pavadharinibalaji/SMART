"""Unit tests for academic information extractor (backend/extractor.py)."""

from datetime import date
import pytest
from extractor import (
    classify_message,
    detect_date,
    extract_academic_items,
    extract_urls,
    parse_message_date,
)


def test_classify_message_word_boundaries_prevent_false_positives():
    # 'prevent', 'eventually', 'seventeen' contain 'event'
    # 'example', 'examine' contain 'exam'
    # 'quizzical' contains 'quiz'
    text_casual_1 = "We must prevent errors and eventually review the report for seventeen cases."
    cat_1, _ = classify_message(text_casual_1)
    assert cat_1 is None

    text_casual_2 = "For example, you can examine the diagram in chapter 2."
    cat_2, _ = classify_message(text_casual_2)
    assert cat_2 is None

    text_casual_3 = "He gave me a quizzical look when I asked about lunch."
    cat_3, _ = classify_message(text_casual_3)
    assert cat_3 is None


def test_classify_message_valid_categories():
    assert classify_message("Assignment 3 is released")[0] == "Assignment"
    assert classify_message("Semester Examination timetable is out")[0] == "Exam"
    assert classify_message("Important Notice: classes suspended tomorrow")[0] == "Announcement"
    assert classify_message("Hands-on Workshop on Docker & Kubernetes")[0] == "Event"
    assert classify_message("Summer Internship Opportunity at Google")[0] == "Opportunity"


def test_explicit_dates_parsing():
    res1 = detect_date("Submission deadline is 28/10/2026.", "19/10/2026, 9:00 am")
    assert res1["date_status"] == "parsed"
    assert res1["due_date"] == "2026-10-28"

    res2 = detect_date("Workshop scheduled on 15 November 2026.", "19/10/2026, 9:00 am")
    assert res2["date_status"] == "parsed"
    assert res2["due_date"] == "2026-11-15"

    res3 = detect_date("Final paper due on December 5, 2026.", "19/10/2026, 9:00 am")
    assert res3["date_status"] == "parsed"
    assert res3["due_date"] == "2026-12-05"


def test_relative_dates_resolution():
    # Message sent on 19/10/2026
    timestamp = "19/10/2026, 10:00 am"

    res_tomorrow = detect_date("Assignment is due tomorrow!", timestamp)
    assert res_tomorrow["date_status"] == "resolved_from_message_date"
    assert res_tomorrow["due_date"] == "2026-10-20"

    res_day_after = detect_date("Project submission is day after tomorrow.", timestamp)
    assert res_day_after["date_status"] == "resolved_from_message_date"
    assert res_day_after["due_date"] == "2026-10-21"

    # When timestamp cannot be parsed, relative date requires review
    res_unknown_ts = detect_date("Due tomorrow", "InvalidTimestamp")
    assert res_unknown_ts["date_status"] == "needs_review"
    assert res_unknown_ts["due_date"] is None


def test_dates_without_explicit_year():
    # Day and month only: SMART should NOT guess or invent a year
    res = detect_date("Seminar on 24th October at Hall A.", "19/10/2026, 9:00 am")
    assert res["date_status"] == "needs_review"
    assert res["due_date"] is None
    assert "24th October" in res["date_text"]


def test_ambiguous_numeric_dates():
    # 05/06/2026 is ambiguous (May 6 vs June 5)
    res = detect_date("Project demo on 05/06/2026.", "19/10/2026, 9:00 am")
    assert res["date_status"] == "needs_review"
    assert res["due_date"] is None
    assert "ambiguous" in res["date_reasons"][0].lower()


def test_url_extraction_punctuation_and_deduplication():
    text = (
        "Check registration: https://example.edu/form. "
        "Also see (https://example.edu/guidelines). "
        "And visit https://example.edu/form again!"
    )
    urls = extract_urls(text)
    assert len(urls) == 2
    assert urls[0] == "https://example.edu/form"
    assert urls[1] == "https://example.edu/guidelines"


def test_irrelevant_messages_not_extracted():
    messages = [
        {
            "message_id": 1,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Dave",
            "text": "Are you going to the cafeteria for coffee?",
        },
        {
            "message_id": 2,
            "timestamp_text": "19/10/2026, 9:01 am",
            "sender": "Alex",
            "text": "Yes, let's meet in 10 minutes.",
        },
    ]
    items = extract_academic_items(messages)
    assert len(items) == 0


def test_system_messages_not_extracted():
    messages = [
        {
            "message_id": 1,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "System",
            "text": "Messages and calls are end-to-end encrypted.",
        },
    ]
    items = extract_academic_items(messages)
    assert len(items) == 0


def test_deadline_vs_mentioned_date_distinction():
    messages = [
        {
            "message_id": 1,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Prof",
            "text": "Assignment 1 submission deadline is due on 28/10/2026.",
        },
        {
            "message_id": 2,
            "timestamp_text": "19/10/2026, 9:05 am",
            "sender": "Rep",
            "text": "Assignment 2 was discussed on 28/10/2026.",
        },
    ]
    items = extract_academic_items(messages)
    assert len(items) == 2
    # Item 1 has explicit deadline language
    assert items[0]["date_type"] == "deadline"
    assert items[0]["review_required"] is False

    # Item 2 has a mentioned date without deadline language
    assert items[1]["date_type"] == "mentioned_date"
    assert items[1]["review_required"] is True
    assert any("deadline phrasing" in r for r in items[1]["review_reasons"])


def test_source_evidence_preservation():
    messages = [
        {
            "message_id": 42,
            "timestamp_text": "19/10/2026, 11:30 am",
            "sender": "Prof. Smith",
            "text": "Quiz 1 is scheduled for 25/10/2026 in Room 301.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["source_message_id"] == 42
    assert item["source_sender"] == "Prof. Smith"
    assert item["source_timestamp"] == "19/10/2026, 11:30 am"
    assert item["source_text"] == "Quiz 1 is scheduled for 25/10/2026 in Room 301."
    assert item["extraction_method"] == "rules"
