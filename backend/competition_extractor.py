"""Competition and Opportunity Extraction Engine for SMART 2.1.

Identifies academic competitions, hackathons, coding contests, paper submissions,
and research grants from communication messages. Extracts structured metadata
(name, organizer, eligibility, deadlines, event dates, registration links) with
evidence tracing, without inventing missing fields.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from temporal_parser import (
    BASIC_RELATIVE_DAYS,
    PATTERN_BASIC_RELATIVE,
    PATTERN_DAY_MONTH_NO_YEAR,
    PATTERN_DAY_MONTH_YEAR,
    PATTERN_MONTH_DAY_NO_YEAR,
    PATTERN_MONTH_DAY_YEAR,
    PATTERN_NUMERIC_FULL,
    detect_date,
    parse_message_date,
    parse_reference_timestamp,
    resolve_weekday,
)

# Competition & hackathon detection patterns (strictly non-newline spaces)
COMPETITION_TITLE_PATTERNS = [
    re.compile(r"\b([A-Z0-9][A-Za-z0-9\t -]{2,40}[ \t]+(?:Hackathon|Datathon|Ideathon|Olympiad|Challenge|Competition|Contest|Championship|Symposium|Fellowship|Regional|Olympiads))\b", re.I),
    re.compile(r"\b((?:National|International|State|Inter-College|Annual|Global)[ \t]+[A-Za-z0-9\t -]{2,35}[ \t]+(?:Competition|Hackathon|Contest|Challenge|Regional))\b", re.I),
    re.compile(r"\b([A-Z0-9]{2,10}[ \t]+(?:Coding[ \t]+Contest|Programming[ \t]+Challenge|Hackathon))\b", re.I),
    re.compile(r"\b(Call[ \t]+for[ \t]+(?:Papers|Proposals|Projects|Submissions))\b", re.I),
]

ORGANIZER_PATTERNS = [
    re.compile(r"\b(?:organized|hosted|conducted|presented)\s+by\s+([A-Za-z0-9\s,.&-]{3,50})(?:\.|\n|,|$)", re.I),
    re.compile(r"\bby\s+(?:the\s+)?([A-Za-z0-9\s.&-]{3,40}\s+(?:Department|University|Institute|College|Club|Society|Chapter|Foundation|Corporation|Inc))\b", re.I),
    re.compile(r"\b([A-Za-z0-9\s.&-]{3,40}\s+(?:University|Institute|College|ACM\s+Student\s+Chapter|IEEE\s+Student\s+Branch))\s+invites\b", re.I),
]

ELIGIBILITY_PATTERNS = [
    re.compile(r"\b(?:eligibility|eligible|open\s+to)\s*:\s*([^\n.;]{4,80})", re.I),
    re.compile(r"\bopen\s+to\s+(?:all\s+)?(students|undergraduates|postgraduates|engineering\s+students|developers|teams)\b", re.I),
    re.compile(r"\b(?:all\s+)?([A-Za-z0-9\s]{2,30}\s+students)\s+(?:can|are\s+eligible\s+to)\s+participate\b", re.I),
]

DEADLINE_PATTERNS = [
    re.compile(r"\b(?:registration|register|apply|submission)\s+(?:deadline|closes?|by|before|last\s+date)\s*(?:is|:)?\s*([^\n.;]{4,40})", re.I),
    re.compile(r"\blast\s+date\s+(?:for\s+registration|to\s+register|to\s+apply)\s*(?:is|:)?\s*([^\n.;]{4,40})", re.I),
    re.compile(r"\bregister\s+(?:by|before|on)\s+([^\n.;]{4,40})", re.I),
]

EVENT_DATE_PATTERNS = [
    re.compile(r"\b(?:event\s+date|hackathon\s+date|competition\s+date|contest\s+date|date\s+of\s+event|scheduled\s+on)\s*(?:is|:)?\s*([^\n.;]{4,40})", re.I),
    re.compile(r"\b(?:held|conducted|taking\s+place)\s+on\s+([^\n.;]{4,40})", re.I),
]

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,!?;:)]}>\"'"


def extract_urls(text: str) -> list[str]:
    """Extract and deduplicate HTTP(S) links."""
    if not text:
        return []
    urls: list[str] = []
    for raw in URL_PATTERN.findall(text):
        cleaned = raw
        while cleaned and cleaned[-1] in TRAILING_PUNCTUATION:
            if cleaned[-1] == ")" and cleaned.count("(") >= cleaned.count(")"):
                break
            cleaned = cleaned[:-1]
        if cleaned:
            parsed = urlparse(cleaned)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                urls.append(cleaned)
    return list(dict.fromkeys(urls))


def is_competition_text(text: str) -> bool:
    """Determine whether text describes a competition or academic opportunity."""
    if not text:
        return False
    lowered = text.lower()
    keywords = [
        "hackathon",
        "competition",
        "contest",
        "ideathon",
        "datathon",
        "olympiad",
        "coding challenge",
        "call for papers",
        "fellowship",
        "project grant",
        "symposium",
        "case study challenge",
    ]
    return any(k in lowered for k in keywords)


def extract_competition_opportunity(
    text: str,
    source_id: Optional[str] = None,
    source_sender: Optional[str] = None,
    source_timestamp: Optional[str] = None,
    source_type: str = "gmail",
    is_demo: bool = False,
) -> Optional[dict[str, Any]]:
    """Extract a structured competition opportunity record from communication text.

    Allows incomplete records when fields are absent. Never invents deadlines or URLs.
    """
    if not text or not is_competition_text(text):
        return None

    clean_text = text.strip()

    # 1. Name
    name: Optional[str] = None
    for pat in COMPETITION_TITLE_PATTERNS:
        m = pat.search(clean_text)
        if m:
            name = m.group(1).strip()
            break
    if not name:
        # Fallback: first line or snippet with hackathon/contest keyword
        lines = [ln.strip() for ln in clean_text.splitlines() if ln.strip()]
        for ln in lines:
            if any(k in ln.lower() for k in ("hackathon", "competition", "contest", "challenge", "fellowship")):
                if len(ln) <= 80:
                    name = ln
                    break
        if not name:
            name = "Academic Competition / Challenge"

    # 2. Organizer
    organizer: Optional[str] = None
    for pat in ORGANIZER_PATTERNS:
        m = pat.search(clean_text)
        if m:
            organizer = m.group(1).strip()
            break
    if not organizer and source_sender and "@" in source_sender:
        organizer = source_sender.split("<")[0].strip() or source_sender

    # 3. Eligibility
    eligibility: Optional[str] = None
    for pat in ELIGIBILITY_PATTERNS:
        m = pat.search(clean_text)
        if m:
            eligibility = m.group(1).strip()
            break

    # 4. URLs
    urls = extract_urls(clean_text)
    registration_url = urls[0] if urls else None

    # Reference timestamp for relative date resolution
    ref_dt = parse_reference_timestamp(source_timestamp)

    # 5. Registration Deadline
    reg_deadline: Optional[str] = None
    deadline_evidence: Optional[str] = None
    for pat in DEADLINE_PATTERNS:
        m = pat.search(clean_text)
        if m:
            raw_match = m.group(1).strip()
            date_info = detect_date(raw_match, source_timestamp)
            if date_info and date_info.get("due_date"):
                reg_deadline = date_info["due_date"]
                deadline_evidence = m.group(0).strip()
                break

    # 6. Event Date
    event_date: Optional[str] = None
    for pat in EVENT_DATE_PATTERNS:
        m = pat.search(clean_text)
        if m:
            raw_match = m.group(1).strip()
            date_info = detect_date(raw_match, source_timestamp)
            if date_info and date_info.get("due_date"):
                event_date = date_info["due_date"]
                break

    # 7. Confidence & Review status
    reasons: list[str] = []
    if not reg_deadline:
        reasons.append("Missing explicit registration deadline.")
    if not registration_url:
        reasons.append("No registration link detected.")
    if not eligibility:
        reasons.append("Eligibility criteria unspecified.")

    confidence = "HIGH" if (reg_deadline and registration_url) else ("MEDIUM" if reg_deadline or registration_url else "LOW")
    review_status = "confirmed" if confidence == "HIGH" else "needs_review"

    # Evidence snippet
    evidence_text = deadline_evidence or (name if name in clean_text else clean_text[:200])

    return {
        "name": name,
        "organizer": organizer,
        "description": clean_text[:350],
        "eligibility": eligibility,
        "registration_deadline": reg_deadline,
        "event_date": event_date,
        "registration_url": registration_url,
        "source_type": source_type,
        "source_id": source_id,
        "source_sender": source_sender or "Academic Notification",
        "source_timestamp": source_timestamp,
        "evidence_text": evidence_text,
        "confidence": confidence,
        "review_status": review_status,
        "is_demo": 1 if is_demo else 0,
    }
