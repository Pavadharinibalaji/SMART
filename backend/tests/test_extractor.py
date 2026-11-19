"""Unit tests for academic information extractor (backend/extractor.py)."""

from datetime import date
import pytest
from extractor import (
    calculate_confidence,
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


# ==============================================================================
# Phase 3: Confidence Scoring & Evidence Intelligence Tests
# ==============================================================================


# 26. High-confidence explicit assignment with a clear date
def test_confidence_high_explicit_assignment():
    messages = [
        {
            "message_id": 201,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Prof. Turing",
            "text": "Assignment 1 on Distributed Consensus is released. The submission deadline is due on 28/10/2026.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["confidence"] == "HIGH"
    assert item["category"] == "Assignment"
    assert item["due_date"] == "2026-10-28"
    assert item["date_type"] == "deadline"
    assert item["review_required"] is False
    assert any("explicit calendar date" in r.lower() for r in item["confidence_reasons"])
    assert "The submission deadline is due on 28/10/2026." in item["evidence_text"]


# 27. High-confidence examination with an explicit date
def test_confidence_high_explicit_examination():
    messages = [
        {
            "message_id": 202,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Coordinator",
            "text": "The Distributed Systems midterm exam will be held on 15/11/2026 at Hall B.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["confidence"] == "HIGH"
    assert item["category"] == "Exam"
    assert item["due_date"] == "2026-11-15"
    assert item["date_type"] == "event_date"
    assert item["review_required"] is False
    assert any("explicit calendar date" in r.lower() for r in item["confidence_reasons"])


# 28. Medium-confidence task with a resolvable relative date
def test_confidence_medium_relative_date():
    messages = [
        {
            "message_id": 203,
            "timestamp_text": "19/10/2026, 9:00 am",  # Monday
            "sender": "TA Sarah",
            "text": "DBMS assignment submission is due Friday.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["confidence"] == "MEDIUM"
    assert item["category"] == "Assignment"
    assert item["due_date"] == "2026-10-23"
    assert any("relative date resolved" in r.lower() for r in item["confidence_reasons"])


# 29. Low-confidence task with ambiguous dates
def test_confidence_low_ambiguous_dates():
    # Multiple candidate dates in single task
    messages = [
        {
            "message_id": 204,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Prof",
            "text": "The project demo will be held on either 10/11/2026 or 12/11/2026.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["confidence"] == "LOW"
    assert item["due_date"] is None
    assert item["review_required"] is True
    assert any("ambiguous" in r.lower() for r in item["confidence_reasons"])


# 30. Task with no date but strong task evidence
def test_confidence_medium_no_date_strong_evidence():
    messages = [
        {
            "message_id": 205,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Prof",
            "text": "Assignment 2 is released. Please check the course portal for instructions and test cases.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["confidence"] == "MEDIUM"
    assert item["category"] == "Assignment"
    assert item["due_date"] is None
    assert any("no deadline or event date" in r.lower() for r in item["confidence_reasons"])


# 31. Ambiguous category classification
def test_confidence_low_ambiguous_category():
    # Multiple conflicting categories in one clause
    messages = [
        {
            "message_id": 206,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Office",
            "text": "Semester exam assignment guidelines are published.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["confidence"] == "LOW"
    assert item["review_required"] is True
    assert any("multiple conflicting" in r.lower() for r in item["confidence_reasons"])


# 32. Multiple tasks with correctly separated evidence
def test_multi_item_separated_evidence_and_confidence():
    messages = [
        {
            "message_id": 207,
            "timestamp_text": "19/10/2026, 9:00 am",  # Monday
            "sender": "Coordinator",
            "text": "DBMS assignment submission is Friday. CN internal exam is 25/11/2026.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 2

    # Task 1: Assignment due Friday -> relative date -> MEDIUM
    assert items[0]["category"] == "Assignment"
    assert items[0]["due_date"] == "2026-10-23"
    assert items[0]["confidence"] == "MEDIUM"
    assert "DBMS assignment submission is Friday" in items[0]["evidence_text"]
    assert "CN internal exam" not in items[0]["evidence_text"]

    # Task 2: Exam on 25/11/2026 -> explicit date -> HIGH
    assert items[1]["category"] == "Exam"
    assert items[1]["due_date"] == "2026-11-25"
    assert items[1]["confidence"] == "HIGH"
    assert "CN internal exam is 25/11/2026" in items[1]["evidence_text"]
    assert "DBMS assignment" not in items[1]["evidence_text"]


# 33. Evidence preservation for multiline messages
def test_multiline_evidence_preservation():
    messages = [
        {
            "message_id": 208,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Teacher",
            "text": "Assignment 1 is released.\nThe deadline is 28/10/2026.\nSubmit code on portal.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    item = items[0]
    assert item["confidence"] == "HIGH"
    # Evidence text reflects the source task text without alteration
    assert "Assignment 1 is released" in item["evidence_text"]
    assert "deadline is 28/10/2026" in item["evidence_text"]
    assert item["source_text"] == messages[0]["text"]


# 34. Confidence consistency across repeated extraction runs
def test_confidence_determinism_repeated_runs():
    messages = [
        {
            "message_id": 209,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Prof",
            "text": "Project demo is due on 28/10/2026. Register for the workshop before Wednesday.",
        }
    ]
    first_run = extract_academic_items(messages)
    for _ in range(5):
        subsequent_run = extract_academic_items(messages)
        assert len(first_run) == len(subsequent_run)
        for i in range(len(first_run)):
            assert first_run[i]["confidence"] == subsequent_run[i]["confidence"]
            assert first_run[i]["confidence_reasons"] == subsequent_run[i]["confidence_reasons"]
            assert first_run[i]["evidence_text"] == subsequent_run[i]["evidence_text"]


# 35. Evidence text is an exact substring of source message
def test_evidence_text_is_exact_source_substring():
    messages = [
        {
            "message_id": 210,
            "timestamp_text": "19/10/2026, 9:00 am",
            "sender": "Admin",
            "text": "Assignment 1 is due on 28/10/2026. Important Notice: holiday declared tomorrow for all students.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 2
    for item in items:
        # Every evidence_text must be derived from the source text
        assert item["evidence_text"] in item["source_text"] or item["evidence_text"].strip() in item["source_text"]


# ==============================================================================
# Phase 3.1: Category Conflict Detection & Compound Clause Evidence Isolation
# ==============================================================================


# 36. Assignment contextualized by workshop is NOT a genuine category conflict
def test_assignment_workshop_contextual_reference_not_conflict():
    """
    'Submit your lab exercise report for the robotics workshop' — 'workshop' is
    prepositional context for the submission, not an independent Event task.
    Confidence must NOT be LOW solely because 'workshop' appeared.
    """
    msg = "Submit your lab exercise report for the robotics workshop on 28/10/2026."
    results = extract_academic_items([{
        "text": msg,
        "sender": "Prof. Kumar",
        "timestamp_text": "2026-10-19 10:00",
    }])
    assert len(results) == 1
    item = results[0]
    assert item["category"] == "Assignment"
    # Explicit date with deadline language -> HIGH (not penalised for contextual 'workshop')
    assert item["confidence"] == "HIGH"
    # review_required should NOT be True due to a false category conflict
    assert item["review_required"] is False


# 37. Assignment report for a hackathon — contextual opportunity, not genuine conflict
def test_assignment_hackathon_contextual_reference_not_conflict():
    """'Submit report for the annual hackathon' — 'hackathon' is contextual, not a competing Opportunity task."""
    msg = "Submit report for the annual hackathon by 30/10/2026."
    results = extract_academic_items([{
        "text": msg,
        "sender": "Prof. Kumar",
        "timestamp_text": "2026-10-19 10:00",
    }])
    assert len(results) == 1
    item = results[0]
    assert item["category"] == "Assignment"
    assert item["confidence"] in ("HIGH", "MEDIUM")


# 38. Genuine assignment + exam conflict -> LOW confidence
def test_genuine_assignment_exam_conflict_produces_low_confidence():
    """
    'Semester exam assignment guidelines are published.' — both 'exam' and 'assignment'
    are present in the same clause without a clear primary action verb distinguishing them.
    This is a genuine category conflict and must produce LOW confidence.
    """
    msg = "Semester exam assignment guidelines are published."
    results = extract_academic_items([{
        "text": msg,
        "sender": "Prof. Kumar",
        "timestamp_text": "2026-10-19 10:00",
    }])
    assert len(results) == 1
    item = results[0]
    # Genuine conflict -> LOW
    assert item["confidence"] == "LOW"
    assert item["review_required"] is True


# 39. Comma-separated independent tasks produce isolated evidence
def test_comma_separated_tasks_evidence_isolation():
    """
    'Submit assignment 1 on 10/11/2026, CN exam on 12/11/2026.'
    Must produce two candidates with non-overlapping evidence_text.
    """
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

    assign_item = next(r for r in results if r["category"] == "Assignment")
    exam_item = next(r for r in results if r["category"] == "Exam")

    # source_text is shared across both
    assert assign_item["source_text"] == msg
    assert exam_item["source_text"] == msg

    # Evidence must not cross task boundaries
    assert "CN exam" not in assign_item["evidence_text"]
    assert "assignment 1" not in exam_item["evidence_text"].lower()


# 40. Date-safe comma preservation: "Friday, 20 November 2026" must NOT be split
def test_date_comma_not_split():
    """Commas inside dates must NOT be treated as task separators."""
    msg = "Assignment is due on Friday, 20 November 2026."
    results = extract_academic_items([{
        "text": msg,
        "sender": "Prof. Kumar",
        "timestamp_text": "2026-10-19 10:00",
    }])
    # Only one task, not split at the comma inside the date
    assert len(results) == 1
    item = results[0]
    assert item["category"] == "Assignment"


# 41. Normal sentence commas are preserved (non-academic lists)
def test_normal_comma_preserved_in_non_academic_context():
    """Commas in non-academic contexts must not trigger a split."""
    msg = "Subjects covered include OS, DBMS, and CN. Submit assignment by Friday."
    results = extract_academic_items([{
        "text": msg,
        "sender": "Prof. Kumar",
        "timestamp_text": "2026-11-14 10:00",  # Friday
    }])
    # Should produce one assignment (not misparse "OS, DBMS" as separate tasks)
    assert len(results) == 1
    assert results[0]["category"] == "Assignment"


# 42. is_contextual_secondary_keyword distinguishes context from conflict
def test_is_contextual_secondary_keyword():
    """Unit test for the _is_contextual_secondary_keyword helper function."""
    from extractor import _is_contextual_secondary_keyword

    # Prepositional workshop context for an assignment -> contextual (True)
    assert _is_contextual_secondary_keyword(
        "Assignment", "Event",
        "Submit your lab exercise report for the robotics workshop on 28/10/2026."
    ) is True

    # Hackathon as prepositional context for a submission -> contextual (True)
    assert _is_contextual_secondary_keyword(
        "Assignment", "Opportunity",
        "Submit report for the annual hackathon by 30/10/2026."
    ) is True

    # Exam + assignment: no primary assignment action verb dominating -> NOT contextual (False)
    assert _is_contextual_secondary_keyword(
        "Assignment", "Exam",
        "Semester exam assignment guidelines are published."
    ) is False

    # Assignment + exam with two distinct intents -> NOT contextual (False)
    assert _is_contextual_secondary_keyword(
        "Assignment", "Exam",
        "Submit the assignment and prepare for the semester examination."
    ) is False


# 43. Evidence reconstruction edge cases (Phase 3.2.5)
def test_evidence_reconstruction_two_identical_consecutive_segments():
    """Verify that two identical consecutive segments in a cluster are both preserved."""
    messages = [
        {
            "message_id": 301,
            "timestamp_text": "2026-11-01 10:00:00",
            "sender": "Prof",
            "text": "Assignment 1 due Nov 25.\nAssignment 1 due Nov 25.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    assert items[0]["evidence_text"] in items[0]["source_text"]
    assert items[0]["evidence_text"] == "Assignment 1 due Nov 25.\nAssignment 1 due Nov 25."


def test_evidence_reconstruction_repeated_first_and_last_segments():
    """Verify that repeated first and last segments preserve the complete cluster span."""
    messages = [
        {
            "message_id": 302,
            "timestamp_text": "2026-11-01 10:00:00",
            "sender": "Prof",
            "text": "Submit assignment 1.\nImportant details.\nSubmit assignment 1 on Nov 25.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    assert items[0]["evidence_text"] in items[0]["source_text"]
    assert items[0]["evidence_text"] == "Submit assignment 1.\nImportant details.\nSubmit assignment 1 on Nov 25."


def test_evidence_reconstruction_repeated_announcements_separated_by_different_sentences():
    """Verify that repeated announcements separated by another sentence preserve independent spans."""
    messages = [
        {
            "message_id": 303,
            "timestamp_text": "2026-11-01 10:00:00",
            "sender": "Prof",
            "text": "Assignment 1 due Nov 25.\nExam on Dec 01.\nAssignment 1 due Nov 25.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 3
    for it in items:
        assert it["evidence_text"] in it["source_text"]
    assert items[0]["evidence_text"] == "Assignment 1 due Nov 25"
    assert items[1]["evidence_text"] == "Exam on Dec 01"
    assert items[2]["evidence_text"] == "Assignment 1 due Nov 25."


def test_evidence_reconstruction_multiline_clusters_with_repeated_dates():
    """Verify that multiline clusters with repeated dates preserve all segments in evidence."""
    messages = [
        {
            "message_id": 304,
            "timestamp_text": "2026-11-01 10:00:00",
            "sender": "Prof",
            "text": "Workshop on 15/12/2026.\nMorning session on 15/12/2026.\nEvening session on 15/12/2026.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 1
    assert items[0]["evidence_text"] in items[0]["source_text"]
    assert items[0]["evidence_text"] == "Workshop on 15/12/2026.\nMorning session on 15/12/2026.\nEvening session on 15/12/2026."


def test_evidence_reconstruction_punctuation_and_blank_line_preservation():
    """Verify that blank lines, punctuation, and abbreviations are preserved without mutilation."""
    messages = [
        {
            "message_id": 305,
            "timestamp_text": "2026-11-01 10:00:00",
            "sender": "Prof",
            "text": "Notice:\n\nAssignment 1 due 20/11/2026!\n\nPlease check LMS.",
        }
    ]
    items = extract_academic_items(messages)
    assert len(items) == 2
    for it in items:
        assert it["evidence_text"] in it["source_text"]
    assert items[0]["evidence_text"] == "Notice:"
    assert items[1]["evidence_text"] == "Assignment 1 due 20/11/2026!\n\nPlease check LMS."
