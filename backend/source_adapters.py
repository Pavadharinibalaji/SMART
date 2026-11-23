"""Source Adapter Layer for SMART 2.0.

Provides a normalized message representation and pluggable adapter architecture
decoupling source-specific communication formats (WhatsApp, Gmail, Google Classroom,
Manual) from SMART's academic intelligence extraction pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Any, Optional

from parser import parse_whatsapp_text

ALLOWED_SOURCE_TYPES = {"whatsapp", "gmail", "google_classroom", "manual"}


@dataclass
class SourceMessage:
    """Normalized communication message representation for SMART intelligence engine.

    Fields:
    - source_type: Origin platform ('whatsapp', 'gmail', 'google_classroom', 'manual').
    - source_id: Stable identifier from origin platform (e.g. email Message-ID, post ID).
    - source_sender: Sender display name, email, or institutional identity.
    - source_timestamp: Original message timestamp string.
    - source_text: Message body / textual content.
    - source_filename: Origin filename where applicable (e.g. WhatsApp export .txt).
    - source_metadata: Extensible dictionary for source-specific headers or attributes.
    - message_id: Sequential or local integer identifier for internal tracking.
    """

    source_type: str = "whatsapp"
    source_id: Optional[str] = None
    source_sender: str = "System"
    source_timestamp: str = ""
    source_text: str = ""
    source_filename: str = ""
    source_metadata: dict[str, Any] = field(default_factory=dict)
    message_id: int = 1

    def __post_init__(self) -> None:
        """Validate and normalize fields."""
        clean_type = (self.source_type or "").strip().lower()
        if clean_type not in ALLOWED_SOURCE_TYPES:
            raise ValueError(
                f"Invalid source_type '{self.source_type}'. "
                f"Allowed types: {', '.join(sorted(ALLOWED_SOURCE_TYPES))}"
            )
        self.source_type = clean_type
        self.source_sender = (self.source_sender or "System").strip()
        self.source_text = self.source_text or ""
        self.source_timestamp = (self.source_timestamp or "").strip()
        self.source_filename = (self.source_filename or "").strip()
        if self.source_id is not None:
            self.source_id = str(self.source_id).strip() or None
        if not isinstance(self.source_metadata, dict):
            self.source_metadata = {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary compatible with extract_academic_items."""
        return {
            "message_id": self.message_id,
            "sender": self.source_sender,
            "timestamp_text": self.source_timestamp,
            "text": self.source_text,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_sender": self.source_sender,
            "source_timestamp": self.source_timestamp,
            "source_text": self.source_text,
            "source_filename": self.source_filename,
            "source_metadata": self.source_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceMessage:
        """Reconstruct SourceMessage from dictionary serialization."""
        return cls(
            source_type=data.get("source_type", "whatsapp"),
            source_id=data.get("source_id"),
            source_sender=data.get("source_sender") or data.get("sender") or "System",
            source_timestamp=data.get("source_timestamp") or data.get("timestamp_text") or "",
            source_text=data.get("source_text") or data.get("text") or "",
            source_filename=data.get("source_filename") or "",
            source_metadata=data.get("source_metadata") if isinstance(data.get("source_metadata"), dict) else {},
            message_id=data.get("message_id", 1),
        )


class SourceAdapter(ABC):
    """Abstract base class for academic communication source adapters."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Unique identifier of the communication source."""
        pass

    @abstractmethod
    def parse(self, raw_input: Any, **kwargs: Any) -> list[SourceMessage]:
        """Parse raw platform payload into normalized SourceMessage objects."""
        pass


class WhatsAppAdapter(SourceAdapter):
    """Adapter for WhatsApp chat exports (.txt format). Preserves existing parser."""

    @property
    def source_type(self) -> str:
        return "whatsapp"

    def parse(self, raw_input: Any, **kwargs: Any) -> list[SourceMessage]:
        raw_text = str(raw_input) if raw_input is not None else ""
        filename = kwargs.get("filename", "")
        parsed = parse_whatsapp_text(raw_text)

        messages: list[SourceMessage] = []
        for item in parsed:
            msg_id = item.get("message_id", len(messages) + 1)
            # Create a deterministic source_id from filename and message_id if available
            stable_id = f"wa_{filename}_{msg_id}" if filename else f"wa_msg_{msg_id}"
            messages.append(
                SourceMessage(
                    source_type="whatsapp",
                    source_id=stable_id,
                    source_sender=item.get("sender", "System"),
                    source_timestamp=item.get("timestamp_text", ""),
                    source_text=item.get("text", ""),
                    source_filename=filename,
                    source_metadata={
                        "date": item.get("date", ""),
                        "time": item.get("time", ""),
                    },
                    message_id=msg_id,
                )
            )
        return messages


class GmailAdapter(SourceAdapter):
    """Adapter for Gmail messages (JSON / dictionary representation).

    Accepts:
    - A list of email dicts, OR a single email dict, OR JSON string.
    Supported email fields:
    - id / messageId: unique email id
    - sender / from: sender address or name
    - timestamp / date: email date string
    - subject: subject line (prepended to body if relevant)
    - body / text / snippet: email message text
    - labels / threadId / cc: optional metadata
    """

    @property
    def source_type(self) -> str:
        return "gmail"

    def parse(self, raw_input: Any, **kwargs: Any) -> list[SourceMessage]:
        data = raw_input
        if isinstance(raw_input, str):
            try:
                data = json.loads(raw_input)
            except Exception:
                # Check for RFC email headers: From:, Date:, Subject:
                rfc_from = re.search(r"^From:\s*(.+)$", raw_input, re.MULTILINE | re.IGNORECASE)
                rfc_date = re.search(r"^Date:\s*(.+)$", raw_input, re.MULTILINE | re.IGNORECASE)
                rfc_subject = re.search(r"^Subject:\s*(.+)$", raw_input, re.MULTILINE | re.IGNORECASE)
                if rfc_from or rfc_date or rfc_subject:
                    parts = raw_input.split("\n\n", 1)
                    body = parts[1].strip() if len(parts) > 1 else raw_input
                    data = [{
                        "from": rfc_from.group(1).strip() if rfc_from else "Unknown Sender",
                        "date": rfc_date.group(1).strip() if rfc_date else "",
                        "subject": rfc_subject.group(1).strip() if rfc_subject else "",
                        "body": body,
                    }]
                else:
                    # Treat raw text string as a single email body
                    data = [{"body": raw_input}]

        if isinstance(data, dict):
            # Check for container format {"messages": [...]} or {"threads": [...]}
            if "messages" in data and isinstance(data["messages"], list):
                raw_emails = data["messages"]
            else:
                raw_emails = [data]
        elif isinstance(data, list):
            raw_emails = data
        else:
            raw_emails = []

        filename = kwargs.get("filename", "")
        messages: list[SourceMessage] = []

        for idx, email in enumerate(raw_emails):
            if not isinstance(email, dict):
                continue
            email_id = str(email.get("id") or email.get("messageId") or f"gmail_{idx + 1}")
            sender = str(email.get("sender") or email.get("from") or "Unknown Sender").strip()
            timestamp = str(email.get("timestamp") or email.get("date") or "").strip()
            subject = str(email.get("subject") or "").strip()
            body = str(email.get("body") or email.get("text") or email.get("snippet") or "").strip()

            # Compose source text with subject header if present
            if subject and not body.startswith(subject):
                combined_text = f"Subject: {subject}\n\n{body}"
            else:
                combined_text = body or subject

            if not combined_text.strip():
                continue

            meta = {
                "subject": subject,
                "threadId": email.get("threadId"),
                "labels": email.get("labels", []),
            }

            messages.append(
                SourceMessage(
                    source_type="gmail",
                    source_id=email_id,
                    source_sender=sender,
                    source_timestamp=timestamp,
                    source_text=combined_text,
                    source_filename=filename,
                    source_metadata=meta,
                    message_id=len(messages) + 1,
                )
            )
        return messages


class GoogleClassroomAdapter(SourceAdapter):
    """Adapter for Google Classroom announcements and coursework.

    Accepts:
    - A list of announcement/coursework dicts, OR a single dict, OR JSON string.
    Supported fields:
    - id: classroom item ID
    - courseId: course identifier
    - text / description / title: announcement or assignment text
    - creatorUserId / teacherName: author
    - updateTime / creationTime / timestamp: date string
    - materials / alternateLink: optional course metadata
    """

    @property
    def source_type(self) -> str:
        return "google_classroom"

    def parse(self, raw_input: Any, **kwargs: Any) -> list[SourceMessage]:
        data = raw_input
        if isinstance(raw_input, str):
            try:
                data = json.loads(raw_input)
            except Exception:
                data = [{"text": raw_input}]

        default_item_type = None
        if isinstance(data, dict):
            if "announcements" in data and isinstance(data["announcements"], list):
                raw_items = data["announcements"]
                default_item_type = "announcement"
            elif "courseWork" in data and isinstance(data["courseWork"], list):
                raw_items = data["courseWork"]
                default_item_type = "coursework"
            else:
                raw_items = [data]
        elif isinstance(data, list):
            raw_items = data
        else:
            raw_items = []

        filename = kwargs.get("filename", "")
        messages: list[SourceMessage] = []

        for idx, item in enumerate(raw_items):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or f"gc_{idx + 1}")
            course_id = str(item.get("courseId") or "")
            sender = str(item.get("teacherName") or item.get("creatorUserId") or "Classroom Instructor").strip()
            timestamp = str(item.get("updateTime") or item.get("creationTime") or item.get("timestamp") or "").strip()

            title = str(item.get("title") or "").strip()
            text_body = str(item.get("text") or item.get("description") or "").strip()

            if title and text_body and not text_body.startswith(title):
                combined_text = f"{title}\n\n{text_body}"
            else:
                combined_text = text_body or title

            if not combined_text.strip():
                continue

            item_type = item.get("item_type")
            if not item_type:
                if default_item_type:
                    item_type = default_item_type
                elif "dueDate" in item or "cw" in item_id.lower() or "coursework" in item_id.lower():
                    item_type = "coursework"
                else:
                    item_type = "coursework" if (title and any(k in title.lower() for k in ("assignment", "problem set", "lab", "quiz", "homework", "project"))) else "announcement"

            meta = {
                "courseId": course_id,
                "alternateLink": item.get("alternateLink"),
                "state": item.get("state"),
                "item_type": item_type,
            }

            messages.append(
                SourceMessage(
                    source_type="google_classroom",
                    source_id=f"{course_id}_{item_id}" if course_id else item_id,
                    source_sender=sender,
                    source_timestamp=timestamp,
                    source_text=combined_text,
                    source_filename=filename,
                    source_metadata=meta,
                    message_id=len(messages) + 1,
                )
            )
        return messages


