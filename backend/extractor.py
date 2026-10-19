
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse


CATEGORY_KEYWORDS = {
    "Assignment": [
        "assignment", "homework", "submission", "submit",
        "coursework", "lab record",
    ],
    "Exam": [
        "exam", "examination", "internal test", "semester test",
        "assessment", "quiz", "model test",
    ],
    "Announcement": [
        "announcement", "circular", "important notice",
        "schedule change", "postponed", "rescheduled",
    ],
    "Opportunity": [
        "internship", "hackathon", "competition", "scholarship",
        "job opening", "registration open", "placement drive",
    ],
    "Event": [
        "workshop", "seminar", "conference", "webinar",
        "event", "guest lecture",
    ],
}

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

DATE_PATTERNS = [
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(
        r"\b(?:\d{1,2}\s+)?"
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
        r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|"
        r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b",
        re.IGNORECASE,
    ),
]

DEADLINE_KEYWORDS = [
    "due", "deadline", "submit by", "last date",
    "last day", "submission by", "before",
]

RELATIVE_DATES = {
    "today": 0,
    "tomorrow": 1,
    "day after tomorrow": 2,
}


def parse_message_date(timestamp_text):
    """Parse common WhatsApp dates in day/month/year format."""
    date_part = timestamp_text.split(",", 1)[0].strip()

    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_part, fmt).date()
        except ValueError:
            continue

    return None


def detect_date(text, timestamp_text):
    """Return a date only when it can be interpreted from the message."""
    message_date = parse_message_date(timestamp_text)
    lowered = text.lower()

    # Check longer phrases before shorter ones.
    for phrase in ("day after tomorrow", "tomorrow", "today"):
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            if message_date is None:
                return {
                    "date_text": phrase,
                    "due_date": None,
                    "date_status": "needs_review",
                }

            resolved = message_date + timedelta(
                days=RELATIVE_DATES[phrase]
            )
            return {
                "date_text": phrase,
                "due_date": resolved.isoformat(),
                "date_status": "resolved_from_message_date",
            }

    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        date_text = match.group(0).strip()
        cleaned = re.sub(
            r"(\d)(st|nd|rd|th)\b",
            r"\1",
            date_text,
            flags=re.IGNORECASE,
        )

        formats = [
            "%d/%m/%Y", "%d/%m/%y",
            "%d-%m-%Y", "%d-%m-%y",
            "%B %d %Y", "%B %d, %Y",
            "%b %d %Y", "%b %d, %Y",
            "%d %B %Y", "%d %b %Y",
        ]

        # Dates without a year need explicit review rather than
        # silently assuming the current year.
        if not re.search(r"\b\d{4}\b", cleaned):
            return {
                "date_text": date_text,
                "due_date": None,
                "date_status": "needs_review",
            }

        for fmt in formats:
            try:
                parsed = datetime.strptime(cleaned, fmt).date()
                return {
                    "date_text": date_text,
                    "due_date": parsed.isoformat(),
                    "date_status": "parsed",
                }
            except ValueError:
                continue

        return {
            "date_text": date_text,
            "due_date": None,
            "date_status": "needs_review",
        }

    return {
        "date_text": None,
        "due_date": None,
        "date_status": "not_found",
    }


def extract_urls(text):
    """Find HTTP(S) links and validate their basic structure."""
    urls = []

    for match in URL_PATTERN.findall(text):
        url = match.rstrip(".,!?;:)")
        parsed = urlparse(url)

        if parsed.scheme in ("http", "https") and parsed.netloc:
            urls.append(url)

    return list(dict.fromkeys(urls))


def classify_message(text):
    """Return the first matching academic category."""
    lowered = text.lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lowered:
                return category

    return None


def extract_academic_items(messages):
    """Extract candidate academic items while preserving evidence."""
    items = []

    for message in messages:
        text = message["text"]
        category = classify_message(text)

        if category is None:
            continue

        date_info = detect_date(text, message["timestamp_text"])
        urls = extract_urls(text)
        lowered = text.lower()

        has_deadline_language = any(
            keyword in lowered for keyword in DEADLINE_KEYWORDS
        )

        # A date may be an event date, not necessarily a deadline.
        # Preserve the wording and flag ambiguity for human review.
        review_required = (
            date_info["date_status"] == "needs_review"
            or (
                date_info["due_date"] is not None
                and not has_deadline_language
            )
        )

        items.append({
            "item_id": message["message_id"],
            "category": category,
            "title": text[:100].strip(),
            "date_text": date_info["date_text"],
            "due_date": date_info["due_date"],
            "date_status": date_info["date_status"],
            "urls": urls,
            "source_message_id": message["message_id"],
            "source_sender": message["sender"],
            "source_timestamp": message["timestamp_text"],
            "source_text": text,
            "extraction_method": "rules",
            "review_required": review_required,
        })

    return items
