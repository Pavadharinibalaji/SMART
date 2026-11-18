"""Unit tests for academic information extractor (backend/extractor.py)."""

from datetime import date
import pytest
from extractor import (
    classify_message,
    detect_date,
    extract_academic_items,
    extract_time,
    extract_urls,
    parse_message_date,
    resolve_weekday,
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


# ==============================================================================
# Phase 2: Enhanced Parsing and Extraction Intelligence Tests
# ==============================================================================

# Group A: Multi-item extraction
# 1. Assignment and examination in one message
def test_multi_item_assignment_and_examination_in_one_message():
    messages = [
        {
            "message_id": 1,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Coordinator",
            "text": "DBMS assignment submission is Friday. CN internal exam is Monday.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 2
    assert items[0]["category"] == "Assignment"
    assert "DBMS assignment" in items[0]["title"]
    assert items[0]["due_date"] == "2026-10-23"
    assert items[0]["source_message_id"] == 1
    assert items[0]["source_text"] == messages[0]["text"]

    assert items[1]["category"] == "Exam"
    assert "CN internal exam" in items[1]["title"]
    assert items[1]["due_date"] == "2026-10-26"
    assert items[1]["source_message_id"] == 1
    assert items[1]["source_text"] == messages[0]["text"]


# 2. Assignment, examination, and event in one message
def test_multi_item_assignment_examination_and_event_in_one_message():
    messages = [
        {
            "message_id": 2,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Coordinator",
            "text": "DBMS assignment submission is Friday. CN internal exam is Monday. Register for the AI workshop before Wednesday.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 3
    categories = [i["category"] for i in items]
    assert "Assignment" in categories
    assert "Exam" in categories
    assert any(c in ("Event", "Opportunity") for c in categories)


# 3. Registration deadline and event date in one message
def test_multi_item_registration_deadline_and_event_date_in_one_message():
    messages = [
        {
            "message_id": 3,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Workshop Chair",
            "text": "Workshop registration closes on Wednesday. The workshop will be held on Saturday.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 2
    reg_item = next(i for i in items if i["date_type"] == "deadline")
    assert reg_item["due_date"] == "2026-10-21"  # Wednesday
    event_item = next(i for i in items if i["date_type"] == "event_date")
    assert event_item["due_date"] == "2026-10-24"  # Saturday


# 4. Single-task message still works
def test_single_task_message_still_works():
    messages = [
        {
            "message_id": 4,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Teacher",
            "text": "Assignment 1 on Distributed Systems is due on 28/10/2026.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    assert items[0]["category"] == "Assignment"
    assert items[0]["due_date"] == "2026-10-28"


# 5. No duplicate candidates for multiline single task
def test_no_duplicate_candidates_for_multiline_task():
    messages = [
        {
            "message_id": 5,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Teacher",
            "text": "Assignment 1 is released.\nThe deadline is 28/10/2026.\nSubmit code on portal.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    assert items[0]["category"] == "Assignment"
    assert items[0]["due_date"] == "2026-10-28"


# Group B: Multiple dates
# 6. Two explicit dates associated with two tasks
def test_two_explicit_dates_associated_with_two_tasks():
    messages = [
        {
            "message_id": 6,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Dept Rep",
            "text": "Assignment submission is due on 20 November 2026. The internal examination is on 25 November 2026.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 2
    assignment_item = next(i for i in items if i["category"] == "Assignment")
    exam_item = next(i for i in items if i["category"] == "Exam")
    assert assignment_item["due_date"] == "2026-11-20"
    assert exam_item["due_date"] == "2026-11-25"


# 7. Two relative weekdays associated with two tasks
def test_two_relative_weekdays_associated_with_two_tasks():
    messages = [
        {
            "message_id": 7,
            "timestamp_text": "19/10/2026, 9:00 am",  # Monday
            "sender": "Dept Rep",
            "text": "DBMS assignment is due on Friday. Operating Systems quiz is on Monday.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 2
    assert items[0]["due_date"] == "2026-10-23"  # Friday
    assert items[1]["due_date"] == "2026-10-26"  # Monday


# 8. Multiple dates in one sentence with ambiguous association
def test_multiple_dates_in_one_sentence_ambiguous_association():
    messages = [
        {
            "message_id": 8,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Teacher",
            "text": "The project demo will be held on either 10/11/2026 or 12/11/2026.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    assert items[0]["review_required"] is True
    assert items[0]["date_status"] == "needs_review"
    assert items[0]["due_date"] is None
    assert any("Multiple candidate dates" in r for r in items[0]["review_reasons"])


# 9. Date association does not leak across unrelated tasks
def test_date_association_does_not_leak_across_tasks():
    messages = [
        {
            "message_id": 9,
            "timestamp_text": "19/10/2026, 9:00 am",  # Monday
            "sender": "Admin",
            "text": "Assignment 1 is due on 28/10/2026. Important Notice: holiday declared tomorrow for all students.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 2
    assign_item = next(i for i in items if i["category"] == "Assignment")
    notice_item = next(i for i in items if i["category"] == "Announcement")
    assert assign_item["due_date"] == "2026-10-28"
    assert notice_item["due_date"] == "2026-10-20"  # tomorrow


# Group C: Deadline times
# 10. 11:59 PM
def test_extract_time_1159_pm():
    res = extract_time("Submit the assignment by 11:59 PM on Friday.")
    assert res["time_text"] == "11:59 PM"
    assert res["deadline_time"] == "23:59"


# 11. 9:30 AM
def test_extract_time_930_am():
    res = extract_time("Internal examination starts at 9:30 AM on Monday.")
    assert res["time_text"] == "9:30 AM"
    assert res["deadline_time"] == "09:30"


# 12. 24-hour time
def test_extract_time_24_hour():
    res1 = extract_time("Submit report before 14:30 on Friday.")
    assert res1["time_text"] == "14:30"
    assert res1["deadline_time"] == "14:30"

    res2 = extract_time("Project portal closes at 23:59.")
    assert res2["time_text"] == "23:59"
    assert res2["deadline_time"] == "23:59"


# 13. Time without minutes
def test_extract_time_without_minutes():
    res_pm = extract_time("Guest lecture at 5 PM on Tuesday.")
    assert res_pm["time_text"] == "5 PM"
    assert res_pm["deadline_time"] == "17:00"

    res_am = extract_time("Meeting starts at 9 AM.")
    assert res_am["time_text"] == "9 AM"
    assert res_am["deadline_time"] == "09:00"


# 14. Missing time remains missing
def test_missing_time_remains_missing():
    res = extract_time("Assignment is due on Friday.")
    assert res["time_text"] is None
    assert res["deadline_time"] is None


# Group D: Relative weekdays
# 15. Tomorrow
def test_relative_weekday_tomorrow():
    res = detect_date("Assignment is due tomorrow!", "19/10/2026, 10:00 am")
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-10-20"


# 16. Day after tomorrow
def test_relative_weekday_day_after_tomorrow():
    res = detect_date("Project submission is day after tomorrow.", "19/10/2026, 10:00 am")
    assert res["date_status"] == "resolved_from_message_date"
    assert res["due_date"] == "2026-10-21"


# 17. Bare weekday
def test_relative_bare_weekday():
    # Message sent on Monday 19/10/2026
    timestamp = "19/10/2026, 9:00 am"
    res_fri = detect_date("Assignment is due Friday.", timestamp)
    assert res_fri["due_date"] == "2026-10-23"

    res_mon = detect_date("Next lecture on Monday.", timestamp)
    assert res_mon["due_date"] == "2026-10-26"


# 18. Next Monday
def test_relative_next_weekday():
    # Message sent on Monday 19/10/2026
    timestamp = "19/10/2026, 9:00 am"
    res_next_mon = detect_date("Midterm exam is next Monday.", timestamp)
    assert res_next_mon["due_date"] == "2026-10-26"

    # Next Friday from Monday is in the following week (+11 days)
    res_next_fri = detect_date("Project due next Friday.", timestamp)
    assert res_next_fri["due_date"] == "2026-10-30"


# 19. Message timestamp unavailable
def test_relative_weekday_timestamp_unavailable():
    res = detect_date("Assignment is due Friday.", "")
    assert res["due_date"] is None
    assert res["date_status"] == "needs_review"


# 20. Weekday at a year boundary
def test_relative_weekday_year_boundary():
    # Wednesday, December 30, 2026
    timestamp = "30/12/2026, 10:00 am"
    res_fri = detect_date("Lab record due Friday.", timestamp)
    assert res_fri["due_date"] == "2027-01-01"

    res_next_mon = detect_date("Exam scheduled for next Monday.", timestamp)
    assert res_next_mon["due_date"] == "2027-01-04"


# Group E: International dates
# 21. DD/MM/YYYY
def test_international_date_slash():
    res = detect_date("Final submission is 28/10/2026.", "19/10/2026, 9:00 am")
    assert res["due_date"] == "2026-10-28"
    assert res["date_status"] == "parsed"


# 22. DD-MM-YYYY
def test_international_date_hyphen():
    res = detect_date("Final submission is 28-10-2026.", "19/10/2026, 9:00 am")
    assert res["due_date"] == "2026-10-28"
    assert res["date_status"] == "parsed"


# 23. DD.MM.YYYY
def test_international_date_dot():
    res = detect_date("Final submission is 28.10.2026.", "19/10/2026, 9:00 am")
    assert res["due_date"] == "2026-10-28"
    assert res["date_status"] == "parsed"


# 24. Textual month formats
def test_textual_month_formats():
    res1 = detect_date("Workshop on 15 November 2026.", "19/10/2026, 9:00 am")
    assert res1["due_date"] == "2026-11-15"

    res2 = detect_date("Final paper due on December 5, 2026.", "19/10/2026, 9:00 am")
    assert res2["due_date"] == "2026-12-05"


# 25. Ambiguous numeric date remains flagged
def test_ambiguous_numeric_date_remains_flagged():
    res = detect_date("Meeting on 05/06/2026.", "19/10/2026, 9:00 am")
    assert res["due_date"] is None
    assert res["date_status"] == "needs_review"
    assert "ambiguous" in res["date_reasons"][0].lower()
