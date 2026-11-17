"""WhatsApp Chat Export Parser for SMART.

Converts raw text exports from WhatsApp (Android and iOS) into structured message
dictionaries.

Known Limitations:
1. Export formats vary by OS language/locale settings (e.g. DD/MM/YYYY vs MM/DD/YYYY).
2. WhatsApp exports do not contain timezone offsets.
3. Media attachments appear as placeholders (e.g. "<Media omitted>") without file payloads.
4. Messages spanning multiple lines without timestamps are treated as continuation of the
   preceding message.
"""

import re
from typing import Any

# Remove invisible directional formatting marks and BOMs frequently found in WhatsApp exports.
INVISIBLE_CHARS_PATTERN = re.compile(r"[\u200e\u200f\u202a-\u202e\ufeff]")

# Normalize narrow no-break space and non-breaking spaces.
SPACE_NORMALIZE_PATTERN = re.compile(r"[\u202f\xa0]")

# Common WhatsApp system notification phrases without sender.
SYSTEM_NOTIFICATION_PATTERNS = [
    re.compile(r"^messages and calls are end-to-end encrypted", re.IGNORECASE),
    re.compile(r"^you (created group|added|were added|left|deleted)", re.IGNORECASE),
    re.compile(r"joined using this group's invite link", re.IGNORECASE),
    re.compile(r"security code changed", re.IGNORECASE),
    re.compile(r"changed the subject to", re.IGNORECASE),
    re.compile(r"changed the group description", re.IGNORECASE),
    re.compile(r"changed this group's icon", re.IGNORECASE),
    re.compile(r"this message was deleted", re.IGNORECASE),
]

# Combined pattern for iOS and Android WhatsApp timestamp headers.
# iOS format: [19/10/2026, 9:00:00 AM] Sender: Message
# Android format: 19/10/26, 9:00 am - Sender: Message
MESSAGE_PATTERN = re.compile(
    r"^(?:"
    # iOS: [date, time] content
    r"\[(?P<ios_date>\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}),\s*"
    r"(?P<ios_time>\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM|am|pm|a\.m\.|p\.m\.))?)\]\s*"
    r"(?P<ios_content>.*)"
    r"|"
    # Android: date, time - content
    r"(?P<android_date>\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}),\s*"
    r"(?P<android_time>\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM|am|pm|a\.m\.|p\.m\.))?)\s*[-–—]\s*"
    r"(?P<android_content>.*)"
    r")$",
    re.IGNORECASE,
)


def clean_line(line: str) -> str:
    """Strip invisible direction marks and normalize Unicode spaces."""
    cleaned = INVISIBLE_CHARS_PATTERN.sub("", line)
    cleaned = SPACE_NORMALIZE_PATTERN.sub(" ", cleaned)
    return cleaned.strip("\r")


def is_system_notification(content: str) -> bool:
    """Check if the content matches known WhatsApp system notices."""
    for pattern in SYSTEM_NOTIFICATION_PATTERNS:
        if pattern.search(content):
            return True
    return False


def parse_whatsapp_text(raw_text: str) -> list[dict[str, Any]]:
    """Parse raw WhatsApp text export into structured message records.

    Each message record contains:
    - message_id: 1-based sequential integer
    - timestamp_text: combined date and time string
    - date: extracted date string (e.g. '19/10/2026')
    - time: extracted time string (e.g. '9:00 AM')
    - sender: sender display name or 'System'
    - text: message text content (including multiline continuations)
    """
    if not raw_text or not raw_text.strip():
        return []

    messages: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_line in raw_text.splitlines():
        line = clean_line(raw_line)
        match = MESSAGE_PATTERN.match(line)

        if match:
            # Commit the previous message before starting the new one.
            if current is not None:
                messages.append(current)

            date = (match.group("ios_date") or match.group("android_date") or "").strip()
            time = (match.group("ios_time") or match.group("android_time") or "").strip()
            content = (
                match.group("ios_content")
                if match.group("ios_content") is not None
                else match.group("android_content")
            ) or ""

            # Standard chat format has "Sender: message".
            # Continuation colons inside the message are preserved by splitting only once.
            if is_system_notification(content):
                sender = "System"
                text = content
            elif ": " in content:
                sender_part, text_part = content.split(": ", 1)
                sender = sender_part.strip() or "System"
                text = text_part
            else:
                sender = "System"
                text = content

            current = {
                "message_id": len(messages) + 1,
                "timestamp_text": f"{date}, {time}",
                "date": date,
                "time": time,
                "sender": sender,
                "text": text,
            }

        elif current is not None:
            # Append continuation line to previous message body, preserving formatting.
            current["text"] += "\n" + raw_line

    if current is not None:
        messages.append(current)

    return messages