class ManualAdapter(SourceAdapter):
    """Adapter for manual task/announcement entry."""

    @property
    def source_type(self) -> str:
        return "manual"

    def parse(self, raw_input: Any, **kwargs: Any) -> list[SourceMessage]:
        if isinstance(raw_input, dict):
            text = str(raw_input.get("text") or raw_input.get("source_text") or "").strip()
            sender = str(raw_input.get("sender") or raw_input.get("source_sender") or "Manual Entry").strip()
            timestamp = str(raw_input.get("timestamp") or raw_input.get("source_timestamp") or "").strip()
            source_id = raw_input.get("source_id")
        else:
            text = str(raw_input or "").strip()
            sender = kwargs.get("sender", "Manual Entry").strip()
            timestamp = kwargs.get("timestamp", "").strip()
            source_id = kwargs.get("source_id")

        if not timestamp:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        if not source_id:
            source_id = f"manual_{int(datetime.now(timezone.utc).timestamp())}"

        if not text:
            return []

        return [
            SourceMessage(
                source_type="manual",
                source_id=str(source_id),
                source_sender=sender or "Manual Entry",
                source_timestamp=timestamp,
                source_text=text,
                source_filename=kwargs.get("filename", ""),
                source_metadata=kwargs.get("metadata", {}),
                message_id=1,
            )
        ]


_ADAPTER_REGISTRY: dict[str, SourceAdapter] = {
    "whatsapp": WhatsAppAdapter(),
    "gmail": GmailAdapter(),
    "google_classroom": GoogleClassroomAdapter(),
    "manual": ManualAdapter(),
}


def get_source_adapter(source_type: str) -> SourceAdapter:
    """Retrieve the registered adapter for a given source_type."""
    clean = (source_type or "").strip().lower()
    adapter = _ADAPTER_REGISTRY.get(clean)
    if not adapter:
        raise ValueError(
            f"Unsupported source_type '{source_type}'. "
            f"Supported sources: {', '.join(sorted(_ADAPTER_REGISTRY.keys()))}"
        )
    return adapter


def register_source_adapter(adapter: SourceAdapter) -> None:
    """Register or override a SourceAdapter implementation."""
    _ADAPTER_REGISTRY[adapter.source_type.lower()] = adapter

