"""iCalendar (RFC 5545) Export Module for SMART.

Generates standards-compliant .ics calendar exports for confirmed academic deadlines.
Applies RFC 5545 text escaping and line folding rules without inventing timezones
or speculative times.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any


def escape_ics_text(text: str) -> str:
    """Escape text according to RFC 5545 Section 3.3.11.

    Escapes backslashes first, then semicolons, commas, and converts newlines to literal '\\n'.
    """
    if not text:
        return ""
    # Backslash first
    escaped = text.replace("\\", "\\\\")
    # Semicolons
    escaped = escaped.replace(";", r"\;")
    # Commas
    escaped = escaped.replace(",", r"\,")
    # Newlines
    escaped = escaped.replace("\r\n", "\n").replace("\r", "\n").replace("\n", r"\n")
    return escaped


def fold_ics_line(line: str, max_bytes: int = 75) -> str:
    """Fold lines longer than 75 octets according to RFC 5545 Section 3.1.

    Inserts CRLF followed by a single space.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= max_bytes:
        return line

    chunks: list[str] = []
    current_chunk = bytearray()
    limit = max_bytes

    for char in line:
        char_bytes = char.encode("utf-8")
        if len(current_chunk) + len(char_bytes) > limit:
            chunks.append(current_chunk.decode("utf-8"))
            current_chunk = bytearray(b" " + char_bytes)
            limit = max_bytes
        else:
            current_chunk.extend(char_bytes)

    if current_chunk:
        chunks.append(current_chunk.decode("utf-8"))

    return "\r\n".join(chunks)


def format_dtstamp(timestamp_str: str | None) -> str:
    """Format an ISO timestamp into UTC iCalendar format (YYYYMMDDTHHMMSSZ)."""
    if timestamp_str:
        try:
            # Handle standard ISO strings
            clean_ts = timestamp_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_ts)
            dt_utc = dt.astimezone(timezone.utc)
            return dt_utc.strftime("%Y%m%dT%H%M%SZ")
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def generate_ics(items: list[dict[str, Any]]) -> str:
    """Generate RFC 5545 compliant iCalendar content for confirmed deadlines.

    Only includes items with date_type='deadline' and a valid due_date.
    """
    raw_lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SMART Academic Intelligence//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for item in items:
        # Strict filter: only confirmed deadlines with valid due_date
        due_date = item.get("due_date")
        date_type = (item.get("date_type") or "").strip().lower()
        if not due_date or date_type != "deadline":
            continue

        # Format date as YYYYMMDD
        date_parts = str(due_date).strip().split("-")
        if len(date_parts) != 3 or len(date_parts[0]) != 4:
            continue
        compact_date = "".join(date_parts)

        item_id = item.get("id") or "0"
        uid = f"smart-deadline-item-{item_id}@smart.local"
        dtstamp = format_dtstamp(item.get("updated_at") or item.get("created_at"))

        title = item.get("title") or "Academic Deadline"
        escaped_summary = escape_ics_text(title)

        # Assemble informative description
        desc_parts: list[str] = []
        if item.get("category"):
            desc_parts.append(f"Category: {item['category']}")
        if item.get("source_sender"):
            desc_parts.append(f"Sender: {item['source_sender']}")
        if item.get("source_timestamp"):
            desc_parts.append(f"Source Date: {item['source_timestamp']}")
        if item.get("source_filename"):
            desc_parts.append(f"Export Source: {item['source_filename']}")
        if item.get("description"):
            desc_parts.append(f"\nDetails:\n{item['description']}")
        elif item.get("source_text"):
            desc_parts.append(f"\nOriginal Message:\n{item['source_text']}")

        full_desc = "\n".join(desc_parts)
        escaped_desc = escape_ics_text(full_desc)

        raw_lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{compact_date}",
                f"SUMMARY:{escaped_summary}",
                f"DESCRIPTION:{escaped_desc}",
                "END:VEVENT",
            ]
        )

    raw_lines.append("END:VCALENDAR")

    # Fold each line per RFC 5545 and join with CRLF
    folded_lines = [fold_ics_line(line) for line in raw_lines]
    return "\r\n".join(folded_lines) + "\r\n"
