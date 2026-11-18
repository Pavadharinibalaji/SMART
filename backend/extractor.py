"""Rule-based Academic Information Extractor for SMART.

Extracts candidate academic items (assignments, exams, announcements, events,
and opportunities) from structured WhatsApp messages using deterministic rules,
word-boundary matching, multi-item extraction, conservative date/time resolution,
and source evidence preservation.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

# Categories and their word-boundary patterns to prevent substring false positives
# (e.g. 'eventually' matching 'event', 'example' matching 'exam', 'quizzical' matching 'quiz').
CATEGORY_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "Assignment": [
        re.compile(r"\bassignments?\b", re.I),
        re.compile(r"\bhomeworks?\b", re.I),
        re.compile(r"\bsubmissions?\b", re.I),
        re.compile(r"\bsubmit(?:s|ted|ting)?\b", re.I),
        re.compile(r"\bcoursework\b", re.I),
        re.compile(r"\blab\s+(?:record|manual|submission|report|exercise)s?\b", re.I),
        re.compile(r"\bproject\s+(?:submission|report|deadline|demo|presentation|evaluation)s?\b", re.I),
    ],
    "Exam": [
        re.compile(r"\bexams?\b", re.I),
        re.compile(r"\bexaminations?\b", re.I),
        re.compile(r"\binternal\s+(?:assessment|test|exam)s?\b", re.I),
        re.compile(r"\bsemester\s+(?:test|exam)s?\b", re.I),
        re.compile(r"\bmidterm\b", re.I),
        re.compile(r"\bquiz(?:zes)?\b", re.I),
        re.compile(r"\bmodel\s+(?:test|exam)s?\b", re.I),
        re.compile(r"\bviva\s+voce\b", re.I),
        re.compile(r"\bviva\b", re.I),
        re.compile(r"\bassessment\b", re.I),
    ],
    "Announcement": [
        re.compile(r"\bannouncements?\b", re.I),
        re.compile(r"\bcirculars?\b", re.I),
        re.compile(r"\bimportant\s+notices?\b", re.I),
        re.compile(r"\bnotice\s*:", re.I),
        re.compile(r"\bofficial\s+notice\b", re.I),
        re.compile(r"\bschedule\s+change\b", re.I),
        re.compile(r"\bpostponed\b", re.I),
        re.compile(r"\brescheduled\b", re.I),
        re.compile(r"\bclasses?\s+(?:cancelled|suspended)\b", re.I),
        re.compile(r"\bholiday\s+declared\b", re.I),
    ],
    "Opportunity": [
        re.compile(r"\binternships?\b", re.I),
        re.compile(r"\bhackathons?\b", re.I),
        re.compile(r"\bcompetitions?\b", re.I),
        re.compile(r"\bscholarships?\b", re.I),
        re.compile(r"\bjob\s+(?:openings?|vacanc(?:y|ies)|postings?)\b", re.I),
        re.compile(r"\bregistration\s+(?:is\s+)?open\b", re.I),
        re.compile(r"\bplacement\s+drive\b", re.I),
        re.compile(r"\bfellowships?\b", re.I),
        re.compile(r"\bhiring\b", re.I),
    ],
    "Event": [
        re.compile(r"\bworkshops?\b", re.I),
        re.compile(r"\bseminars?\b", re.I),
        re.compile(r"\bconferences?\b", re.I),
        re.compile(r"\bwebinars?\b", re.I),
        re.compile(r"\bguest\s+lectures?\b", re.I),
        re.compile(r"\bsymposiums?\b", re.I),
        re.compile(r"\bevents?\b", re.I),
    ],
}

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,!?;:)]}>\"'"

DEADLINE_INDICATORS = [
    re.compile(r"\bdue\b", re.I),
    re.compile(r"\bdeadlines?\b", re.I),
    re.compile(r"\bsubmit\s+(?:by|before|on)\b", re.I),
    re.compile(r"\bsubmissions?\s+(?:is|by|deadline|date|before|due)\b", re.I),
    re.compile(r"\blast\s+date\b", re.I),
    re.compile(r"\blast\s+day\b", re.I),
    re.compile(r"\bby\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", re.I),
    re.compile(r"\bby\s+(?:midnight|end\s+of\s+day|eod|11:59)\b", re.I),
    re.compile(r"\bbefore\s+(?:midnight|\d{1,2}[/-]\d{1,2})\b", re.I),
    re.compile(r"\b(?:registration\s+)?closes?\s+(?:on|by|at|before)\b", re.I),
    re.compile(r"\b(?:register|apply)\b.*?\b(?:by|before)\b", re.I),
    re.compile(r"\bregistration\s+(?:deadline|closes?|date)\b", re.I),
]

RELATIVE_DAYS = {
    "day after tomorrow": 2,
    "tomorrow": 1,
    "today": 0,
    "tonight": 0,
}

WEEKDAY_MAP: dict[str, int] = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

PATTERN_RELATIVE_WEEKDAY = re.compile(
    r"\b(?:(?P<modifier>this|coming|next)\s+)?(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b",
    re.IGNORECASE,
)

TIME_12H_WITH_MINUTES = re.compile(
    r"\b(?P<hour>1[0-2]|0?[1-9]):(?P<minute>[0-5]\d)\s*(?P<ampm>[AaPp]\.?[Mm]\.?)\b"
)
TIME_12H_NO_MINUTES = re.compile(
    r"\b(?P<hour>1[0-2]|0?[1-9])\s*(?P<ampm>[AaPp]\.?[Mm]\.?)\b"
)
TIME_24H = re.compile(
    r"\b(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)\b(?!\s*[:/.-]\d)"
)

MONTH_NAMES = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
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

# 3. Day Month WITHOUT Year (e.g. 24th October, October 24) -> Must NOT invent year
PATTERN_DAY_MONTH_NO_YEAR = re.compile(
    rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<month>{MONTH_NAMES})\b(?!,?\s+\d{{4}})",
    re.IGNORECASE,
)
PATTERN_MONTH_DAY_NO_YEAR = re.compile(
    rf"\b(?P<month>{MONTH_NAMES})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\b(?!,?\s+\d{{4}})",
    re.IGNORECASE,
)

# 4. Numeric dates (DD/MM/YYYY or DD-MM-YYYY or YYYY-MM-DD or DD.MM.YYYY)
PATTERN_NUMERIC_FULL = re.compile(
    r"\b(?P<p1>\d{1,4})[./-](?P<p2>\d{1,2})[./-](?P<p3>\d{2,4})\b"
)


def parse_message_date(timestamp_text: str) -> date | None:
    """Parse WhatsApp message timestamp date conservatively."""
    if not timestamp_text:
        return None

    date_part = timestamp_text.split(",", 1)[0].strip()

    # Try common WhatsApp export date formats
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


def extract_urls(text: str) -> list[str]:
    """Find HTTP(S) links, normalize trailing punctuation, and deduplicate."""
    if not text:
        return []

    urls: list[str] = []
    for raw_match in URL_PATTERN.findall(text):
        cleaned = raw_match
        while cleaned and cleaned[-1] in TRAILING_PUNCTUATION:
            if cleaned[-1] == ")" and cleaned.count("(") >= cleaned.count(")"):
                break
            cleaned = cleaned[:-1]

        if not cleaned:
            continue

        parsed = urlparse(cleaned)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            urls.append(cleaned)

    return list(dict.fromkeys(urls))


def _clean_ordinal(text: str) -> str:
    """Strip st/nd/rd/th suffix from numeric day."""
    return re.sub(r"(\d+)(?:st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)


def resolve_weekday(text: str, message_date: date | None) -> dict[str, Any] | None:
    """Resolve a relative weekday expression using message timestamp date as anchor."""
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
                f"Relative weekday '{raw_snippet}' detected, but message timestamp date could not be parsed confidently."
            ],
        }

    msg_w = message_date.weekday()
    days_ahead = (target_w - msg_w) % 7
    if days_ahead == 0:
        days_ahead = 7

    is_next = modifier == "next"
    if is_next and (msg_w + days_ahead <= 6):
        days_ahead += 7

    resolved = message_date + timedelta(days=days_ahead)
    return {
        "date_text": raw_snippet,
        "due_date": resolved.isoformat(),
        "date_status": "resolved_from_message_date",
        "date_reasons": [
            f"Resolved relative weekday '{raw_snippet}' (+{days_ahead}d) using message timestamp date {message_date.isoformat()}."
        ],
    }


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


def detect_all_dates(text: str, timestamp_text: str) -> list[dict[str, Any]]:
    """Detect all date expressions in text, resolving dates and preserving spans."""
    if not text:
        return []

    message_date = parse_message_date(timestamp_text)
    candidates: list[dict[str, Any]] = []

    # Priority 1: Day Month Year (e.g. 24 October 2026, 20 November 2026)
    for m in PATTERN_DAY_MONTH_YEAR.finditer(text):
        raw_snippet = m.group(0).strip()
        cleaned = _clean_ordinal(raw_snippet)
        for fmt in ("%d %B %Y", "%d %b %Y", "%d of %B %Y", "%d of %b %Y"):
            try:
                dt = datetime.strptime(cleaned, fmt).date()
                candidates.append({
                    "start": m.start(),
                    "end": m.end(),
                    "priority": 1,
                    "date_text": raw_snippet,
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
        cleaned = _clean_ordinal(raw_snippet).replace(",", "")
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                dt = datetime.strptime(cleaned, fmt).date()
                candidates.append({
                    "start": m.start(),
                    "end": m.end(),
                    "priority": 2,
                    "date_text": raw_snippet,
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

    # Priority 4: Relative day expressions ("day after tomorrow", "tomorrow", "today", "tonight")
    lowered = text.lower()
    for phrase in ("day after tomorrow", "tomorrow", "today", "tonight"):
        for m in re.finditer(rf"\b{re.escape(phrase)}\b", lowered):
            if message_date is not None:
                offset = RELATIVE_DAYS[phrase]
                resolved = message_date + timedelta(days=offset)
                candidates.append({
                    "start": m.start(),
                    "end": m.end(),
                    "priority": 4,
                    "date_text": phrase,
                    "due_date": resolved.isoformat(),
                    "date_status": "resolved_from_message_date",
                    "date_reasons": [
                        f"Resolved relative expression '{phrase}' (+{offset}d) using message timestamp date {message_date.isoformat()}."
                    ],
                })
            else:
                candidates.append({
                    "start": m.start(),
                    "end": m.end(),
                    "priority": 4,
                    "date_text": phrase,
                    "due_date": None,
                    "date_status": "needs_review",
                    "date_reasons": [
                        f"Relative date '{phrase}' detected, but message timestamp date could not be parsed confidently."
                    ],
                })

    # Priority 5: Month + Day WITHOUT Year (Requirement: do not invent a year!)
    for pat in (PATTERN_DAY_MONTH_NO_YEAR, PATTERN_MONTH_DAY_NO_YEAR):
        for m in pat.finditer(text):
            raw_snippet = m.group(0).strip()
            candidates.append({
                "start": m.start(),
                "end": m.end(),
                "priority": 5,
                "date_text": raw_snippet,
                "due_date": None,
                "date_status": "needs_review",
                "date_reasons": [
                    f"Date '{raw_snippet}' specifies day and month without a year. SMART does not assume a year."
                ],
            })

    # Priority 6: Relative weekdays (e.g. Friday, Monday, next Monday, next Friday)
    for m in PATTERN_RELATIVE_WEEKDAY.finditer(text):
        raw_snippet = m.group(0).strip()
        weekday_info = resolve_weekday(raw_snippet, message_date)
        if weekday_info:
            candidates.append({
                "start": m.start(),
                "end": m.end(),
                "priority": 6,
                "date_text": weekday_info["date_text"],
                "due_date": weekday_info["due_date"],
                "date_status": weekday_info["date_status"],
                "date_reasons": weekday_info["date_reasons"],
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
            if cand["priority"] == 6 and 0 <= (a_start - c_end) <= 4:
                overlaps = True
                break
        if not overlaps:
            accepted.append(cand)

    accepted.sort(key=lambda c: c["start"])
    return accepted


def detect_date(text: str, timestamp_text: str) -> dict[str, Any]:
    """Detect and evaluate dates from message text and timestamp.

    Returns:
    - date_text: original date string or phrase found in text
    - due_date: ISO date string (YYYY-MM-DD) if confidently parsed, else None
    - date_status: 'parsed' | 'resolved_from_message_date' | 'needs_review' | 'not_found'
    - date_reasons: list of explanations for uncertainty or status
    """
    all_dates = detect_all_dates(text, timestamp_text)
    if not all_dates:
        return {
            "date_text": None,
            "due_date": None,
            "date_status": "not_found",
            "date_reasons": [],
        }

    if len(all_dates) == 1:
        return {
            "date_text": all_dates[0]["date_text"],
            "due_date": all_dates[0]["due_date"],
            "date_status": all_dates[0]["date_status"],
            "date_reasons": all_dates[0]["date_reasons"],
        }

    # Multiple dates: check if they resolve to the exact same date
    distinct_resolved = {d.get("due_date") for d in all_dates if d.get("due_date") is not None}
    distinct_raw = {d.get("date_text") for d in all_dates if d.get("date_text") is not None}
    if len(distinct_resolved) == 1 and len(distinct_raw) == 1:
        return {
            "date_text": all_dates[0]["date_text"],
            "due_date": all_dates[0]["due_date"],
            "date_status": all_dates[0]["date_status"],
            "date_reasons": all_dates[0]["date_reasons"],
        }

    # Truly multiple dates in one text: ambiguous association
    date_snippets = [d["date_text"] for d in all_dates if d.get("date_text")]
    return {
        "date_text": ", ".join(date_snippets),
        "due_date": None,
        "date_status": "needs_review",
        "date_reasons": [
            f"Multiple candidate dates detected in task text ({', '.join(date_snippets)}); marked for human review."
        ],
    }


def classify_message(text: str) -> tuple[str | None, list[str]]:
    """Classify message into an academic category using word-boundary matching.

    Returns:
    - category: matched category name or None
    - matched_categories: list of all categories that had at least one match
    """
    matches: list[str] = []

    for category, patterns in CATEGORY_PATTERNS.items():
        for pat in patterns:
            if pat.search(text):
                matches.append(category)
                break

    if not matches:
        return None, []

    # Priority ordering when multiple match
    priority_order = ["Assignment", "Exam", "Opportunity", "Event", "Announcement"]
    for cat in priority_order:
        if cat in matches:
            return cat, matches

    return matches[0], matches


def split_message_into_segments(text: str) -> list[str]:
    """Split message text into candidate clauses / sentences while preserving abbreviations."""
    if not text:
        return []

    protected = text
    abbreviations = [
        "Dr.", "Prof.", "Mr.", "Mrs.", "Ms.", "vs.", "e.g.", "i.e.", "etc.", "approx.", "dept.",
    ]
    abbr_map: dict[str, str] = {}
    for i, abbr in enumerate(abbreviations):
        placeholder = f"__ABBR_{i}__"
        abbr_map[placeholder] = abbr
        protected = re.sub(re.escape(abbr), placeholder, protected, flags=re.IGNORECASE)

    split_regex = re.compile(
        r"(?:\.\s+(?=[A-Z0-9])|[!?]\s+|;\s*|\n+|\s+(?:and|but)\s+(?=(?:the\s+)?(?:assignment|exam|internal|workshop|seminar|conference|hackathon|internship|submission|quiz|registration)\b))",
        re.IGNORECASE,
    )

    raw_segments = split_regex.split(protected)
    segments: list[str] = []
    for seg in raw_segments:
        clean = seg.strip()
        if not clean:
            continue
        for placeholder, original in abbr_map.items():
            clean = clean.replace(placeholder, original)
        segments.append(clean)

    return segments or [text]


def extract_academic_items(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract candidate academic items while preserving evidence and flagging uncertainty.

    Requirements enforced:
    - Multi-item extraction: independent tasks in a single message are extracted as separate items.
    - Preserves single multiline tasks without duplicate candidate generation.
    - Accurate date association: dates and times are associated with their specific tasks.
    - Ambiguous multi-date statements within a task are flagged for human review.
    - Time extraction: extracts 12h and 24h deadline/event times into structured fields.
    - Relative weekday resolution using message timestamp.
    - Distinguishes confirmed deadline language from event/mentioned dates.
    - Preserves original message text, sender, and timestamp as source evidence.
    """
    items: list[dict[str, Any]] = []

    for message in messages:
        sender = message.get("sender", "System")
        text = message.get("text", "")

        # System notifications (encryption, user added, etc.) are not academic items.
        if sender == "System":
            continue

        # Check if message has any academic category
        msg_category, _ = classify_message(text)
        if msg_category is None:
            continue

        timestamp_text = message.get("timestamp_text", "")

        # Segment message into sentences / clauses
        segments = split_message_into_segments(text)

        # Cluster segments into academic tasks
        task_clusters: list[list[str]] = []
        current_cluster: list[str] = []
        current_cat: str | None = None
        current_date_info: dict[str, Any] | None = None
        current_date_type: str = "none"

        for seg in segments:
            cat, _ = classify_message(seg)
            date_info = detect_date(seg, timestamp_text)
            has_deadline_lang = any(pat.search(seg) for pat in DEADLINE_INDICATORS)
            if has_deadline_lang:
                d_type = "deadline"
            elif date_info["due_date"] is not None or date_info["date_text"] is not None:
                d_type = "event_date" if cat in ("Event", "Exam", "Opportunity") else "mentioned_date"
            else:
                d_type = "none"

            if not current_cluster:
                current_cluster = [seg]
                current_cat = cat
                current_date_info = date_info
                current_date_type = d_type
            else:
                is_new_task = False
                if cat is not None:
                    if current_cat is None:
                        current_cat = cat
                    elif cat != current_cat:
                        is_new_task = True
                    else:
                        prev_has_date = (
                            current_date_info is not None
                            and (current_date_info.get("due_date") is not None or current_date_info.get("date_text") is not None)
                        )
                        seg_has_date = (
                            date_info.get("due_date") is not None
                            or date_info.get("date_text") is not None
                        )
                        if prev_has_date and seg_has_date:
                            if current_date_type != d_type:
                                is_new_task = True
                            elif (
                                current_date_info.get("due_date") != date_info.get("due_date")
                                or current_date_info.get("date_text") != date_info.get("date_text")
                            ):
                                is_new_task = True

                if is_new_task:
                    task_clusters.append(current_cluster)
                    current_cluster = [seg]
                    current_cat = cat
                    current_date_info = date_info
                    current_date_type = d_type
                else:
                    current_cluster.append(seg)
                    if current_cat is None and cat is not None:
                        current_cat = cat
                    if current_date_info is None or current_date_info.get("due_date") is None:
                        if date_info.get("due_date") is not None or date_info.get("date_text") is not None:
                            current_date_info = date_info
                            current_date_type = d_type

        if current_cluster:
            task_clusters.append(current_cluster)

        # Build academic item for each cluster
        for cluster in task_clusters:
            cluster_text = " ".join(cluster).strip()
            category, all_matched_cats = classify_message(cluster_text)
            if category is None:
                category = msg_category
                all_matched_cats = [category]

            date_info = detect_date(cluster_text, timestamp_text)
            time_info = extract_time(cluster_text)
            urls = extract_urls(cluster_text)

            has_deadline_language = any(pat.search(cluster_text) for pat in DEADLINE_INDICATORS)
            if has_deadline_language:
                date_type = "deadline"
            elif date_info["due_date"] is not None or date_info["date_text"] is not None:
                date_type = "event_date" if category in ("Event", "Exam", "Opportunity") else "mentioned_date"
            else:
                date_type = "none"

            # Check weak event match
            is_isolated_event_keyword = False
            if category == "Event":
                lowered_cluster = cluster_text.lower()
                has_specific_event_word = any(
                    w in lowered_cluster
                    for w in (
                        "workshop", "seminar", "conference", "webinar",
                        "guest lecture", "symposium", "meetup", "hackathon"
                    )
                )
                if not has_specific_event_word and re.search(r"\bevents?\b", lowered_cluster):
                    is_isolated_event_keyword = True

            review_reasons: list[str] = list(date_info.get("date_reasons", []))
            review_required = False

            if date_info["date_status"] == "needs_review":
                review_required = True

            if category == "Assignment" and date_type == "mentioned_date":
                review_required = True
                review_reasons.append("Date mentioned without explicit deadline phrasing (e.g. 'due', 'submit by').")

            if len(all_matched_cats) > 1:
                review_required = True
                review_reasons.append(
                    f"Multiple categories matched ({', '.join(all_matched_cats)}); classified as '{category}'."
                )

            if is_isolated_event_keyword and date_info["date_status"] == "not_found":
                review_required = True
                review_reasons.append("Message matched generic word 'event' without specific event terminology or dates.")

            # Construct title
            lines = [l.strip() for l in cluster if l.strip()]
            title = lines[0][:120].strip() if lines else cluster_text[:120].strip()

            items.append({
                "item_id": message.get("message_id", len(items) + 1),
                "category": category,
                "title": title or "Untitled candidate message",
                "date_text": date_info["date_text"],
                "due_date": date_info["due_date"],
                "date_status": date_info["date_status"],
                "date_type": date_type,
                "time_text": time_info["time_text"],
                "deadline_time": time_info["deadline_time"],
                "urls": urls,
                "source_message_id": message.get("message_id"),
                "source_sender": sender,
                "source_timestamp": timestamp_text,
                "source_text": text,
                "extraction_method": "rules",
                "review_required": review_required,
                "review_reasons": review_reasons,
            })

    return items
