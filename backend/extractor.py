"""Rule-based Academic Information Extractor for SMART.

Extracts candidate academic items (assignments, exams, announcements, events,
and opportunities) from structured WhatsApp messages using deterministic rules,
word-boundary matching, multi-item extraction, conservative date/time resolution,
and source evidence preservation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from prioritization import (
    assess_academic_importance,
    assess_task_urgency,
    calculate_priority,
    classify_academic_intent,
)

# Provenance signing secret (configurable via env; random secure key generated on startup if omitted)
_RUNTIME_PROVENANCE_SECRET: bytes | None = None


def get_provenance_secret() -> bytes:
    """Return the active HMAC secret for candidate provenance tokens.

    1. Checks the SMART_PROVENANCE_SECRET environment variable. If set and non-empty,
       uses its UTF-8 encoded bytes.
    2. If SMART_PROVENANCE_SECRET is missing or empty, generates a cryptographically
       secure 32-byte random key for the current process runtime (secrets.token_bytes(32))
       instead of falling back to any predictable hardcoded key.
    """
    global _RUNTIME_PROVENANCE_SECRET
    env_secret = os.environ.get("SMART_PROVENANCE_SECRET", "").strip()
    if env_secret:
        return env_secret.encode("utf-8")
    if _RUNTIME_PROVENANCE_SECRET is None:
        _RUNTIME_PROVENANCE_SECRET = secrets.token_bytes(32)
    return _RUNTIME_PROVENANCE_SECRET


def create_candidate_token(candidate: dict[str, Any]) -> str:
    """Create a tamper-evident HMAC-SHA256 token certifying candidate extraction provenance.

    Binds the authoritative source_text, category, evidence_text, evidence_start_index,
    evidence_end_index, confidence, confidence_reasons, is_actionable, actionability_type,
    update_type, due_date, date_status, date_text, date_type, and is_range.
    """
    provenance_data = {
        "source_text": candidate.get("source_text", ""),
        "category": candidate.get("category", ""),
        "evidence_text": candidate.get("evidence_text"),
        "evidence_start_index": candidate.get("evidence_start_index"),
        "evidence_end_index": candidate.get("evidence_end_index"),
        "confidence": candidate.get("confidence", "UNASSESSED"),
        "confidence_reasons": candidate.get("confidence_reasons") or [],
        "is_actionable": bool(candidate.get("is_actionable", True)),
        "actionability_type": str(candidate.get("actionability_type", "action_required")),
        "update_type": candidate.get("update_type"),
        "due_date": candidate.get("due_date"),
        "date_status": candidate.get("date_status"),
        "date_text": candidate.get("date_text"),
        "date_type": candidate.get("date_type"),
        "is_range": bool(candidate.get("is_range", False)),
        "previous_due_date": candidate.get("previous_due_date"),
        "time_text": candidate.get("time_text"),
        "deadline_time": candidate.get("deadline_time"),
        "importance": candidate.get("importance", "UNASSESSED"),
        "academic_intent": candidate.get("academic_intent"),
        "source_type": candidate.get("source_type", "whatsapp"),
        "source_id": candidate.get("source_id"),
        "source_metadata": candidate.get("source_metadata") or {},
    }
    raw_json = json.dumps(provenance_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(raw_json).decode("ascii")
    secret = get_provenance_secret()
    sig = hmac.new(secret, raw_json, hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_candidate_token(token: str) -> dict[str, Any] | None:
    """Verify candidate token authenticity and signature.

    Returns the decoded provenance dictionary if valid, or None if invalid or tampered.
    """
    if not token or not isinstance(token, str) or "." not in token:
        return None
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    payload_b64, sig = parts
    try:
        raw_json = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
    except Exception:
        return None
    secret = get_provenance_secret()
    expected_sig = hmac.new(secret, raw_json, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        data = json.loads(raw_json.decode("utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None

# Categories and their word-boundary patterns to prevent substring false positives
# (e.g. 'eventually' matching 'event', 'example' matching 'exam', 'quizzical' matching 'quiz').
CATEGORY_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "Assignment": [
        re.compile(r"\bassignments?\b", re.I),
        re.compile(r"\bhomeworks?\b", re.I),
        re.compile(r"\bproblem\s+sets?\b", re.I),
        re.compile(r"\bsubmissions?\b", re.I),
        re.compile(r"\bsubmit(?:s|ted|ting)?\b", re.I),
        re.compile(r"\bcoursework\b", re.I),
        re.compile(r"\blab\s+(?:record|manual|submission|report|exercise)s?\b", re.I),
        re.compile(r"\bproject\s+(?:submission|report|deadline|demo|presentation|evaluation|proposal|phase\s*\d+)s?\b", re.I),
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
        re.compile(r"\bclasses?\s+(?:are\s+)?(?:cancelled|suspended)\b", re.I),
        re.compile(r"\b(?:cancelled|canceled|cancellation|called\s+off)\b", re.I),
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
    re.compile(r"\bsubmit(?:s|ted|ting)?\b.*?\b(?:by|before|on|today|tomorrow|tonight)\b", re.I),
    re.compile(r"\bsubmit(?:s|ted|ting)?\b", re.I),
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

from temporal_parser import (
    BASIC_RELATIVE_DAYS,
    MONTH_NAMES,
    PATTERN_BASIC_RELATIVE,
    PATTERN_DATE_RANGE,
    PATTERN_DAY_MONTH_NO_YEAR,
    PATTERN_DAY_MONTH_YEAR,
    PATTERN_MONTH_DAY_NO_YEAR,
    PATTERN_MONTH_DAY_YEAR,
    PATTERN_MONTH_END,
    PATTERN_NUMERIC_FULL,
    PATTERN_RELATIVE_DURATION,
    PATTERN_RELATIVE_WEEKDAY,
    TIME_12H_NO_MINUTES,
    TIME_12H_WITH_MINUTES,
    TIME_24H,
    WEEKDAY_MAP,
    clean_ordinal,
    clean_ordinal as _clean_ordinal,
    detect_all_dates,
    detect_date,
    extract_time,
    extract_update_transition_dates,
    parse_message_date,
    parse_number,
    parse_reference_timestamp,
    resolve_weekday,
)

RELATIVE_DAYS = BASIC_RELATIVE_DAYS


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





# Conversational student chatter patterns to prevent false positives from casual chat
PAST_TENSE_COMPLETION_PATTERNS = [
    re.compile(r"\b(?:i|we|already)\s+(?:have\s+)?(?:completed|submitted|finished|done|uploaded)\b", re.I),
    re.compile(r"\b(?:i've|we've)\s+(?:completed|submitted|finished|done|uploaded)\b", re.I),
    re.compile(r"\b(?:completed|submitted|finished|uploaded)\s+(?:the|my|our)\s+(?:assignment|homework|lab|report|record|project)\b", re.I),
    re.compile(r"\bdone\s+with\s+(?:the\s+)?(?:assignment|homework|lab|project)\b", re.I),
]

PEER_QUESTION_PATTERNS = [
    re.compile(r"^(?:is|did|has|have|can|could|will|would|are|does|do|anyone|anybody)\b.*\?", re.I),
    re.compile(r"^(?:what|when|where|why|how)\b.*(?:\?|$)", re.I),
    re.compile(r"\b(?:did\s+anyone|has\s+anyone|anyone\s+submitted|is\s+tomorrow|when\s+is\s+the|what\s+is\s+the)\b.*(?:\?|$)", re.I),
    re.compile(r"\?+\s*$", re.I),
]

DISCUSSION_WITHOUT_DELIVERABLE_PATTERNS = [
    re.compile(r"\b(?:assignment|exam|quiz|project|lab|homework)\s+(?:discussion|meeting|clarification|doubt\s+clearing|review\s+session)\b", re.I),
    re.compile(r"\b(?:discussion|meeting|clarification|doubt\s+clearing)(?:\s+session)?\s+(?:on|about|for|regarding)\s+(?:the\s+)?(?:assignment|exam|quiz|project|lab|homework)\b", re.I),
]

# Explicit negative directives instructing not to perform an action (e.g. "Do not submit the old assignment.")
NEGATIVE_DIRECTIVE_PATTERNS = [
    re.compile(r"\b(?:do\s+not|don't|no\s+need\s+to|should\s+not|never)\s+(?:submit|register|attend|upload|apply|come)\b", re.I),
]

# Historical and completed past event patterns
HISTORICAL_PAST_PATTERNS = [
    re.compile(r"\b(?:was|were)\s+(?:conducted|held|organized|completed|done|finished|taken|concluded)\b", re.I),
    re.compile(r"\b(?:happened|occurred|took\s+place|concluded)\b", re.I),
    re.compile(r"\b(?:deadline\s+was|was\s+the\s+deadline)\b", re.I),
]

IMPERATIVE_DIRECTIVE_PATTERN = re.compile(
    r"\b(?:must\s+submit|please\s+submit|kindly\s+submit|submit\s+(?:by|before|on)|due\s+(?:on|by|date)|all\s+students\s+must|deadline\s+is)\b",
    re.I,
)


def is_conversational_chatter(text: str) -> bool:
    """Check if a message or segment is conversational student chatter rather than an academic instruction."""
    if not text:
        return False
    clean = text.strip()
    # Explicit negative directives (e.g. "Do not submit the old assignment") should not generate actionable tasks
    for pat in NEGATIVE_DIRECTIVE_PATTERNS:
        if pat.search(clean):
            return True
    # Explicit imperative deadline directive overrides chatter heuristics
    if IMPERATIVE_DIRECTIVE_PATTERN.search(clean):
        return False
    for pat in PAST_TENSE_COMPLETION_PATTERNS:
        if pat.search(clean):
            return True
    for pat in DISCUSSION_WITHOUT_DELIVERABLE_PATTERNS:
        if pat.search(clean):
            return True
    for pat in PEER_QUESTION_PATTERNS:
        if pat.search(clean):
            return True
    return False


def detect_update_type(text: str) -> str | None:
    """Detect whether text represents an update, postponement, extension, cancellation, revision, etc."""
    if not text:
        return None
    lowered = text.lower()
    # 1. Cancellation
    if re.search(r"\b(?:cancelled|canceled|cancellation|classes?\s+(?:are\s+)?suspended|suspended\s+until|called\s+off|deadline\s+(?:is\s+)?cancelled|exam\s+(?:is\s+)?cancelled)\b", lowered):
        return "cancellation"
    # 2. Confirmation
    if re.search(r"\b(?:confirms?|confirmation|remains?\s+unchanged|no\s+change\s+in\s+deadline|deadline\s+stands|remains?\s+as\s+scheduled|unaltered|deadline\s+is\s+confirmed|deadline\s+remains?)\b", lowered):
        return "confirmation"
    # 3. Extension
    if re.search(r"\b(?:deadline\s+)?(?:extended|extension|last\s+date\s+extended)\b", lowered):
        return "extension"
    # 4. Postponement
    if re.search(r"\b(?:postponed|postponement|deferred|put\s+on\s+hold|pushed\s+back)\b", lowered):
        return "postponement"
    # 5. Rescheduled
    if re.search(r"\b(?:rescheduled|reschedule)\b", lowered):
        return "rescheduled"
    # 6. Revision
    if re.search(r"\b(?:revised|revision|amended)\s+(?:deadline|schedule|date|timetable|submission)\b|\b(?:deadline|date|submission\s+date)\s+(?:has\s+been\s+|is\s+)?(?:revised|amended)\b", lowered):
        return "revision"
    # 7. Replacement
    if re.search(r"\b(?:replacing|superseding|in\s+lieu\s+of|replaces\s+the|new\s+deadline\s+replaces)\b", lowered):
        return "replacement"
    # 8. Window Change
    if re.search(r"\b(?:submission\s+window|window\s+is\s+(?:now\s+)?open|window\s+extended|portal\s+is\s+open)\b", lowered):
        return "window_change"
    return None


def detect_actionability(
    category: str,
    text: str,
    date_type: str,
    date_status: str,
    update_type: str | None,
) -> tuple[bool, str]:
    """Determine whether extracted academic information requires student action or is informational."""
    # Confirmations, cancellations, and indefinite postponements without a scheduled date are informational
    if update_type in ("cancellation", "confirmation"):
        return False, "informational"
    if update_type == "postponement" and date_status in ("not_found", "needs_review"):
        return False, "informational"

    # Announcements without direct action imperatives are informational
    if category == "Announcement":
        if re.search(r"\b(?:must|mandatory|required\s+to|action\s+required|please\s+submit|register\s+now)\b", text, re.I):
            return True, "action_required"
        return False, "informational"

    # Assignments and exams require student preparation or submission action
    if category in ("Assignment", "Exam"):
        return True, "action_required"

    # Opportunities (hackathons, internships, jobs)
    if category == "Opportunity":
        if date_type == "deadline" or re.search(r"\b(?:apply|register|submission)\b", text, re.I):
            return True, "action_required"
        return False, "fyi"

    # Events (workshops, seminars)
    if category == "Event":
        if re.search(r"\b(?:register|registration|mandatory|attendance\s+is\s+compulsory)\b", text, re.I):
            return True, "action_required"
        return False, "informational"

    return True, "action_required"


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

    # Contextual intelligence: if postponement or cancellation announcement without an explicit new date,
    # classify as Announcement rather than Exam or Assignment (e.g. 'The exam was postponed.')
    up_type = detect_update_type(text)
    if up_type in ("postponement", "cancellation"):
        has_explicit_date = bool(
            PATTERN_DAY_MONTH_YEAR.search(text)
            or PATTERN_MONTH_DAY_YEAR.search(text)
            or PATTERN_NUMERIC_FULL.search(text)
        )
        if not has_explicit_date:
            if "Announcement" not in matches:
                matches.append("Announcement")
            return "Announcement", matches

    # Priority ordering when multiple match
    priority_order = ["Assignment", "Exam", "Opportunity", "Event", "Announcement"]
    for cat in priority_order:
        if cat in matches:
            return cat, matches

    return matches[0], matches


ALLOWED_CATEGORIES = {"Assignment", "Exam", "Announcement", "Event", "Opportunity"}
ALLOWED_CONFIDENCE_LEVELS = {"HIGH", "MEDIUM", "LOW", "UNASSESSED"}

# Patterns for detecting prepositional/contextual event references that do NOT indicate
# a conflicting task intent (e.g. "report for the robotics workshop").
_PREP_EVENT_CONTEXT = re.compile(
    r"\b(?:for|at|in|during|towards|regarding|about)\s+"
    r"(?:the\s+|a\s+|an\s+|our\s+)?"
    r"(?:[\w-]+\s+)*"
    r"(?:workshops?|seminars?|conferences?|webinars?|symposiums?|events?)\b",
    re.IGNORECASE,
)
_COMPOUND_NOUN_EVENT = re.compile(
    r"\b(?:workshops?|seminars?|conferences?|webinars?|symposiums?)\s+"
    r"(?:assignments?|tasks?|reports?|submissions?|exercises?)\b",
    re.IGNORECASE,
)
_PREP_OPP_CONTEXT = re.compile(
    r"\b(?:for|at|in|during|towards)\s+"
    r"(?:the\s+|a\s+|an\s+|our\s+)?"
    r"(?:[\w-]+\s+)*"
    r"(?:internships?|hackathons?|competitions?|fellowships?)\b",
    re.IGNORECASE,
)
_PRIMARY_ASSIGNMENT_ACTION = re.compile(
    r"\b(?:submits?|submitted|submitting|due|coursework|homework|"
    r"lab\s+(?:report|record|manual|exercise|submission)|"
    r"project\s+(?:report|submission|demo|proposal))\b",
    re.IGNORECASE,
)


def _is_contextual_secondary_keyword(primary_cat: str, other_cat: str, text: str) -> bool:
    """Return True when other_cat keywords in text are contextual background rather than a conflicting task intent.

    Example:
        "Submit your lab exercise report for the robotics workshop on 28/10/2026."
        -> primary_cat=Assignment, other_cat=Event
        -> "workshop" is prepositional context for the submission, not an independent Event task.

    Example:
        "Semester exam assignment guidelines are published."
        -> primary_cat=Assignment, other_cat=Exam
        -> "exam" is genuinely a competing task intent (not contextual).
    """
    if primary_cat == "Assignment" and other_cat == "Event":
        has_primary_action = bool(_PRIMARY_ASSIGNMENT_ACTION.search(text))
        is_prep_context = bool(_PREP_EVENT_CONTEXT.search(text))
        is_compound_noun = bool(_COMPOUND_NOUN_EVENT.search(text))
        return has_primary_action and (is_prep_context or is_compound_noun)

    if primary_cat == "Assignment" and other_cat == "Opportunity":
        has_primary_action = bool(_PRIMARY_ASSIGNMENT_ACTION.search(text))
        is_prep_context = bool(_PREP_OPP_CONTEXT.search(text))
        return has_primary_action and is_prep_context

    return False


def calculate_confidence(
    category: str,
    all_matched_cats: list[str],
    date_info: dict[str, Any],
    date_type: str,
    is_isolated_event_keyword: bool,
    cluster_text: str,
) -> tuple[str, list[str]]:
    """Determine explainable, deterministic confidence level (HIGH, MEDIUM, LOW) and reasons.

    Decision Table / Rules:
    1. LOW Confidence:
       - Date is ambiguous or unresolvable (date_status == 'needs_review'):
         multiple conflicting dates, ambiguous numeric format, missing year, etc.
         (A candidate with an ambiguous date must never receive HIGH confidence).
       - Genuinely conflicting or ambiguous category matches where the secondary
         keyword represents a distinct task intent (not a contextual reference).
       - Generic keyword 'event' matched without specific academic event context.
       - Assignment date mentioned without explicit deadline phrasing (date_type == 'mentioned_date').
    2. MEDIUM Confidence:
       - Clear category with relative date resolved from message timestamp anchor.
       - Clear academic task with no date specified (date_status == 'not_found').
    3. HIGH Confidence:
       - Clear unambiguous category with explicit, validated calendar date (date_status == 'parsed')
         and confirmed deadline or event date type.

    Category Conflict Nuance:
       When multiple categories match but the secondary keywords are prepositional context
       (e.g. "for the workshop", "at the seminar"), they are treated as contextual information
       rather than conflicting task intents, and do not reduce confidence to LOW.
    """
    reasons: list[str] = []
    date_status = date_info.get("date_status", "not_found")

    # 1. Ambiguous or incomplete date -> LOW
    if date_status == "needs_review":
        reasons.append("Date expression is ambiguous, incomplete, or requires human confirmation.")
        date_reasons = date_info.get("date_reasons") or []
        for dr in date_reasons:
            if dr not in reasons:
                reasons.append(dr)
        return "LOW", reasons

    # 2. Category conflict analysis — distinguish genuine conflicts from contextual co-occurrence
    if len(all_matched_cats) > 1:
        genuine_conflict = False
        for other_cat in all_matched_cats:
            if other_cat == category:
                continue
            if not _is_contextual_secondary_keyword(category, other_cat, cluster_text):
                genuine_conflict = True
                break

        if genuine_conflict:
            reasons.append(
                f"Multiple conflicting academic categories matched ({', '.join(all_matched_cats)})."
            )
            return "LOW", reasons
        # else: secondary keywords are contextual — do not penalise confidence

    # 3. Weak generic 'event' keyword -> LOW
    if is_isolated_event_keyword:
        reasons.append("Generic keyword 'event' matched without specific academic event context.")
        return "LOW", reasons

    # 4. Assignment with mentioned date lacking deadline language -> LOW
    if category == "Assignment" and date_type == "mentioned_date":
        reasons.append("Date mentioned without explicit submission deadline phrasing.")
        return "LOW", reasons

    # 5. Missing date with clear academic task -> MEDIUM
    if date_status == "not_found":
        reasons.append("Clear academic task identified, but no deadline or event date was specified.")
        return "MEDIUM", reasons

    # 6. Relative date resolved from message timestamp -> MEDIUM
    if date_status == "resolved_from_message_date":
        reasons.append("Academic task identified with relative date resolved from message timestamp anchor.")
        return "MEDIUM", reasons

    # 7. Explicit validated calendar date with confirmed task intent -> HIGH
    if date_status == "parsed" and date_type in ("deadline", "event_date"):
        reasons.append("Unambiguous academic category with validated explicit calendar date.")
        return "HIGH", reasons

    # Default fallback -> MEDIUM
    reasons.append("Candidate academic task extracted with standard rule-based heuristics.")
    return "MEDIUM", reasons


# Comma-split pattern: splits on commas followed by an independent academic clause.
# Does NOT split dates like "Friday, 20 November 2026" or "November 20, 2026".
_COMMA_ACADEMIC_SPLIT = re.compile(
    r",\s*(?="
    r"(?:(?:also|please|kindly|additionally|remember\s+to|make\s+sure\s+to)\s+)*"
    r"(?:(?:the|an|a|your|our|final|internal|semester|next|upcoming|this)\s+)?"
    r"(?:(?:semester|midterm|final|internal|upcoming|next|model|online|revised|regular)\s+)?"
    r"(?:[A-Za-z0-9_-]+\s+)?"
    r"(?:exam|examination|test|quiz|assignment|homework|submission|"
    r"lab\s+(?:record|manual|report|exercise|submission)|"
    r"project\s+(?:submission|report|deadline|demo|presentation|proposal)|"
    r"workshop|seminar|webinar|conference|hackathon|internship)\b"
    r"|(?:(?:also|please|kindly|additionally|remember\s+to|make\s+sure\s+to)\s+)*(?:submit|register|apply|attend|prepare|complete|upload)\b"
    r")",
    re.IGNORECASE,
)

# Conjunction split pattern for splitting on "and/but/while/as well as" before independent academic tasks.
# Supports optional comma prefix before conjunction (e.g. ", but the online assignment...") and descriptor modifiers.
_CONJ_ACADEMIC_SPLIT = re.compile(
    r"(?:,\s*)?\s+(?:and|but|while|as\s+well\s+as|along\s+with)\s+(?="
    r"(?:[^\w\s]+\s*)*"
    r"(?:(?:also|please|kindly|additionally|remember\s+to|make\s+sure\s+to)\s+)*"
    r"(?:the\s+)?"
    r"(?:prepare\s+(?:for\s+)?|attend\s+|register\s+(?:for\s+)?|submit\s+|write\s+|complete\s+|upload\s+)?"
    r"(?:(?:the|a|an|your|our|this)\s+)?"
    r"(?:semester|midterm|final|internal|upcoming|next|model|online|revised|regular)?\s*"
    r"(?:assignment|exam|examination|test|quiz|workshop|seminar|conference|hackathon|internship|submission|registration|lab|project)\b"
    r")",
    re.IGNORECASE,
)


def split_message_into_segments(text: str) -> list[str]:
    """Split message text into candidate clauses / sentences while preserving abbreviations.

    Splits on:
    - Sentence-ending punctuation followed by a capital letter or digit.
    - Exclamation marks, question marks.
    - Semicolons.
    - Newlines.
    - Coordinating conjunctions (and, but, while) before academic nouns.
    - Commas before independent academic clauses (comma-separated task lists).

    Does NOT split on:
    - Commas inside dates ("Friday, 20 November 2026", "November 20, 2026").
    - Commas inside abbreviations (Dr., Prof., etc.).
    - Commas inside normal sentence structure (non-academic context).
    """
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
        protected = re.sub(r"\b" + re.escape(abbr), placeholder, protected, flags=re.IGNORECASE)

    # Primary splits: sentence boundaries, semicolons, newlines
    sentence_split_regex = re.compile(
        r"(?:\.\s+(?=[A-Z0-9])|[!?]\s+|;\s*|\n+)",
        re.IGNORECASE,
    )

    primary_segments: list[str] = []
    for seg in sentence_split_regex.split(protected):
        clean = seg.strip()
        if not clean:
            continue
        # Secondary split: coordinating conjunctions before academic nouns
        sub_parts = _CONJ_ACADEMIC_SPLIT.split(clean)
        for part in sub_parts:
            part = part.strip()
            if not part:
                continue
            # Tertiary split: comma-separated independent academic clauses
            comma_parts = _COMMA_ACADEMIC_SPLIT.split(part)
            for cp in comma_parts:
                cp = cp.strip()
                if cp:
                    primary_segments.append(cp)

    segments: list[str] = []
    for seg in primary_segments:
        for placeholder, original in abbr_map.items():
            seg = seg.replace(placeholder, original)
        segments.append(seg)

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

    for raw_msg in messages:
        message = raw_msg.to_dict() if hasattr(raw_msg, "to_dict") else raw_msg
        sender = message.get("sender") or message.get("source_sender") or "System"
        text = message.get("text") or message.get("source_text") or ""
        source_type = message.get("source_type", "whatsapp")
        source_id = message.get("source_id")
        source_metadata = message.get("source_metadata") or {}

        # System notifications (encryption, user added, etc.) are not academic items.
        if sender == "System":
            continue

        # Check if message has any academic category
        msg_category, _ = classify_message(text)
        if msg_category is None:
            continue

        timestamp_text = message.get("timestamp_text") or message.get("source_timestamp") or ""

        # Segment message into sentences / clauses
        segments = split_message_into_segments(text)

        # If all segments are conversational chatter, ignore message
        if all(is_conversational_chatter(s) for s in segments):
            continue

        # Cluster segments into academic tasks
        task_clusters: list[list[str]] = []
        current_cluster: list[str] = []
        current_cat: str | None = None
        current_date_info: dict[str, Any] | None = None
        current_date_type: str = "none"

        for seg in segments:
            # Skip conversational chatter segments within a message
            if is_conversational_chatter(seg):
                continue
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
        current_text_offset = 0
        for cluster in task_clusters:
            if cluster:
                search_pos = current_text_offset
                start_pos = -1
                end_pos = -1
                all_found = True
                for i, seg in enumerate(cluster):
                    idx = text.find(seg, search_pos)
                    if idx == -1:
                        all_found = False
                        break
                    if i == 0:
                        start_pos = idx
                    end_pos = idx + len(seg)
                    search_pos = end_pos

                if all_found and start_pos != -1 and end_pos != -1:
                    raw_span = text[start_pos:end_pos]
                    leading_ws = len(raw_span) - len(raw_span.lstrip())
                    trailing_ws = len(raw_span) - len(raw_span.rstrip())
                    ev_start = start_pos + leading_ws
                    ev_end = end_pos - trailing_ws
                    cluster_text = text[ev_start:ev_end]
                    current_text_offset = end_pos
                    evidence_start_index = ev_start
                    evidence_end_index = ev_end
                else:
                    cluster_text = " ".join(cluster).strip()
                    evidence_start_index = None
                    evidence_end_index = None
            else:
                cluster_text = ""
                evidence_start_index = None
                evidence_end_index = None
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

            # Distinguish date resolution from temporal meaning:
            # 1. Historical events ("was conducted yesterday", "workshop happened yesterday"):
            #    Not an automatically created pending deadline -> due_date is None, date_type="event_date", is_actionable=False.
            # 2. Past deadlines ("assignment deadline was yesterday"):
            #    Past deadline preserved as due_date (not an invented future date), but is_actionable=False, review_required=True.
            is_past_text = any(pat.search(cluster_text) for pat in HISTORICAL_PAST_PATTERNS)
            message_date = parse_reference_timestamp(timestamp_text)
            is_past_date = False
            if date_info["due_date"] is not None and message_date is not None:
                try:
                    due_d = datetime.strptime(date_info["due_date"], "%Y-%m-%d").date()
                    if due_d < message_date:
                        is_past_date = True
                except ValueError:
                    pass
            elif date_info["date_text"] and "yesterday" in date_info["date_text"].lower():
                is_past_date = True

            is_historical_event = (is_past_text or is_past_date) and category in ("Event", "Exam", "Announcement") and not has_deadline_language
            is_past_deadline = (is_past_text or is_past_date) and has_deadline_language

            if is_historical_event:
                date_type = "event_date"
                item_due_date = None  # Do not force historical event dates into due_date
                item_date_status = date_info["date_status"]
            elif is_past_deadline:
                date_type = "deadline"
                item_due_date = date_info["due_date"]  # Preserve past deadline without inventing a future date
                item_date_status = "needs_review"
            else:
                item_due_date = date_info["due_date"]
                item_date_status = date_info["date_status"]

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

            if item_date_status == "needs_review":
                review_required = True

            if is_past_deadline:
                review_required = True
                review_reasons.append("Deadline is in the past relative to the message timestamp.")

            if category == "Assignment" and date_type == "mentioned_date":
                review_required = True
                review_reasons.append("Date mentioned without explicit deadline phrasing (e.g. 'due', 'submit by').")

            # Category conflict check: only flag review if the secondary keyword represents
            # a genuine competing task intent, not a contextual prepositional reference.
            if len(all_matched_cats) > 1:
                has_genuine_conflict = any(
                    not _is_contextual_secondary_keyword(category, other_cat, cluster_text)
                    for other_cat in all_matched_cats
                    if other_cat != category
                )
                if has_genuine_conflict:
                    review_required = True
                    review_reasons.append(
                        f"Multiple categories matched ({', '.join(all_matched_cats)}); classified as '{category}'."
                    )

            if is_isolated_event_keyword and date_info["date_status"] == "not_found":
                review_required = True
                review_reasons.append("Message matched generic word 'event' without specific event terminology or dates.")

            confidence, confidence_reasons = calculate_confidence(
                category=category,
                all_matched_cats=all_matched_cats,
                date_info=date_info,
                date_type=date_type,
                is_isolated_event_keyword=is_isolated_event_keyword,
                cluster_text=cluster_text,
            )

            if confidence == "LOW":
                review_required = True

            review_reasons = list(dict.fromkeys(review_reasons))

            # Intelligence heuristics: actionability and update categorization
            update_type = detect_update_type(cluster_text)
            previous_due_date = None
            item_date_text = date_info["date_text"]

            if update_type:
                trans = extract_update_transition_dates(cluster_text, timestamp_text)
                if trans:
                    if trans.get("previous_date"):
                        previous_due_date = trans["previous_date"]
                    elif trans.get("previous_date_text"):
                        previous_due_date = trans["previous_date_text"]
                    if trans.get("new_date"):
                        item_due_date = trans["new_date"]
                        item_date_status = trans["new_date_status"]
                    if trans.get("new_date_text"):
                        item_date_text = trans["new_date_text"]

                if update_type == "cancellation":
                    item_due_date = None
                    item_date_status = "not_found"
                    date_type = "none"
                    is_actionable = False
                    actionability_type = "informational"
                    review_required = True
                    review_reasons.append("Deadline or academic event cancelled by notice.")
                elif update_type == "confirmation":
                    if not item_due_date and date_info["date_status"] == "not_found":
                        is_actionable = False
                        actionability_type = "informational"
                elif update_type == "window_change":
                    date_type = "deadline"
                    is_actionable = True
                    actionability_type = "action_required"

            if is_historical_event or is_past_deadline:
                is_actionable = False
                actionability_type = "informational"
            else:
                is_actionable, actionability_type = detect_actionability(
                    category=category,
                    text=cluster_text,
                    date_type=date_type,
                    date_status=item_date_status,
                    update_type=update_type,
                )

            # Construct title
            lines = [l.strip() for l in cluster if l.strip()]
            title = lines[0][:120].strip() if lines else cluster_text[:120].strip()

            item = {
                "item_id": message.get("message_id", len(items) + 1),
                "category": category,
                "title": title or "Untitled candidate message",
                "date_text": item_date_text,
                "due_date": item_due_date,
                "date_status": item_date_status,
                "date_type": date_type,
                "is_range": bool(date_info.get("is_range", False)),
                "time_text": time_info["time_text"],
                "deadline_time": time_info["deadline_time"],
                "previous_due_date": previous_due_date,
                "urls": urls,
                "evidence_text": cluster_text,
                "evidence_start_index": evidence_start_index,
                "evidence_end_index": evidence_end_index,
                "confidence": confidence,
                "confidence_reasons": confidence_reasons,
                "is_actionable": is_actionable,
                "actionability_type": actionability_type,
                "update_type": update_type,
                "source_message_id": message.get("message_id"),
                "source_sender": sender,
                "source_timestamp": timestamp_text,
                "source_text": text,
                "source_filename": message.get("source_filename") or message.get("filename") or "",
                "source_type": source_type,
                "source_id": source_id,
                "source_metadata": source_metadata,
                "extraction_method": "rules",
                "review_required": review_required,
                "review_reasons": review_reasons,
            }

            intent, intent_reasons = classify_academic_intent(
                category=category,
                title=title,
                text=cluster_text,
                actionability_type=actionability_type,
            )
            importance, importance_reasons = assess_academic_importance(
                category=category,
                academic_intent=intent,
                title=title,
                text=cluster_text,
                is_actionable=is_actionable,
                status="pending",
            )
            urgency, urgency_reasons, delta_days = assess_task_urgency(
                due_date=item_due_date,
                date_status=item_date_status,
                status="pending",
                current_date=None,
                text=cluster_text,
            )
            priority, priority_reasons = calculate_priority(
                urgency=urgency,
                importance=importance,
                is_actionable=is_actionable,
                status="pending",
                date_status=item_date_status,
                delta_days=delta_days,
                review_required=review_required,
            )

            item["academic_intent"] = intent
            item["academic_intent_reasons"] = intent_reasons
            item["importance"] = importance
            item["importance_reasons"] = importance_reasons
            item["urgency"] = urgency
            item["urgency_reasons"] = urgency_reasons
            item["delta_days"] = delta_days
            item["priority"] = priority
            item["priority_reasons"] = priority_reasons

            item["candidate_token"] = create_candidate_token(item)
            items.append(item)

    return items
