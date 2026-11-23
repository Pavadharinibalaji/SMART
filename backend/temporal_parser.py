"""Temporal Expression Parsing and Relative Date Intelligence Module for SMART.

Provides deterministic parsing and resolution of temporal expressions in academic
communications (assignments, exams, announcements, events, and opportunities)
anchored to the original source message timestamp.

Guiding Principles:
1. Reference Anchor: Resolves relative dates strictly from the source message timestamp date,
   NEVER the current system date or runtime execution date.
2. Conservative Handling: If the source timestamp is missing, malformed, or ambiguous,
   the expression remains unresolved (due_date=None, date_status='needs_review').
3. Timezone Awareness: WhatsApp exports are timezone-naive local representations; we do not
   invent an artificial timezone or shift calendar dates unexpectedly.
4. Non-fabrication: Relative date resolution does not promote unverified expressions to HIGH
   confidence; ambiguous phrases ("soon", "within a few days") strictly require review.
5. Range Protection: Multi-day ranges are not collapsed into a single speculative deadline.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
import re
from typing import Any

# ==============================================================================
# 1. Number and Weekday Mappings
# ==============================================================================

NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "a": 1,
    "an": 1,
}

WEEKDAY_MAP: dict[str, int] = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

MONTH_NAMES = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)

# Basic relative day offsets relative to message date
BASIC_RELATIVE_DAYS: dict[str, int] = {
    "today": 0,
    "tonight": 0,
    "this morning": 0,
    "this evening": 0,
    "tomorrow": 1,
    "day after tomorrow": 2,
    "yesterday": -1,
}

# ==============================================================================
# 2. Regular Expressions
# ==============================================================================

# Time patterns
TIME_12H_WITH_MINUTES = re.compile(
    r"\b(?P<hour>1[0-2]|0?[1-9])[:.](?P<minute>[0-5]\d)\s*(?P<ampm>[AaPp]\.?[Mm]\.?)\b"
)
TIME_12H_NO_MINUTES = re.compile(
    r"\b(?P<hour>1[0-2]|0?[1-9])\s*(?P<ampm>[AaPp]\.?[Mm]\.?)\b"
)
TIME_24H = re.compile(
    r"\b(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)\b(?!\s*[:/.-]\d)"
)

# Explicit date regexes
# 1. Day Month Year (e.g. 24th October 2026, 24 Oct 2026, 20 November 2026)
PATTERN_DAY_MONTH_YEAR = re.compile(
    rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<month>{MONTH_NAMES})(?:,?\s+(?P<year>\d{{4}}))\b",
    re.IGNORECASE,
)

# 2. Month Day Year (e.g. October 24th, 2026 or December 5, 2026)
PATTERN_MONTH_DAY_YEAR = re.compile(
    rf"\b(?P<month>{MONTH_NAMES})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{{4}}))\b",
    re.IGNORECASE,
)

# 3. Numeric dates (DD/MM/YYYY or DD-MM-YYYY or YYYY-MM-DD or DD.MM.YYYY)
PATTERN_NUMERIC_FULL = re.compile(
    r"\b(?P<p1>\d{1,4})[./-](?P<p2>\d{1,2})[./-](?P<p3>\d{2,4})\b"
)

# 4. Day Month WITHOUT Year (e.g. 24th October, October 24) -> Must NOT invent year
PATTERN_DAY_MONTH_NO_YEAR = re.compile(
    rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<month>{MONTH_NAMES})\b(?!,?\s+\d{{4}})",
    re.IGNORECASE,
)
PATTERN_MONTH_DAY_NO_YEAR = re.compile(
    rf"\b(?P<month>{MONTH_NAMES})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\b(?!,?\s+\d{{4}})",
    re.IGNORECASE,
)

# 4b. Numeric day and month without year (e.g. 25/11, 25-11, 25.11, 05/11)
PATTERN_NUMERIC_DAY_MONTH_NO_YEAR = re.compile(
    r"\b(?P<p1>\d{1,2})[./-](?P<p2>\d{1,2})\b(?!\s*[:/.-]\d)(?!\s*(?:am|pm|[ap]\.m\.|hrs?|hours?))",
    re.IGNORECASE,
)

# 5. Basic relative day expressions
PATTERN_BASIC_RELATIVE = re.compile(
    r"\b(?:day\s+after\s+tomorrow|tomorrow|today|tonight|this\s+morning|this\s+evening|yesterday)\b",
    re.IGNORECASE,
)

# 6. Relative duration expressions (within 2 days, in 3 days, after 5 days, within one week, in two weeks, after 10 days)
PATTERN_RELATIVE_DURATION = re.compile(
    r"\b(?P<prefix>within|in|after)\s+"
    r"(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an)\s+"
    r"(?P<unit>days?|weeks?)\b",
    re.IGNORECASE,
)

# 7. Month-end expressions (end of the month, by the end of the month, end of this month)
PATTERN_MONTH_END = re.compile(
    r"\b(?:(?:by|before|at)\s+the\s+)?end\s+of\s+(?:the|this)\s+month\b",
    re.IGNORECASE,
)

# 8. Relative weekday expressions (this Friday, next Monday, coming Wednesday, by Friday, before Monday, on Monday, Friday)
PATTERN_RELATIVE_WEEKDAY = re.compile(
    r"\b(?:(?P<modifier>this|next|coming|by|before|on)\s+)?"
    r"(?P<weekday>monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat|sunday|sun)\b",
    re.IGNORECASE,
)

# 9. Date ranges (from Monday to Wednesday, between Friday and Sunday, Monday through Thursday)
PATTERN_DATE_RANGE = re.compile(
    r"\b(?:"
    r"from\s+(?P<r1_start>[A-Za-z0-9/.-]+(?:\s+[A-Za-z0-9]+)?)\s+(?:to|until|till)\s+(?P<r1_end>[A-Za-z0-9/.-]+(?:\s+[A-Za-z0-9]+)?)"
    r"|"
    r"between\s+(?P<r2_start>[A-Za-z0-9/.-]+(?:\s+[A-Za-z0-9]+)?)\s+and\s+(?P<r2_end>[A-Za-z0-9/.-]+(?:\s+[A-Za-z0-9]+)?)"
    r"|"
    r"(?P<r3_start>[A-Za-z0-9/.-]+)\s+through\s+(?P<r3_end>[A-Za-z0-9/.-]+)"
    r")\b",
    re.IGNORECASE,
)

# 10. Ambiguous temporal expressions requiring human review
PATTERN_AMBIGUOUS_RELATIVE = re.compile(
    r"\b(?:soon|within\s+a\s+few\s+days|in\s+a\s+few\s+days|in\s+a\s+couple\s+(?:of\s+)?days|later\s+this\s+week|at\s+some\s+point)\b",
    re.IGNORECASE,
)

# 11. Incomplete and unanchored temporal expressions (asap, announced later, before lunch, next week)
PATTERN_INCOMPLETE_TEMPORAL = re.compile(
    r"\b(?:"
    r"asap|as\s+soon\s+as\s+possible|"
    r"(?:will\s+be\s+)?announced\s+later|(?:will\s+be\s+)?notified\s+later|"
    r"to\s+be\s+announced|to\s+be\s+decided|tba|tbd|"
    r"(?:before|after)\s+lunch|"
    r"next\s+week|sometime\s+next\s+week|later\s+next\s+week"
    r")\b",
    re.IGNORECASE,
)


# ==============================================================================
# 3. Helper Functions
# ==============================================================================

def clean_ordinal(text: str) -> str:
    """Strip st/nd/rd/th suffix from numeric day (e.g. '24th' -> '24')."""
    return re.sub(r"(\d+)(?:st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)


def parse_number(val: str) -> int | None:
    """Parse numeric digit or written English number word into an integer."""
    clean = val.strip().lower()
    if clean.isdigit():
        return int(clean)
    return NUMBER_WORDS.get(clean)


def parse_reference_timestamp(timestamp_text: str | None) -> date | None:
    """Extract and parse the calendar date from a WhatsApp message timestamp.

    Supports:
    - Standard WhatsApp exports (iOS & Android): '19/10/2026, 9:00 am', '[19/10/2026, 09:00:00]'
    - ISO 8601 timestamps: '2026-11-20T10:00:00Z', '2026-11-20T10:00:00+05:30', '2026-11-20'
    - Common date separators: slash (/), dash (-), dot (.)

    Timezone Behavior:
    WhatsApp export timestamps are timezone-naive local representations.
    For ISO strings with timezone offsets, the calendar date in that representation
    is preserved directly without unexpected shifting to UTC.
    """
    if not timestamp_text:
        return None

    clean = timestamp_text.strip().strip("[]")
    if not clean:
        return None

    # Handle ISO formats first
    if "T" in clean:
        try:
            iso_dt = datetime.fromisoformat(clean.replace("Z", "+00:00"))
            return iso_dt.date()
        except (ValueError, TypeError):
            pass

    # Extract date portion before comma or time separator
    date_part = clean.split(",", 1)[0].strip()
    # If no comma, check if separated by space
    if " " in date_part and not ("/" in date_part or "-" in date_part or "." in date_part):
        date_part = date_part.split(" ", 1)[0].strip()

    for fmt in (
        "%d/%m/%Y", "%d/%m/%y",
        "%d-%m-%Y", "%d-%m-%y",
        "%d.%m.%Y", "%d.%m.%y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(date_part, fmt).date()
        except ValueError:
            continue

    return None


# Backward-compatible alias
parse_message_date = parse_reference_timestamp


def extract_time(text: str) -> dict[str, str | None]:
    """Extract deadline or event time from text, returning raw text and normalized HH:MM."""
    if not text:
        return {"time_text": None, "deadline_time": None}

    # 1. 12-hour format with minutes (e.g. 11:59 PM, 9:30 AM)
    m = TIME_12H_WITH_MINUTES.search(text)
    if m:
        h = int(m.group("hour"))
        minute = int(m.group("minute"))
        ampm = m.group("ampm").replace(".", "").upper()
        if ampm == "PM" and h != 12:
            h += 12
        elif ampm == "AM" and h == 12:
            h = 0
        return {
            "time_text": m.group(0).strip(),
            "deadline_time": f"{h:02d}:{minute:02d}",
        }

    # 2. 12-hour format without minutes (e.g. 5 PM, 9 AM)
    m = TIME_12H_NO_MINUTES.search(text)
    if m:
        h = int(m.group("hour"))
        ampm = m.group("ampm").replace(".", "").upper()
        if ampm == "PM" and h != 12:
            h += 12
        elif ampm == "AM" and h == 12:
            h = 0
        return {
            "time_text": m.group(0).strip(),
            "deadline_time": f"{h:02d}:00",
        }

    # 3. 24-hour format HH:MM (e.g. 14:30, 23:59)
    m = TIME_24H.search(text)
    if m:
        h = int(m.group("hour"))
        minute = int(m.group("minute"))
        return {
            "time_text": m.group(0).strip(),
            "deadline_time": f"{h:02d}:{minute:02d}",
        }

    return {"time_text": None, "deadline_time": None}


# ==============================================================================
# 4. Weekday Resolution Logic
# ==============================================================================

def resolve_weekday(text: str, message_date: date | None) -> dict[str, Any] | None:
    """Resolve a relative weekday expression using message timestamp date as anchor.

    Resolution Rules (anchored to ref_date, ref_w):
    - 'by <weekday>':
      Resolves to that target weekday itself ((target_w - ref_w) % 7, or +7d if today).
      e.g. From Friday 2026-11-20: 'by Monday' -> 2026-11-23.
    - 'before <weekday>':
      Strictly prior to the target day: computes the upcoming target weekday date,
      then subtracts 1 calendar day ((days_to_target - 1)).
      e.g. From Friday 2026-11-20: 'before Monday' -> 2026-11-22 (Sunday).
    - 'on <weekday>' / bare '<weekday>':
      Resolves to the upcoming occurrence of that weekday.
      e.g. From Friday 2026-11-20: 'on Monday' -> 2026-11-23.
    - 'this <weekday>':
      - If target_w == ref_w: 0 days (today, e.g. 'this Friday' on Friday is today, 2026-11-20).
      - If target_w > ref_w: target_w - ref_w (upcoming day in current calendar week).
      - If target_w < ref_w: day in current week has already passed; flags needs_review to prevent expired assumptions.
    - 'next <weekday>':
      - If target_w <= ref_w: (target_w - ref_w) % 7 or 7 if 0 (e.g. 'next Monday' on Friday is +3d -> 2026-11-23; on Monday is +7d).
      - If target_w > ref_w: (target_w - ref_w) + 7 (day in subsequent week; e.g. 'next Friday' on Monday is +11d).
    - 'coming <weekday>':
      (target_w - ref_w) % 7 or 7 if 0 (the immediately next occurrence).
    """
    if not text:
        return None

    m = PATTERN_RELATIVE_WEEKDAY.search(text)
    if not m:
        return None

    raw_snippet = m.group(0).strip()
    modifier = (m.group("modifier") or "").lower()
    weekday_str = m.group("weekday").lower()
    target_w = WEEKDAY_MAP.get(weekday_str)
    if target_w is None:
        return None

    if message_date is None:
        return {
            "date_text": raw_snippet,
            "due_date": None,
            "date_status": "needs_review",
            "date_reasons": [
                f"Relative weekday '{raw_snippet}' detected, but message timestamp date is missing or unparseable. SMART does not assume current system date."
            ],
        }

    ref_w = message_date.weekday()

    if modifier == "this":
        if target_w == ref_w:
            days_ahead = 0
        elif target_w > ref_w:
            days_ahead = target_w - ref_w
        else:
            return {
                "date_text": raw_snippet,
                "due_date": None,
                "date_status": "needs_review",
                "date_reasons": [
                    f"Relative weekday '{raw_snippet}' refers to a day that has already passed in the current week ({message_date.isoformat()}). Marked for human review."
                ],
            }
    elif modifier == "next":
        if target_w <= ref_w:
            days_ahead = (target_w - ref_w) % 7
            if days_ahead == 0:
                days_ahead = 7
        else:
            days_ahead = (target_w - ref_w) + 7
    elif modifier == "coming":
        days_ahead = (target_w - ref_w) % 7
        if days_ahead == 0:
            days_ahead = 7
    elif modifier == "by":
        days_ahead = (target_w - ref_w) % 7
        if days_ahead == 0:
            days_ahead = 7
    elif modifier == "before":
        days_to_target = (target_w - ref_w) % 7
        if days_to_target == 0:
            days_to_target = 7
        days_ahead = days_to_target - 1
    else:  # bare weekday or 'on <weekday>'
        if target_w > ref_w:
            days_ahead = target_w - ref_w
        else:
            days_ahead = (target_w - ref_w) % 7
            if days_ahead == 0:
                days_ahead = 7

    resolved = message_date + timedelta(days=days_ahead)
    return {
        "date_text": raw_snippet,
        "due_date": resolved.isoformat(),
        "date_status": "resolved_from_message_date",
        "date_reasons": [
            f"Resolved relative weekday '{raw_snippet}' (+{days_ahead}d) using message timestamp date {message_date.isoformat()}."
        ],
    }


# ==============================================================================
# 5. Core Detection Engine
# ==============================================================================

def detect_all_dates(text: str, timestamp_text: str | None) -> list[dict[str, Any]]:
    """Detect all date expressions in text, resolving dates and preserving spans.

    Evaluates expressions with explicit priority ordering:
    - Priority 1: Day Month Year (explicit date with year)
    - Priority 2: Month Day Year (explicit date with year)
    - Priority 3: Numeric Full (DD/MM/YYYY, YYYY-MM-DD)
    - Priority 4: Basic relative day expressions (today, tomorrow, day after tomorrow, tonight, this morning, this evening, yesterday)
    - Priority 5: Relative durations (within 2 days, in 3 days, after 5 days, within one week, in two weeks, end of the month)
    - Priority 6: Day Month without Year (strictly requires review; no year invented)
    - Priority 7: Relative weekdays (this Friday, next Monday, coming Wednesday, by Friday, before Monday, on Friday)
    - Priority 8: Ambiguous relative expressions (soon, within a few days)
    - Priority 9: Date ranges (from X to Y, between X and Y, X through Y)
    """
    if not text:
        return []

    message_date = parse_reference_timestamp(timestamp_text)
    candidates: list[dict[str, Any]] = []

    # Priority 1: Day Month Year (e.g. 24 October 2026, 20 November 2026)
    for m in PATTERN_DAY_MONTH_YEAR.finditer(text):
        raw_snippet = m.group(0).strip()
        cleaned = clean_ordinal(raw_snippet)
        for fmt in ("%d %B %Y", "%d %b %Y", "%d of %B %Y", "%d of %b %Y"):
            try:
                dt = datetime.strptime(cleaned, fmt).date()
                start_idx = m.start()
                full_snippet = raw_snippet
                preceding = text[:m.start()].rstrip(" ,")
                m_weekday = re.search(r"\b(?P<stated_weekday>monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat|sunday|sun)\b\s*,?\s*$", preceding, re.I)
                if m_weekday:
                    stated = m_weekday.group("stated_weekday").lower()
                    stated_w = WEEKDAY_MAP.get(stated)
                    actual_w = dt.weekday()
                    start_idx = m_weekday.start()
                    full_snippet = text[start_idx:m.end()].strip()
                    if stated_w is not None and stated_w != actual_w:
                        candidates.append({
                            "start": start_idx,
                            "end": m.end(),
                            "priority": 1,
                            "date_text": full_snippet,
                            "due_date": None,
                            "date_status": "needs_review",
                            "date_reasons": [
                                f"Conflicting temporal information: {dt.strftime('%d %B %Y')} is a {calendar.day_name[actual_w]}, which conflicts with stated weekday '{m_weekday.group('stated_weekday')}'. Marked for review without guessing."
                            ],
                        })
                        break

                candidates.append({
                    "start": start_idx,
                    "end": m.end(),
                    "priority": 1,
                    "date_text": full_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["Explicit date with year detected and validated."],
                })
                break
            except ValueError:
                continue

    # Priority 2: Month Day Year (e.g. October 24, 2026, December 5, 2026)
    for m in PATTERN_MONTH_DAY_YEAR.finditer(text):
        raw_snippet = m.group(0).strip()
        cleaned = clean_ordinal(raw_snippet).replace(",", "")
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                dt = datetime.strptime(cleaned, fmt).date()
                start_idx = m.start()
                full_snippet = raw_snippet
                preceding = text[:m.start()].rstrip(" ,")
                m_weekday = re.search(r"\b(?P<stated_weekday>monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat|sunday|sun)\b\s*,?\s*$", preceding, re.I)
                if m_weekday:
                    stated = m_weekday.group("stated_weekday").lower()
                    stated_w = WEEKDAY_MAP.get(stated)
                    actual_w = dt.weekday()
                    start_idx = m_weekday.start()
                    full_snippet = text[start_idx:m.end()].strip()
                    if stated_w is not None and stated_w != actual_w:
                        candidates.append({
                            "start": start_idx,
                            "end": m.end(),
                            "priority": 2,
                            "date_text": full_snippet,
                            "due_date": None,
                            "date_status": "needs_review",
                            "date_reasons": [
                                f"Conflicting temporal information: {dt.strftime('%d %B %Y')} is a {calendar.day_name[actual_w]}, which conflicts with stated weekday '{m_weekday.group('stated_weekday')}'. Marked for review without guessing."
                            ],
                        })
                        break

                candidates.append({
                    "start": start_idx,
                    "end": m.end(),
                    "priority": 2,
                    "date_text": full_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["Explicit date with year detected and validated."],
                })
                break
            except ValueError:
                continue

    # Priority 3: Numeric Full (e.g. 28/10/2026, 28-10-2026, 28.10.2026, 2026-10-28)
    for num_match in PATTERN_NUMERIC_FULL.finditer(text):
        p1 = num_match.group("p1")
        p2 = num_match.group("p2")
        p3 = num_match.group("p3")
        raw_snippet = num_match.group(0).strip()

        # ISO YYYY-MM-DD
        if len(p1) == 4:
            try:
                dt = datetime.strptime(raw_snippet, "%Y-%m-%d").date()
                candidates.append({
                    "start": num_match.start(),
                    "end": num_match.end(),
                    "priority": 3,
                    "date_text": raw_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["ISO date detected and validated."],
                })
                continue
            except ValueError:
                pass

        v1 = int(p1)
        v2 = int(p2)

        # Ambiguous DD/MM vs MM/DD
        if v1 <= 12 and v2 <= 12 and v1 != v2:
            candidates.append({
                "start": num_match.start(),
                "end": num_match.end(),
                "priority": 3,
                "date_text": raw_snippet,
                "due_date": None,
                "date_status": "needs_review",
                "date_reasons": [
                    f"Numeric date '{raw_snippet}' is ambiguous between DD/MM and MM/DD format."
                ],
            })
            continue

        year_len = len(p3)
        sep = "/" if "/" in raw_snippet else ("-" if "-" in raw_snippet else ".")

        # Unambiguous DD/MM
        if v1 > 12 and v2 <= 12:
            fmt = f"%d{sep}%m{sep}%Y" if year_len == 4 else f"%d{sep}%m{sep}%y"
            try:
                dt = datetime.strptime(raw_snippet, fmt).date()
                candidates.append({
                    "start": num_match.start(),
                    "end": num_match.end(),
                    "priority": 3,
                    "date_text": raw_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["Unambiguous day-first numeric date parsed."],
                })
                continue
            except ValueError:
                pass

        # Unambiguous MM/DD
        if v1 <= 12 and v2 > 12:
            fmt = f"%m{sep}%d{sep}%Y" if year_len == 4 else f"%m{sep}%d{sep}%y"
            try:
                dt = datetime.strptime(raw_snippet, fmt).date()
                candidates.append({
                    "start": num_match.start(),
                    "end": num_match.end(),
                    "priority": 3,
                    "date_text": raw_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["Unambiguous month-first numeric date parsed."],
                })
                continue
            except ValueError:
                pass

        # Identical day and month
        if v1 == v2 and v1 <= 12:
            fmt = f"%d{sep}%m{sep}%Y" if year_len == 4 else f"%d{sep}%m{sep}%y"
            try:
                dt = datetime.strptime(raw_snippet, fmt).date()
                candidates.append({
                    "start": num_match.start(),
                    "end": num_match.end(),
                    "priority": 3,
                    "date_text": raw_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["Identical day and month numeric date parsed."],
                })
                continue
            except ValueError:
                pass

        # Fallback numeric
        candidates.append({
            "start": num_match.start(),
            "end": num_match.end(),
            "priority": 3,
            "date_text": raw_snippet,
            "due_date": None,
            "date_status": "needs_review",
            "date_reasons": [f"Numeric date '{raw_snippet}' could not be parsed confidently."],
        })

    # Priority 4: Date ranges (from Monday to Wednesday, between Friday and Sunday, Monday through Thursday)
    for m in PATTERN_DATE_RANGE.finditer(text):
        raw_snippet = m.group(0).strip()
        preceding = text[:m.start()]
        is_update_transition = bool(re.search(r"\b(?:extended|rescheduled|postponed|moved|deferred|revised)\s+(?:from\s+)?$", preceding, re.I))
        if is_update_transition:
            # Deadline update transition (e.g. "extended from 20 November to 25 November")
            candidates.append({
                "start": m.start(),
                "end": m.end(),
                "priority": 4,
                "date_text": raw_snippet,
                "due_date": None,
                "date_status": "needs_review",
                "is_range": False,
                "date_reasons": [
                    f"Deadline update transition detected ('{raw_snippet}')."
                ],
            })
        else:
            candidates.append({
                "start": m.start(),
                "end": m.end(),
                "priority": 4,
                "date_text": raw_snippet,
                "due_date": None,
                "date_status": "needs_review",
                "is_range": True,
                "date_reasons": [
                    f"Date range detected ('{raw_snippet}'); multi-day event/schedule requires human review and must not be collapsed into a single deadline."
                ],
            })

    # Priority 5: Basic relative day expressions
    for m in PATTERN_BASIC_RELATIVE.finditer(text):
        raw_snippet = m.group(0).strip()
        phrase_key = re.sub(r"\s+", " ", raw_snippet.lower())
        offset = BASIC_RELATIVE_DAYS.get(phrase_key)
        if offset is not None:
            if message_date is not None:
                resolved = message_date + timedelta(days=offset)
                candidates.append({
                    "start": m.start(),
                    "end": m.end(),
                    "priority": 5,
                    "date_text": raw_snippet,
                    "due_date": resolved.isoformat(),
                    "date_status": "resolved_from_message_date",
                    "date_reasons": [
                        f"Resolved relative expression '{raw_snippet}' ({'+' if offset >= 0 else ''}{offset}d) using message timestamp date {message_date.isoformat()}."
                    ],
                })
            else:
                candidates.append({
                    "start": m.start(),
                    "end": m.end(),
                    "priority": 5,
                    "date_text": raw_snippet,
                    "due_date": None,
                    "date_status": "needs_review",
                    "date_reasons": [
                        f"Relative date '{raw_snippet}' detected, but message timestamp date could not be parsed confidently."
                    ],
                })

    # Priority 6: Relative duration expressions & Month-end expressions
    for m in PATTERN_RELATIVE_DURATION.finditer(text):
        raw_snippet = m.group(0).strip()
        count_val = parse_number(m.group("count"))
        unit_str = m.group("unit").lower()
        if count_val is not None and count_val > 0:
            days_offset = count_val * 7 if "week" in unit_str else count_val
            if message_date is not None:
                resolved = message_date + timedelta(days=days_offset)
                candidates.append({
                    "start": m.start(),
                    "end": m.end(),
                    "priority": 6,
                    "date_text": raw_snippet,
                    "due_date": resolved.isoformat(),
                    "date_status": "resolved_from_message_date",
                    "date_reasons": [
                        f"Resolved relative duration '{raw_snippet}' (+{days_offset}d) using message timestamp date {message_date.isoformat()}."
                    ],
                })
            else:
                candidates.append({
                    "start": m.start(),
                    "end": m.end(),
                    "priority": 6,
                    "date_text": raw_snippet,
                    "due_date": None,
                    "date_status": "needs_review",
                    "date_reasons": [
                        f"Relative duration '{raw_snippet}' detected, but message timestamp date is missing or unparseable."
                    ],
                })

    for m in PATTERN_MONTH_END.finditer(text):
        raw_snippet = m.group(0).strip()
        if message_date is not None:
            last_day = calendar.monthrange(message_date.year, message_date.month)[1]
            resolved = date(message_date.year, message_date.month, last_day)
            candidates.append({
                "start": m.start(),
                "end": m.end(),
                "priority": 6,
                "date_text": raw_snippet,
                "due_date": resolved.isoformat(),
                "date_status": "resolved_from_message_date",
                "date_reasons": [
                    f"Resolved month-end expression '{raw_snippet}' to last day of month {resolved.isoformat()} using message timestamp date {message_date.isoformat()}."
                ],
            })
        else:
            candidates.append({
                "start": m.start(),
                "end": m.end(),
                "priority": 6,
                "date_text": raw_snippet,
                "due_date": None,
                "date_status": "needs_review",
                "date_reasons": [
                    f"Month-end expression '{raw_snippet}' detected, but message timestamp date is missing or unparseable."
                ],
            })

    # Priority 7: Month + Day WITHOUT Year (strictly requires review; no year invented)
    for pat in (PATTERN_DAY_MONTH_NO_YEAR, PATTERN_MONTH_DAY_NO_YEAR):
        for m in pat.finditer(text):
            raw_snippet = m.group(0).strip()
            start_idx = m.start()
            full_snippet = raw_snippet
            reasons = [f"Date '{raw_snippet}' specifies day and month without a year. SMART does not assume a year."]

            # Check if a weekday precedes it (e.g. "Monday, 24 November")
            preceding = text[:m.start()].rstrip(" ,")
            m_weekday = re.search(r"\b(?P<stated_weekday>monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat|sunday|sun)\b\s*,?\s*$", preceding, re.I)
            if m_weekday:
                start_idx = m_weekday.start()
                full_snippet = text[start_idx:m.end()].strip()
                stated = m_weekday.group("stated_weekday").lower()
                stated_w = WEEKDAY_MAP.get(stated)
                if message_date and stated_w is not None:
                    try:
                        clean_dm = clean_ordinal(raw_snippet).replace(",", "")
                        for fmt in ("%d %B", "%d %b", "%B %d", "%b %d", "%d of %B", "%d of %b"):
                            try:
                                parsed_dm = datetime.strptime(clean_dm, fmt)
                                check_dt = date(message_date.year, parsed_dm.month, parsed_dm.day)
                                if check_dt.weekday() != stated_w:
                                    reasons = [
                                        f"Conflicting temporal information: {check_dt.strftime('%d %B')} in message year {message_date.year} is a {calendar.day_name[check_dt.weekday()]}, which conflicts with stated weekday '{m_weekday.group('stated_weekday')}'. Date specifies day and month without a year."
                                    ]
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass

            candidates.append({
                "start": start_idx,
                "end": m.end(),
                "priority": 7,
                "date_text": full_snippet,
                "due_date": None,
                "date_status": "needs_review",
                "date_reasons": reasons,
            })

    # Priority 7b: Numeric day and month without year (e.g. 25/11, 25-11, 25.11, 05/11)
    for m in PATTERN_NUMERIC_DAY_MONTH_NO_YEAR.finditer(text):
        raw_snippet = m.group(0).strip()
        v1 = int(m.group("p1"))
        v2 = int(m.group("p2"))
        # Validate plausible day/month components (1..31 and 1..12)
        if 1 <= v1 <= 31 and 1 <= v2 <= 31 and not (v1 > 12 and v2 > 12):
            if v1 <= 12 and v2 <= 12 and v1 != v2:
                reasons = [
                    f"Numeric date '{raw_snippet}' specifies day and month without a year, and is ambiguous between DD/MM and MM/DD format."
                ]
            else:
                reasons = [
                    f"Numeric date '{raw_snippet}' specifies day and month without a year. SMART does not assume a year."
                ]
            candidates.append({
                "start": m.start(),
                "end": m.end(),
                "priority": 7,
                "date_text": raw_snippet,
                "due_date": None,
                "date_status": "needs_review",
                "date_reasons": reasons,
            })

    # Priority 8: Relative weekdays (e.g. Friday, Monday, next Monday, this Friday, coming Wednesday)
    for m in PATTERN_RELATIVE_WEEKDAY.finditer(text):
        raw_snippet = m.group(0).strip()
        weekday_info = resolve_weekday(raw_snippet, message_date)
        if weekday_info:
            candidates.append({
                "start": m.start(),
                "end": m.end(),
                "priority": 8,
                "date_text": weekday_info["date_text"],
                "due_date": weekday_info["due_date"],
                "date_status": weekday_info["date_status"],
                "date_reasons": weekday_info["date_reasons"],
            })

    # Priority 9: Incomplete temporal expressions (asap, announced later, before lunch, next week)
    for m in PATTERN_INCOMPLETE_TEMPORAL.finditer(text):
        raw_snippet = m.group(0).strip()
        candidates.append({
            "start": m.start(),
            "end": m.end(),
            "priority": 9,
            "date_text": raw_snippet,
            "due_date": None,
            "date_status": "needs_review",
            "date_reasons": [
                f"Incomplete temporal expression '{raw_snippet}' detected without specific calendar date or deadline; requires human review."
            ],
        })

    # Priority 10: Ambiguous relative expressions (soon, within a few days)
    for m in PATTERN_AMBIGUOUS_RELATIVE.finditer(text):
        raw_snippet = m.group(0).strip()
        candidates.append({
            "start": m.start(),
            "end": m.end(),
            "priority": 10,
            "date_text": raw_snippet,
            "due_date": None,
            "date_status": "needs_review",
            "date_reasons": [
                f"Ambiguous relative temporal expression '{raw_snippet}' detected without an exact date anchor; requires human review."
            ],
        })

    # Filter overlaps: sort candidates by priority (lower number = higher priority), then length descending
    candidates.sort(key=lambda c: (c["priority"], -(c["end"] - c["start"])))

    accepted: list[dict[str, Any]] = []
    for cand in candidates:
        c_start, c_end = cand["start"], cand["end"]
        overlaps = False
        for acc in accepted:
            a_start, a_end = acc["start"], acc["end"]
            if not (c_end <= a_start or c_start >= a_end):
                overlaps = True
                break
            # Suppress weekday immediately preceding an explicit date (e.g. "Friday, 20 November")
            if cand["priority"] == 7 and 0 <= (a_start - c_end) <= 4:
                overlaps = True
                break
        if not overlaps:
            accepted.append(cand)

    accepted.sort(key=lambda c: c["start"])
    return accepted


def detect_date(text: str, timestamp_text: str | None) -> dict[str, Any]:
    """Detect and evaluate dates from message text and timestamp.

    Returns structured dictionary:
    - date_text: original date string or phrase found in text
    - due_date: ISO date string (YYYY-MM-DD) if confidently parsed, else None
    - date_status: 'parsed' | 'resolved_from_message_date' | 'needs_review' | 'not_found'
    - date_reasons: list of explanations for uncertainty or status
    - is_range: True if multi-day date range was detected
    """
    all_dates = detect_all_dates(text, timestamp_text)
    if not all_dates:
        return {
            "date_text": None,
            "due_date": None,
            "date_status": "not_found",
            "date_reasons": [],
            "is_range": False,
        }

    if len(all_dates) == 1:
        res = dict(all_dates[0])
        res.setdefault("is_range", False)
        return {
            "date_text": res["date_text"],
            "due_date": res["due_date"],
            "date_status": res["date_status"],
            "date_reasons": res["date_reasons"],
            "is_range": res["is_range"],
        }

    # Multiple dates: check if they resolve to the exact same date
    distinct_resolved = {d.get("due_date") for d in all_dates if d.get("due_date") is not None}
    distinct_raw = {d.get("date_text") for d in all_dates if d.get("date_text") is not None}
    if len(distinct_resolved) == 1 and len(distinct_raw) == 1:
        res = dict(all_dates[0])
        res.setdefault("is_range", False)
        return {
            "date_text": res["date_text"],
            "due_date": res["due_date"],
            "date_status": res["date_status"],
            "date_reasons": res["date_reasons"],
            "is_range": res["is_range"],
        }

    # Truly multiple dates in one text: ambiguous association
    date_snippets = [d["date_text"] for d in all_dates if d.get("date_text")]
    has_range = any(d.get("is_range") for d in all_dates)
    return {
        "date_text": ", ".join(date_snippets),
        "due_date": None,
        "date_status": "needs_review",
        "date_reasons": [
            f"Multiple candidate dates detected in task text ({', '.join(date_snippets)}); marked for human review."
        ],
        "is_range": has_range,
    }


def extract_update_transition_dates(text: str, timestamp_text: str | None) -> dict[str, Any] | None:
    """Extract previous and updated target dates from an update announcement.

    Supports:
    - 'Tomorrow's internal exam is rescheduled to Friday.' -> previous: tomorrow, new: Friday
    - 'The deadline was extended to 30 November, but the previous message says 28 November.' -> previous: 28 Nov, new: 30 Nov
    - 'Deadline extended from 20 November to 25 November.' -> previous: 20 Nov, new: 25 Nov
    - 'The project submission has been postponed to Monday.' -> previous: None, new: Monday
    """
    if not text:
        return None

    # 0. Pattern: previously due <old_phrase> ... rescheduled/extended/postponed to <new_phrase>
    m0 = re.search(
        r"\b(?:previously\s+due|previously\s+scheduled|earlier\s+due|originally\s+due)\s+(?:on\s+)?(?P<old_phrase>[^,.]+?)\s+(?:is|was|has\s+been)?\s*(?:rescheduled|postponed|extended|moved|deferred)\s+(?:to|until)\s+(?P<new_phrase>[a-z0-9/.-]+(?:\s+[a-z0-9]+)*)",
        text,
        re.I,
    )
    if m0:
        old_str = m0.group("old_phrase").strip()
        new_str = m0.group("new_phrase").strip()
        old_d = detect_date(old_str, timestamp_text)
        new_d = detect_date(new_str, timestamp_text)
        if old_d.get("date_status") != "not_found":
            return {
                "previous_date": old_d.get("due_date"),
                "previous_date_text": old_d.get("date_text") or old_str,
                "new_date": new_d.get("due_date"),
                "new_date_text": new_d.get("date_text") or new_str,
                "new_date_status": new_d.get("date_status", "needs_review"),
            }

    # 1. Pattern: <old_phrase> ... rescheduled/postponed/moved to <new_phrase>
    m1 = re.search(
        rf"\b(?P<old_phrase>tomorrow|yesterday|today|{MONTH_NAMES}\s+\d{{1,2}}(?:st|nd|rd|th)?|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{MONTH_NAMES}(?:\s+\d{{4}})?|\d{{1,2}}[./-]\d{{1,2}}(?:[./-]\d{{2,4}})?|this\s+[a-z]+|next\s+[a-z]+|[a-z]+day)(?:'s)?\s+(?:[a-z0-9_-]+\s+)*(?:is|was|has\s+been)\s+(?:rescheduled|postponed|moved|deferred)\s+(?:to|until)\s+(?P<new_phrase>[a-z0-9/.-]+(?:\s+[a-z0-9]+)*)",
        text,
        re.I,
    )
    if m1:
        old_str = m1.group("old_phrase").strip()
        new_str = m1.group("new_phrase").strip()
        old_d = detect_date(old_str, timestamp_text)
        new_d = detect_date(new_str, timestamp_text)
        if old_d.get("date_status") != "not_found":
            return {
                "previous_date": old_d.get("due_date"),
                "previous_date_text": old_d.get("date_text") or old_str,
                "new_date": new_d.get("due_date"),
                "new_date_text": new_d.get("date_text") or new_str,
                "new_date_status": new_d.get("date_status", "needs_review"),
            }

    # 2. Pattern: (extended|revised) to <new_phrase> ... (previous|earlier|was) <old_phrase>
    m2 = re.search(
        r"\b(?:extended|revised|postponed|rescheduled)\s+to\s+(?P<new_phrase>[^,.]+?)(?:,|\s+but|\s+and|\s+replacing|\s+from)\s+(?:.*?(?:previous|earlier|from|says?|was)\s+(?:message\s+says?\s+)?(?P<old_phrase>[a-z0-9/.-]+(?:\s+[a-z0-9]+)*))",
        text,
        re.I,
    )
    if m2:
        new_str = m2.group("new_phrase").strip()
        old_str = m2.group("old_phrase").strip()
        new_d = detect_date(new_str, timestamp_text)
        old_d = detect_date(old_str, timestamp_text)
        return {
            "previous_date": old_d.get("due_date"),
            "previous_date_text": old_d.get("date_text") or old_str,
            "new_date": new_d.get("due_date"),
            "new_date_text": new_d.get("date_text") or new_str,
            "new_date_status": new_d.get("date_status", "needs_review"),
        }

    # 3. Pattern: extended from <old_phrase> to <new_phrase>
    m3 = re.search(
        r"\b(?:extended|rescheduled|postponed|revised|moved|changed|window\s+changed|shifted)\s+from\s+(?P<old_phrase>[^,.]+?)\s+to\s+(?P<new_phrase>[a-z0-9/.-]+(?:\s+[a-z0-9]+)*)",
        text,
        re.I,
    )
    if m3:
        old_str = m3.group("old_phrase").strip()
        new_str = m3.group("new_phrase").strip()
        old_d = detect_date(old_str, timestamp_text)
        new_d = detect_date(new_str, timestamp_text)
        return {
            "previous_date": old_d.get("due_date"),
            "previous_date_text": old_d.get("date_text") or old_str,
            "new_date": new_d.get("due_date"),
            "new_date_text": new_d.get("date_text") or new_str,
            "new_date_status": new_d.get("date_status", "needs_review"),
        }

    # 4. Pattern: (extended|postponed|rescheduled|revised) to/until <new_phrase>
    m4 = re.search(
        r"\b(?:extended|postponed|rescheduled|revised|deferred|moved)\s+(?:to|until)\s+(?P<new_phrase>[a-z0-9/.-]+(?:\s+[a-z0-9]+)*)",
        text,
        re.I,
    )
    if m4:
        new_str = m4.group("new_phrase").strip()
        new_d = detect_date(new_str, timestamp_text)
        return {
            "previous_date": None,
            "previous_date_text": None,
            "new_date": new_d.get("due_date"),
            "new_date_text": new_d.get("date_text") or new_str,
            "new_date_status": new_d.get("date_status", "needs_review"),
        }

    return None
