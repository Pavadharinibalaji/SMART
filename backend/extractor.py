"""Rule-based Academic Information Extractor for SMART.

Extracts candidate academic items (assignments, exams, announcements, events,
and opportunities) from structured WhatsApp messages using deterministic rules,
word-boundary matching, conservative date resolution, and source evidence preservation.
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
        re.compile(r"\bproject\s+(?:submission|report|deadline)\b", re.I),
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
    re.compile(r"\bsubmit\s+by\b", re.I),
    re.compile(r"\bsubmission\s+(?:by|deadline|date|before)\b", re.I),
    re.compile(r"\blast\s+date\b", re.I),
    re.compile(r"\blast\s+day\b", re.I),
    re.compile(r"\bby\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", re.I),
    re.compile(r"\bby\s+(?:midnight|end\s+of\s+day|eod|11:59)\b", re.I),
    re.compile(r"\bbefore\s+(?:midnight|\d{1,2}[/-]\d{1,2})\b", re.I),
]

RELATIVE_DAYS = {
    "day after tomorrow": 2,
    "tomorrow": 1,
    "today": 0,
    "tonight": 0,
}

MONTH_NAMES = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)

# Explicit date regexes
# 1. Day Month Year (e.g. 24th October 2026, 24 Oct 2026)
PATTERN_DAY_MONTH_YEAR = re.compile(
    rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<month>{MONTH_NAMES})(?:,?\s+(?P<year>\d{{4}}))\b",
    re.IGNORECASE,
)

# 2. Month Day Year (e.g. October 24th, 2026 or Oct 24 2026)
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
        # Safely strip trailing punctuation while respecting balanced parentheses.
        while cleaned and cleaned[-1] in TRAILING_PUNCTUATION:
            if cleaned[-1] == ")" and cleaned.count("(") >= cleaned.count(")"):
                break
            cleaned = cleaned[:-1]

        if not cleaned:
            continue

        parsed = urlparse(cleaned)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            urls.append(cleaned)

    # Deduplicate while preserving order of occurrence
    return list(dict.fromkeys(urls))


def _clean_ordinal(text: str) -> str:
    """Strip st/nd/rd/th suffix from numeric day."""
    return re.sub(r"(\d+)(?:st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)


def detect_date(text: str, timestamp_text: str) -> dict[str, Any]:
    """Detect and evaluate dates from message text and timestamp.

    Returns:
    - date_text: original date string or phrase found in text
    - due_date: ISO date string (YYYY-MM-DD) if confidently parsed, else None
    - date_status: 'parsed' | 'resolved_from_message_date' | 'needs_review' | 'not_found'
    - date_reasons: list of explanations for uncertainty or status
    """
    reasons: list[str] = []
    lowered = text.lower()
    message_date = parse_message_date(timestamp_text)

    # 1. Check relative date expressions (longest to shortest)
    for phrase in ("day after tomorrow", "tomorrow", "today", "tonight"):
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            if message_date is not None:
                offset = RELATIVE_DAYS[phrase]
                resolved = message_date + timedelta(days=offset)
                return {
                    "date_text": phrase,
                    "due_date": resolved.isoformat(),
                    "date_status": "resolved_from_message_date",
                    "date_reasons": [
                        f"Resolved relative expression '{phrase}' (+{offset}d) using message timestamp date {message_date.isoformat()}."
                    ],
                }
            return {
                "date_text": phrase,
                "due_date": None,
                "date_status": "needs_review",
                "date_reasons": [
                    f"Relative date '{phrase}' detected, but message timestamp date could not be parsed confidently."
                ],
            }

    # 2. Check Day Month Year (e.g. 24 October 2026)
    m = PATTERN_DAY_MONTH_YEAR.search(text)
    if m:
        raw_snippet = m.group(0).strip()
        cleaned = _clean_ordinal(raw_snippet)
        for fmt in ("%d %B %Y", "%d %b %Y", "%d of %B %Y", "%d of %b %Y"):
            try:
                dt = datetime.strptime(cleaned, fmt).date()
                return {
                    "date_text": raw_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["Explicit date with year detected and validated."],
                }
            except ValueError:
                continue

    # 3. Check Month Day Year (e.g. October 24, 2026)
    m = PATTERN_MONTH_DAY_YEAR.search(text)
    if m:
        raw_snippet = m.group(0).strip()
        cleaned = _clean_ordinal(raw_snippet).replace(",", "")
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                dt = datetime.strptime(cleaned, fmt).date()
                return {
                    "date_text": raw_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["Explicit date with year detected and validated."],
                }
            except ValueError:
                continue

    # 4. Check Month + Day WITHOUT Year (Requirement: do not invent a year!)
    m_no_year = PATTERN_DAY_MONTH_NO_YEAR.search(text) or PATTERN_MONTH_DAY_NO_YEAR.search(text)
    if m_no_year:
        raw_snippet = m_no_year.group(0).strip()
        return {
            "date_text": raw_snippet,
            "due_date": None,
            "date_status": "needs_review",
            "date_reasons": [
                f"Date '{raw_snippet}' specifies day and month without a year. SMART does not assume a year."
            ],
        }

    # 5. Check numeric dates (e.g. 24/10/2026, 05/06/2026, 2026-10-24)
    num_match = PATTERN_NUMERIC_FULL.search(text)
    if num_match:
        p1 = num_match.group("p1")
        p2 = num_match.group("p2")
        p3 = num_match.group("p3")
        raw_snippet = num_match.group(0).strip()

        # Case A: ISO YYYY-MM-DD
        if len(p1) == 4:
            try:
                dt = datetime.strptime(raw_snippet, "%Y-%m-%d").date()
                return {
                    "date_text": raw_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["ISO date detected and validated."],
                }
            except ValueError:
                pass

        # Case B: DD/MM/YYYY or MM/DD/YYYY
        v1 = int(p1)
        v2 = int(p2)

        # Check for ambiguous date where both v1 and v2 <= 12 and distinct (e.g. 05/06/2026)
        if v1 <= 12 and v2 <= 12 and v1 != v2:
            return {
                "date_text": raw_snippet,
                "due_date": None,
                "date_status": "needs_review",
                "date_reasons": [
                    f"Numeric date '{raw_snippet}' is ambiguous between DD/MM and MM/DD format."
                ],
            }

        # If v1 > 12, unambiguous DD/MM
        if v1 > 12 and v2 <= 12:
            year_len = len(p3)
            sep = "/" if "/" in raw_snippet else ("-" if "-" in raw_snippet else ".")
            fmt = f"%d{sep}%m{sep}%Y" if year_len == 4 else f"%d{sep}%m{sep}%y"
            try:
                dt = datetime.strptime(raw_snippet, fmt).date()
                return {
                    "date_text": raw_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["Unambiguous day-first numeric date parsed."],
                }
            except ValueError:
                pass

        # If v2 > 12, unambiguous MM/DD
        if v1 <= 12 and v2 > 12:
            year_len = len(p3)
            sep = "/" if "/" in raw_snippet else ("-" if "-" in raw_snippet else ".")
            fmt = f"%m{sep}%d{sep}%Y" if year_len == 4 else f"%m{sep}%d{sep}%y"
            try:
                dt = datetime.strptime(raw_snippet, fmt).date()
                return {
                    "date_text": raw_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["Unambiguous month-first numeric date parsed."],
                }
            except ValueError:
                pass

        # If v1 == v2 (e.g. 05/05/2026)
        if v1 == v2 and v1 <= 12:
            year_len = len(p3)
            sep = "/" if "/" in raw_snippet else ("-" if "-" in raw_snippet else ".")
            fmt = f"%d{sep}%m{sep}%Y" if year_len == 4 else f"%d{sep}%m{sep}%y"
            try:
                dt = datetime.strptime(raw_snippet, fmt).date()
                return {
                    "date_text": raw_snippet,
                    "due_date": dt.isoformat(),
                    "date_status": "parsed",
                    "date_reasons": ["Identical day and month numeric date parsed."],
                }
            except ValueError:
                pass

        # Fallback for other numeric matches
        return {
            "date_text": raw_snippet,
            "due_date": None,
            "date_status": "needs_review",
            "date_reasons": [f"Numeric date '{raw_snippet}' could not be parsed confidently."],
        }

    return {
        "date_text": None,
        "due_date": None,
        "date_status": "not_found",
        "date_reasons": [],
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


def extract_academic_items(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract candidate academic items while preserving evidence and flagging uncertainty.

    Requirements enforced:
    - Word boundary keyword matching prevents false positives (e.g. 'prevent', 'eventually').
    - System messages without academic intent are ignored.
    - Dates without explicit year are never given an invented year.
    - Ambiguous numeric dates and relative dates without timestamps are flagged for human review.
    - Distinguishes confirmed deadline language from general mentioned dates.
    - Deduplicates repeated URLs within each message.
    - Preserves original message text, sender, and timestamp as source evidence.
    """
    items: list[dict[str, Any]] = []

    for message in messages:
        sender = message.get("sender", "System")
        text = message.get("text", "")

        # System notifications (encryption, user added, etc.) are not academic items.
        if sender == "System":
            continue

        category, all_matched_cats = classify_message(text)
        if category is None:
            continue

        # Weak match check: if only generic 'event' matched without specific context or dates
        is_isolated_event_keyword = False
        if category == "Event":
            lowered = text.lower()
            # If the only match was 'event/events' and no workshop/seminar/conference/etc.
            has_specific_event_word = any(
                w in lowered
                for w in (
                    "workshop", "seminar", "conference", "webinar",
                    "guest lecture", "symposium", "meetup", "hackathon"
                )
            )
            if not has_specific_event_word and re.search(r"\bevents?\b", lowered):
                is_isolated_event_keyword = True

        date_info = detect_date(text, message.get("timestamp_text", ""))
        urls = extract_urls(text)

        # Check for deadline language
        has_deadline_language = any(pat.search(text) for pat in DEADLINE_INDICATORS)
        if has_deadline_language:
            date_type = "deadline"
        elif date_info["due_date"] is not None or date_info["date_text"] is not None:
            date_type = "event_date" if category in ("Event", "Exam", "Opportunity") else "mentioned_date"
        else:
            date_type = "none"

        review_reasons: list[str] = list(date_info.get("date_reasons", []))

        # Flag for human review when:
        # 1. Date resolution requires review (missing year, relative date without timestamp, ambiguous).
        # 2. Date was found but lacked explicit deadline wording for an Assignment.
        # 3. Multiple conflicting academic categories matched.
        # 4. Isolated generic 'event' word used.
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

        # Construct candidate item title (first non-empty line or first 100 characters)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = lines[0][:120].strip() if lines else text[:120].strip()

        items.append({
            "item_id": message.get("message_id", len(items) + 1),
            "category": category,
            "title": title or "Untitled candidate message",
            "date_text": date_info["date_text"],
            "due_date": date_info["due_date"],
            "date_status": date_info["date_status"],
            "date_type": date_type,
            "urls": urls,
            "source_message_id": message.get("message_id"),
            "source_sender": sender,
            "source_timestamp": message.get("timestamp_text", ""),
            "source_text": text,
            "extraction_method": "rules",
            "review_required": review_required,
            "review_reasons": review_reasons,
        })

    return items
