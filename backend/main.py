"""FastAPI application for SMART (Academic Intelligence Dashboard).

Provides endpoints for health checks, chat parsing, candidate academic information
extraction from WhatsApp exports, SQLite persistence for academic tasks, and
RFC 5545 iCalendar export.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import os
from typing import Any, Optional

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from calendar_export import generate_ics
from database import (
    ALLOWED_CATEGORIES,
    ALLOWED_CONFIDENCE_LEVELS,
    ALLOWED_IMPORTANCE_LEVELS,
    ALLOWED_SOURCE_TYPES,
    ALLOWED_STATUSES,
    create_user_session,
    delete_academic_item,
    delete_google_account,
    delete_user_session,
    find_associated_task,
    find_duplicate_item,
    get_academic_item_by_id,
    get_confirmed_deadline_items,
    get_google_account,
    get_session_with_user,
    get_task_relationships,
    get_teacher_coursework_overview,
    get_teacher_opportunities_overview,
    get_user_by_email,
    get_user_by_id,
    init_db,
    is_valid_iso_date,
    list_academic_items,
    list_classroom_courses,
    list_classroom_coursework,
    list_classroom_submissions,
    list_opportunities,
    list_study_materials,
    save_academic_item,
    save_academic_item_with_association,
    save_opportunity,
    save_study_material,
    update_academic_item,
    update_academic_item_status,
    update_student_opportunity_status,
)
from extractor import create_candidate_token, extract_academic_items, verify_candidate_token
from google_service import (
    build_authorization_url,
    exchange_code_for_tokens,
    ingest_demo_data,
    is_live_google_configured,
    sync_live_classroom,
    sync_live_gmail,
)
from parser import parse_whatsapp_text
from security import (
    generate_csrf_token,
    generate_session_id,
    sanitize_account_for_response,
)
from source_adapters import get_source_adapter

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB upload limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Safely initialize database schema on application startup."""
    init_db()
    yield


# Initialize schema safely on import
init_db()

app = FastAPI(
    title="SMART API",
    description="Academic Intelligence Dashboard backend for parsing, extracting, persisting, and exporting academic items from chat exports.",
    version="0.2.0",
    lifespan=lifespan,
)


# Allow local development frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AcademicItemCreate(BaseModel):
    """Pydantic model validating candidate item save requests.

    confidence and confidence_reasons are system-generated fields.
    Client-supplied values are silently ignored; manually created tasks receive
    UNASSESSED confidence to distinguish them from pipeline-extracted candidates.

    evidence_text, when provided, must be a substring of source_text. The backend
    extraction pipeline uses _trusted_evidence to bypass this check safely.
    """

    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., min_length=1)
    category: str
    description: Optional[str] = None
    date_text: Optional[str] = None
    due_date: Optional[str] = None
    date_type: Optional[str] = None
    date_status: Optional[str] = None
    status: Optional[str] = "pending"
    source_sender: Optional[str] = None
    source_timestamp: Optional[str] = None
    source_text: str = Field(..., min_length=1)
    source_filename: Optional[str] = None
    source_type: Optional[str] = "whatsapp"
    source_id: Optional[str] = None
    source_metadata: Optional[dict[str, Any]] = None
    # Extraction candidate provenance token (HMAC-signed by extraction pipeline).
    candidate_token: Optional[str] = None
    # evidence_text is accepted from clients but validated as a substring of source_text.
    # Arbitrary fabricated evidence is rejected by save_academic_item.
    evidence_text: Optional[str] = None
    evidence_start_index: Optional[int] = None
    evidence_end_index: Optional[int] = None
    # NOTE: confidence and confidence_reasons are intentionally excluded from this schema.
    # Client-supplied confidence assertions are not trusted. The persistence layer assigns
    # UNASSESSED to all manually created items. Only the extraction pipeline may supply
    # a calculated confidence score via _trusted_confidence.
    review_required: Optional[bool] = False
    review_reasons: Optional[list[str]] = None
    is_actionable: Optional[bool] = None
    actionability_type: Optional[str] = None
    update_type: Optional[str] = None
    is_range: Optional[bool] = None
    previous_due_date: Optional[str] = None
    replaces_task_id: Optional[int] = None
    importance: Optional[str] = "UNASSESSED"
    academic_intent: Optional[str] = None


class AcademicItemUpdate(BaseModel):
    """Pydantic model validating partial updates to an academic item.

    confidence and confidence_reasons are system-generated immutable fields.
    They are intentionally excluded from this schema; any PATCH request supplying
    them will be rejected with HTTP 422 (extra_forbidden).
    """

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    date_text: Optional[str] = None
    due_date: Optional[str] = None
    date_type: Optional[str] = None
    date_status: Optional[str] = None
    status: Optional[str] = None
    review_required: Optional[bool] = None
    review_reasons: Optional[list[str]] = None
    is_actionable: Optional[bool] = None
    actionability_type: Optional[str] = None
    update_type: Optional[str] = None
    is_range: Optional[bool] = None
    previous_due_date: Optional[str] = None
    replaces_task_id: Optional[int] = None
    importance: Optional[str] = None
    academic_intent: Optional[str] = None
    # confidence and confidence_reasons are deliberately absent — they are immutable.

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            raise ValueError("Item title cannot be null.")
        clean = v.strip()
        if not clean:
            raise ValueError("Item title cannot be empty.")
        return clean

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            raise ValueError("Item category cannot be null.")
        clean = v.strip()
        if clean not in ALLOWED_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Allowed categories: {', '.join(sorted(ALLOWED_CATEGORIES))}"
            )
        return clean

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        if not is_valid_iso_date(clean):
            raise ValueError(
                f"Invalid due_date format '{v}'. Expected YYYY-MM-DD."
            )
        return clean

    @field_validator("importance")
    @classmethod
    def validate_importance(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip().upper()
        if clean not in ALLOWED_IMPORTANCE_LEVELS:
            raise ValueError(
                f"Invalid importance '{v}'. Allowed levels: {', '.join(sorted(ALLOWED_IMPORTANCE_LEVELS))}"
            )
        return clean


# Backward compatibility alias
AcademicItemStatusUpdate = AcademicItemUpdate


@app.get("/api/health")
def health_check():
    """Health check endpoint to verify backend service status."""
    return {
        "status": "healthy",
        "project": "SMART",
        "version": "0.2.0",
        "message": "SMART backend is running",
    }


async def _read_and_validate_file(file: UploadFile) -> str:
    """Validate uploaded file type, size, encoding, and non-emptiness.

    Returns the decoded UTF-8 string.
    """
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a WhatsApp .txt export.",
        )

    # Read up to MAX_FILE_SIZE + 1 bytes to detect oversized files
    content = await file.read(MAX_FILE_SIZE + 1)

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File is too large. Maximum size is 5 MB.",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    try:
        raw_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Could not decode this file as UTF-8 text.",
        )

    if not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    return raw_text


@app.post("/api/upload-chat")
async def upload_chat(file: UploadFile = File(...)):
    """Parse a WhatsApp .txt export and return structured messages."""
    raw_text = await _read_and_validate_file(file)
    messages = parse_whatsapp_text(raw_text)

    if not messages:
        raise HTTPException(
            status_code=422,
            detail="No recognised WhatsApp messages were found. Please check that the export matches supported WhatsApp formats.",
        )

    return {
        "filename": file.filename,
        "total_messages": len(messages),
        "messages": messages,
    }


@app.post("/api/extract-academic")
async def extract_academic(file: UploadFile = File(...)):
    """Parse a WhatsApp export and extract candidate academic items."""
    raw_text = await _read_and_validate_file(file)
    messages = parse_whatsapp_text(raw_text)

    if not messages:
        raise HTTPException(
            status_code=422,
            detail="No recognised WhatsApp messages were found. Please check that the export matches supported WhatsApp formats.",
        )

    items = extract_academic_items(messages)

    category_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNASSESSED": 0}
    review_count = 0
    for item in items:
        cat = item.get("category", "Uncategorized")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        conf = item.get("confidence", "UNASSESSED")
        confidence_counts[conf] = confidence_counts.get(conf, 0) + 1
        if item.get("review_required"):
            review_count += 1

    return {
        "filename": file.filename,
        "total_messages": len(messages),
        "total_items": len(items),
        "review_required_count": review_count,
        "category_counts": category_counts,
        "confidence_counts": confidence_counts,
        "items": items,
    }


class AcademicSourceExtractRequest(BaseModel):
    """Payload for multi-source academic item extraction."""

    source_type: str = "whatsapp"
    raw_text: Optional[str] = None
    payload: Optional[Any] = None
    filename: Optional[str] = None
    sender: Optional[str] = None
    timestamp: Optional[str] = None


@app.post("/api/extract-academic-source")
def extract_academic_source(req: AcademicSourceExtractRequest) -> dict[str, Any]:
    """Extract candidate academic items from any supported source adapter.

    Supports WhatsApp exports, Gmail payloads/texts, Google Classroom coursework/announcements,
    and Manual text entry via the adapter layer.
    """
    clean_type = (req.source_type or "whatsapp").strip().lower()
    if clean_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_type '{req.source_type}'. Allowed types: {', '.join(sorted(ALLOWED_SOURCE_TYPES))}",
        )

    try:
        adapter = get_source_adapter(clean_type)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    source_input = req.payload if req.payload is not None else req.raw_text
    if source_input is None or (isinstance(source_input, str) and not source_input.strip()):
        raise HTTPException(status_code=400, detail="Missing raw_text or payload to analyze.")

    adapter_kwargs: dict[str, Any] = {}
    if req.filename:
        adapter_kwargs["filename"] = req.filename
    if req.sender:
        adapter_kwargs["sender"] = req.sender
    if req.timestamp:
        adapter_kwargs["timestamp"] = req.timestamp

    try:
        source_messages = adapter.parse(source_input, **adapter_kwargs)
    except Exception as err:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse source messages: {err}",
        )

    if not source_messages:
        raise HTTPException(
            status_code=422,
            detail=f"No messages could be parsed from the provided {clean_type} source.",
        )

    message_dicts = [msg.to_dict() for msg in source_messages]
    items = extract_academic_items(message_dicts)

    category_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNASSESSED": 0}
    review_count = 0
    for item in items:
        cat = item.get("category", "Uncategorized")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        conf = item.get("confidence", "UNASSESSED")
        confidence_counts[conf] = confidence_counts.get(conf, 0) + 1
        if item.get("review_required"):
            review_count += 1

    return {
        "source_type": clean_type,
        "filename": req.filename or f"source_{clean_type}",
        "total_messages": len(source_messages),
        "total_items": len(items),
        "review_required_count": review_count,
        "category_counts": category_counts,
        "confidence_counts": confidence_counts,
        "items": items,
    }


# ==============================================================================
# Phase 2 Endpoints: Persistence & Academic Task Management
# ==============================================================================


def _build_trusted_extraction_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    """Convert an extraction pipeline candidate into a trusted save payload.

    Injects the _trusted_confidence and _trusted_evidence sentinel keys so that
    save_academic_item() persists the pipeline-calculated confidence without
    treating it as a client-supplied (and therefore untrusted) value.

    This is the ONLY internal path that should write system-generated confidence
    into the database; all other callers receive UNASSESSED.
    """
    payload = dict(candidate)
    # Move pipeline confidence to trusted sentinel keys
    payload["_trusted_confidence"] = candidate.get("confidence", "UNASSESSED")
    payload["_trusted_confidence_reasons"] = candidate.get("confidence_reasons") or []
    payload["is_actionable"] = candidate.get("is_actionable", True)
    payload["actionability_type"] = candidate.get("actionability_type", "action_required")
    payload["update_type"] = candidate.get("update_type")
    # Mark evidence as pipeline-sourced (bypasses substring validation since
    # extract_academic_items guarantees evidence_text is derived from source_text)
    payload["_trusted_evidence"] = True
    return payload


@app.post("/api/academic-items", status_code=status.HTTP_201_CREATED)
def create_academic_item(item: AcademicItemCreate) -> dict[str, Any]:
    """Validate and persist an extracted candidate academic item.

    Deduplicates based on source provenance to avoid accidental re-saves.
    """
    payload = item.model_dump()
    trusted_category = None

    # Provenance Integrity Enforcement (Phase 3.3.1 / Phase 3.3.2):
    if item.candidate_token:
        token_data = verify_candidate_token(item.candidate_token)
        if not token_data:
            raise HTTPException(
                status_code=400,
                detail="Invalid or tampered candidate token.",
            )
        if token_data.get("source_text") != item.source_text:
            raise HTTPException(
                status_code=400,
                detail="Candidate token does not match item source text.",
            )

        # Enforce pipeline-certified metadata from signed token,
        # authoritatively overriding any client-supplied parameters.
        payload["_trusted_confidence"] = token_data.get("confidence", "UNASSESSED")
        payload["_trusted_confidence_reasons"] = token_data.get("confidence_reasons") or []
        payload["_trusted_evidence"] = True
        payload["evidence_text"] = token_data.get("evidence_text")
        payload["evidence_start_index"] = token_data.get("evidence_start_index")
        payload["evidence_end_index"] = token_data.get("evidence_end_index")
        if "is_actionable" in token_data:
            payload["is_actionable"] = token_data["is_actionable"]
        else:
            eff_cat = token_data.get("category") or item.category
            payload["is_actionable"] = False if eff_cat == "Announcement" else True

        if "actionability_type" in token_data:
            payload["actionability_type"] = token_data["actionability_type"]
        else:
            eff_cat = token_data.get("category") or item.category
            payload["actionability_type"] = "informational" if eff_cat == "Announcement" else "action_required"

        if "update_type" in token_data:
            payload["update_type"] = token_data["update_type"]
        else:
            payload["update_type"] = None

        if "due_date" in token_data:
            payload["due_date"] = token_data["due_date"]

        if "date_status" in token_data:
            payload["date_status"] = token_data["date_status"]

        if "date_text" in token_data:
            payload["date_text"] = token_data["date_text"]

        if "date_type" in token_data:
            payload["date_type"] = token_data["date_type"]

        if "is_range" in token_data:
            payload["is_range"] = bool(token_data["is_range"])

        if "previous_due_date" in token_data:
            payload["previous_due_date"] = token_data["previous_due_date"]

        if "importance" in token_data:
            payload["importance"] = token_data["importance"]

        if "academic_intent" in token_data:
            payload["academic_intent"] = token_data["academic_intent"]

        if "source_type" in token_data:
            payload["source_type"] = token_data["source_type"]

        if "source_id" in token_data:
            payload["source_id"] = token_data["source_id"]

        if "source_metadata" in token_data:
            payload["source_metadata"] = token_data["source_metadata"]

        if token_data.get("category"):
            trusted_category = token_data["category"]
            payload["category"] = trusted_category
    else:
        # Offsets without a valid extraction candidate token represent fabricated provenance
        if item.evidence_start_index is not None or item.evidence_end_index is not None:
            raise HTTPException(
                status_code=400,
                detail="Evidence occurrence offsets cannot be provided without a valid extraction candidate token.",
            )
        # Manual task creation without token: confidence is UNASSESSED, offsets are None
        if item.source_type in ("gmail", "google_classroom"):
            raise HTTPException(
                status_code=400,
                detail=f"External source provenance '{item.source_type}' requires a pipeline-certified candidate token.",
            )
        payload["_trusted_confidence"] = "UNASSESSED"
        payload["_trusted_confidence_reasons"] = []
        payload["evidence_start_index"] = None
        payload["evidence_end_index"] = None
        payload["is_range"] = bool(item.is_range) if item.is_range is not None else False
        payload["previous_due_date"] = item.previous_due_date
        payload["replaces_task_id"] = item.replaces_task_id
        payload["importance"] = item.importance or "UNASSESSED"
        payload["academic_intent"] = item.academic_intent
        payload["source_type"] = item.source_type or "whatsapp"
        payload["source_id"] = item.source_id
        payload["source_metadata"] = item.source_metadata if isinstance(item.source_metadata, dict) else {}
        if item.is_actionable is None:
            payload["is_actionable"] = False if item.category == "Announcement" else True
        if item.actionability_type is None:
            payload["actionability_type"] = "informational" if item.category == "Announcement" else "action_required"

    effective_cat = trusted_category or item.category
    clean_cat = effective_cat.strip()
    if clean_cat not in ALLOWED_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{clean_cat}'. Allowed categories: {', '.join(sorted(ALLOWED_CATEGORIES))}",
        )

    # Deadline modification & task association handling
    eff_update_type = payload.get("update_type")
    target_id = None
    target_old_reasons: list[str] = []

    if eff_update_type in (
        "extension",
        "postponement",
        "rescheduled",
        "revision",
        "replacement",
        "cancellation",
        "window_change",
    ):
        associated = find_associated_task(payload)
        candidate_target_id = item.replaces_task_id or (associated["id"] if associated else None)
        if candidate_target_id:
            # Server-side validation of target_id
            target_task = get_academic_item_by_id(candidate_target_id)
            if target_task:
                target_id = candidate_target_id
                target_old_reasons = target_task.get("review_reasons") or []
            else:
                payload["review_required"] = True
                curr_reasons = payload.get("review_reasons") or []
                if isinstance(curr_reasons, str):
                    try:
                        curr_reasons = json.loads(curr_reasons)
                    except Exception:
                        curr_reasons = [curr_reasons]
                notif_msg = f"Target replaces_task_id #{candidate_target_id} not found in database; association cleared for safety."
                if notif_msg not in curr_reasons:
                    curr_reasons.append(notif_msg)
                payload["review_reasons"] = curr_reasons

        if target_id:
            payload["replaces_task_id"] = target_id
            if eff_update_type == "cancellation":
                c_reason = "Deadline cancelled by subsequent announcement."
                if c_reason not in target_old_reasons:
                    target_old_reasons.append(c_reason)
                payload["status"] = "cancelled"
            else:
                if not payload.get("previous_due_date") and associated:
                    payload["previous_due_date"] = associated.get("due_date")
                if payload.get("status") in (None, "pending"):
                    payload["status"] = "pending"
        else:
            payload["review_required"] = True
            curr_reasons = payload.get("review_reasons") or []
            if isinstance(curr_reasons, str):
                try:
                    curr_reasons = json.loads(curr_reasons)
                except Exception:
                    curr_reasons = [curr_reasons]
            notif_msg = "Update announcement detected without a confirmed existing task association; requires human review."
            if notif_msg not in curr_reasons:
                curr_reasons.append(notif_msg)
            payload["review_reasons"] = curr_reasons
            if eff_update_type == "cancellation":
                payload["status"] = "cancelled"
    elif payload.get("replaces_task_id"):
        # Server-side check for standalone client-supplied replaces_task_id
        target_task = get_academic_item_by_id(payload["replaces_task_id"])
        if not target_task:
            payload["replaces_task_id"] = None
            payload["review_required"] = True
            curr_reasons = payload.get("review_reasons") or []
            if isinstance(curr_reasons, str):
                try:
                    curr_reasons = json.loads(curr_reasons)
                except Exception:
                    curr_reasons = [curr_reasons]
            notif_msg = f"Target replaces_task_id #{item.replaces_task_id} not found in database; association cleared for safety."
            if notif_msg not in curr_reasons:
                curr_reasons.append(notif_msg)
            payload["review_reasons"] = curr_reasons

    clean_status = (payload.get("status") or item.status or "pending").strip().lower()
    if clean_status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{clean_status}'. Allowed statuses: {', '.join(sorted(ALLOWED_STATUSES))}",
        )
    payload["status"] = clean_status

    # Deduplication check FIRST (before performing any database mutations or associations)
    existing = find_duplicate_item(
        source_text=item.source_text,
        source_timestamp=item.source_timestamp,
        source_sender=item.source_sender,
        category=clean_cat,
        source_filename=item.source_filename,
        source_type=payload.get("source_type") or "whatsapp",
        source_id=payload.get("source_id"),
        title=payload.get("title") or item.title,
        evidence_text=payload.get("evidence_text"),
        evidence_start_index=payload.get("evidence_start_index"),
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Academic item has already been saved (Task #{existing['id']}).",
        )

    try:
        if target_id:
            # Atomically update target status and insert new task in one transaction
            saved = save_academic_item_with_association(
                data=payload,
                target_id=target_id,
                target_status="cancelled" if eff_update_type == "cancellation" else "superseded",
                target_review_required=True if eff_update_type == "cancellation" else None,
                target_review_reasons=target_old_reasons if eff_update_type == "cancellation" else None,
            )
        else:
            saved = save_academic_item(payload)
        return saved
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to persist academic item: {err}",
        )


@app.get("/api/academic-items")
def get_academic_items(
    category: Optional[str] = Query(None, description="Filter by category"),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status"
    ),
    search: Optional[str] = Query(
        None, description="Search in title or description or original message"
    ),
    due_before: Optional[str] = Query(
        None, description="Filter items due on or before date (YYYY-MM-DD)"
    ),
    due_after: Optional[str] = Query(
        None, description="Filter items due on or after date (YYYY-MM-DD)"
    ),
    confidence: Optional[str] = Query(
        None, description="Filter items by confidence level ('HIGH', 'MEDIUM', 'LOW', 'UNASSESSED')"
    ),
    priority: Optional[str] = Query(
        None, description="Filter items by priority level ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')"
    ),
    importance: Optional[str] = Query(
        None, description="Filter items by importance level ('HIGH', 'MEDIUM', 'LOW', 'UNASSESSED')"
    ),
    urgency: Optional[str] = Query(
        None, description="Filter items by urgency level ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NO_DEADLINE', 'NEEDS_REVIEW')"
    ),
    academic_intent: Optional[str] = Query(
        None, description="Filter items by academic intent"
    ),
    source_type: Optional[str] = Query(
        None, description="Filter items by source type ('whatsapp', 'gmail', 'google_classroom', 'manual')"
    ),
) -> list[dict[str, Any]]:
    """List and filter saved academic items with deterministic ordering and prioritization."""
    try:
        items = list_academic_items(
            category=category,
            status=status_filter,
            search=search,
            due_before=due_before,
            due_after=due_after,
            confidence=confidence,
            priority=priority,
            importance=importance,
            urgency=urgency,
            academic_intent=academic_intent,
            source_type=source_type,
        )
        return items
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query academic items: {err}",
        )


def _export_ics_response() -> Response:
    """Helper generating .ics response for confirmed deadlines."""
    items = get_confirmed_deadline_items()
    if not items:
        raise HTTPException(
            status_code=404,
            detail="No confirmed deadlines available to export.",
        )

    ics_content = generate_ics(items)
    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="smart_academic_deadlines.ics"'
        },
    )


@app.get("/api/academic-items/export-ics")
def export_deadlines_ics() -> Response:
    """Export all confirmed academic deadlines as an RFC 5545 .ics calendar."""
    return _export_ics_response()


@app.get("/api/academic-items/export.ics")
def export_deadlines_ics_alias() -> Response:
    """Alias endpoint for direct .ics download."""
    return _export_ics_response()


@app.get("/api/academic-items/{item_id}")
def get_single_academic_item(item_id: int) -> dict[str, Any]:
    """Retrieve a single academic item by ID with full relationship lineage."""
    item = get_academic_item_by_id(item_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"Academic item with ID {item_id} not found.",
        )
    item["relationships"] = get_task_relationships(item_id)
    return item


@app.get("/api/academic-items/{item_id}/relationships")
def get_task_relationships_endpoint(item_id: int) -> dict[str, Any]:
    """Retrieve relationship hierarchy and revision lineage for an academic task."""
    item = get_academic_item_by_id(item_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"Academic item with ID {item_id} not found.",
        )
    return get_task_relationships(item_id)


@app.patch("/api/academic-items/{item_id}")
def update_task_item(
    item_id: int, update: AcademicItemUpdate
) -> dict[str, Any]:
    """Partially update an academic item's editable fields or status."""
    # Check if empty payload was sent
    if not update.model_fields_set:
        item = get_academic_item_by_id(item_id)
        if not item:
            raise HTTPException(
                status_code=404,
                detail=f"Academic item with ID {item_id} not found.",
            )
        return item

    # Backward compatibility: preserve existing 400 Bad Request behavior for invalid status
    if "status" in update.model_fields_set:
        if update.status is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid status. Status cannot be null.",
            )
        clean_status = update.status.strip().lower()
        if clean_status not in ALLOWED_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{update.status}'. Allowed statuses: {', '.join(sorted(ALLOWED_STATUSES))}",
            )

    payload = update.model_dump(exclude_unset=True)

    try:
        updated = update_academic_item(item_id, payload)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to update academic item.",
        )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Academic item with ID {item_id} not found.",
        )
    return updated


# Backward compatibility function alias
update_task_status = update_task_item


@app.delete("/api/academic-items/{item_id}")
def delete_task_item(item_id: int) -> dict[str, Any]:
    """Delete a saved academic item record."""
    deleted = delete_academic_item(item_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Academic item with ID {item_id} not found.",
        )
    return {
        "message": f"Academic item with ID {item_id} deleted successfully.",
        "id": item_id,
    }


# ==============================================================================
# SMART 2.1 — Authentication, Google Sync, Opportunities & Classroom Endpoints
# ==============================================================================

SESSION_COOKIE_NAME = "smart_session"
SESSION_DURATION_HOURS = 24
SMART_ENV = os.environ.get("SMART_ENV", "development").strip().lower()
IS_PRODUCTION = SMART_ENV == "production"


class LoginRequest(BaseModel):
    """Payload for user login / demo sign-in."""
    email: str


def get_current_user_optional(
    smart_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> Optional[dict[str, Any]]:
    """Retrieve current authenticated user from session cookie.

    Falls back to provisioned user record matching legacy header only if no cookie
    is present and the target user is active & provisioned (for test backward compatibility).
    """
    if smart_session:
        session_data = get_session_with_user(smart_session)
        if session_data:
            return session_data

    # Controlled legacy fallback for test harnesses without cookies
    if x_user_email and not IS_PRODUCTION:
        user = get_user_by_email(x_user_email)
        if user and user.get("status") == "active":
            return user
        # Synthetic temporary profile if header specifies role
        role = (x_user_role or "student").strip().lower()
        if role in ("student", "teacher"):
            return {
                "id": None,
                "email": x_user_email.strip().lower(),
                "name": x_user_email.split("@")[0].capitalize(),
                "role": role,
                "status": "active",
                "is_demo": 1,
            }

    return None


def get_current_user(user: Optional[dict[str, Any]] = Depends(get_current_user_optional)) -> dict[str, Any]:
    """Require an authenticated provisioned user."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in to access your SMART workspace.",
        )
    return user


def require_role(required_role: str):
    """Factory dependency to enforce server-side user role."""
    def _role_checker(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        role = user.get("role")
        if role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: {required_role.capitalize()} role is required for this action.",
            )
        return user
    return _role_checker


@app.post("/api/auth/login")
def login_user(payload: LoginRequest, response: Response) -> dict[str, Any]:
    """Authenticate a provisioned user account or demo identity and create server session."""
    email = payload.email.strip().lower()
    user = get_user_by_email(email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account not provisioned: '{email}' has not been assigned a SMART role. Contact your administrator.",
        )

    # In production, disable demo accounts
    if IS_PRODUCTION and user.get("is_demo"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo authentication identities are disabled in production environments.",
        )

    if user.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended or deactivated. Contact your institution administrator.",
        )

    session_id = generate_session_id()
    csrf_token = generate_csrf_token()
    expires_dt = datetime.now(timezone.utc) + timedelta(hours=SESSION_DURATION_HOURS)
    expires_iso = expires_dt.isoformat()

    create_user_session(
        user_id=user["id"],
        session_id=session_id,
        csrf_token=csrf_token,
        expires_at_iso=expires_iso,
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=IS_PRODUCTION,  # Secure cookie automatically enabled in production HTTPS
        max_age=SESSION_DURATION_HOURS * 3600,
        path="/",
    )

    return {
        "status": "authenticated",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "is_demo": bool(user["is_demo"]),
            "department": user.get("department"),
            "program": user.get("program"),
        },
        "csrf_token": csrf_token,
    }


@app.get("/api/auth/me")
def get_current_user_profile(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Return profile for the currently authenticated user session."""
    return {
        "authenticated": True,
        "user": {
            "id": user.get("user_id") or user.get("id"),
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "is_demo": bool(user.get("is_demo")),
            "department": user.get("department"),
            "program": user.get("program"),
        },
        "csrf_token": user.get("csrf_token"),
    }


@app.post("/api/auth/logout")
def logout_user(
    response: Response,
    smart_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Invalidate authenticated session and clear HttpOnly cookie."""
    if smart_session:
        delete_user_session(smart_session)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"status": "logged_out", "message": "Session terminated successfully."}


class OpportunityStatusUpdateRequest(BaseModel):
    """Payload for student competition status updates."""
    status: str
    evidence_notes: Optional[str] = ""
    confirmation_source_ref: Optional[str] = ""


class OpportunityCreateRequest(BaseModel):
    """Payload for creating a competition opportunity."""
    name: str
    organizer: Optional[str] = None
    description: Optional[str] = None
    eligibility: Optional[str] = None
    registration_deadline: Optional[str] = None
    event_date: Optional[str] = None
    registration_url: Optional[str] = None
    confidence: Optional[str] = "HIGH"
    review_status: Optional[str] = "confirmed"


class StudyMaterialCreateRequest(BaseModel):
    """Payload for creating a study material reference."""
    title: str
    file_name: str
    file_type: Optional[str] = "application/pdf"
    file_size: Optional[int] = 0
    file_url: Optional[str] = None
    source_type: Optional[str] = "manual"
    course_id: Optional[str] = None
    course_name: Optional[str] = None


class DemoToggleRequest(BaseModel):
    """Payload for enabling or resetting demo sample data."""
    enable: bool = True
    student_email: Optional[str] = "student.demo@univ.edu"


@app.get("/api/auth/google/url")
def get_google_auth_url(
    role: str = Query("student", description="Requested demonstration role ('student' or 'teacher')"),
    redirect_uri: Optional[str] = Query(None, description="Custom OAuth redirect URI"),
) -> dict[str, Any]:
    """Generate a CSRF-protected Google OAuth 2.0 authorization URL."""
    clean_role = (role or "student").strip().lower()
    if clean_role not in ("student", "teacher"):
        clean_role = "student"
    return build_authorization_url(role=clean_role, redirect_uri=redirect_uri)


@app.get("/api/auth/google/callback")
async def handle_google_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
) -> dict[str, Any]:
    """Handle Google OAuth 2.0 redirect callback, validate CSRF state, and store tokens."""
    if error:
        raise HTTPException(
            status_code=400,
            detail=f"Google OAuth authorization was denied or failed: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=400,
            detail="Missing OAuth 'code' or 'state' query parameter in callback.",
        )

    try:
        account = await exchange_code_for_tokens(code=code, state=state)
        return {
            "status": "connected",
            "message": "Google account connected successfully.",
            "account": sanitize_account_for_response(account),
        }
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to complete Google OAuth exchange: {err}")


@app.get("/api/auth/google/status")
def get_google_auth_status(
    x_user_role: Optional[str] = Header("student", alias="X-User-Role"),
) -> dict[str, Any]:
    """Return current connected Google account status without exposing any tokens."""
    role = (x_user_role or "student").strip().lower()
    account = get_google_account(role=role)
    if not account:
        account = get_google_account()

    is_configured = is_live_google_configured()

    if not account:
        return {
            "connected": False,
            "live_configured": is_configured,
            "message": "No Google account connected.",
            "account": None,
        }

    return {
        "connected": True,
        "live_configured": is_configured,
        "account": sanitize_account_for_response(account),
    }


@app.post("/api/auth/google/disconnect")
def disconnect_google_account(
    email: Optional[str] = Query(None, description="Account email to disconnect"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> dict[str, Any]:
    """Disconnect Google account and delete stored encrypted tokens."""
    target_email = email or x_user_email
    if not target_email:
        acc = get_google_account()
        if acc:
            target_email = acc.get("email")

    if not target_email:
        return {"status": "no_account", "message": "No connected account found to disconnect."}

    deleted = delete_google_account(target_email)
    return {
        "status": "disconnected" if deleted else "not_found",
        "email": target_email,
        "message": "Google account disconnected and tokens securely removed.",
    }


@app.post("/api/auth/demo-toggle")
def toggle_demo_data(payload: DemoToggleRequest) -> dict[str, Any]:
    """Initialize or reset labeled demo data for offline testing and grading."""
    if payload.enable:
        res = ingest_demo_data(student_email=payload.student_email or "student.demo@univ.edu")
        return res
    return {"status": "disabled", "message": "Demo data initialization cleared."}


@app.post("/api/sync/gmail")
async def trigger_gmail_sync(
    max_messages: int = Query(15, ge=1, le=50),
    x_user_role: Optional[str] = Header("student", alias="X-User-Role"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> dict[str, Any]:
    """Manually trigger Gmail synchronization for authenticated user's account."""
    role = (x_user_role or "student").strip().lower()
    account = get_google_account(email=x_user_email, role=role)
    if not account:
        account = get_google_account()

    if not account:
        raise HTTPException(
            status_code=400,
            detail="No connected Google account found. Please connect your Google account or enable Demo mode.",
        )

    # If demo account or live credentials not configured, use demo sync
    if account.get("is_demo") or not is_live_google_configured():
        now_iso = datetime.now(timezone.utc).isoformat()
        account["last_sync_gmail"] = now_iso
        ingest_demo_data(student_email=account.get("email", "student.demo@univ.edu"))
        return {
            "status": "success",
            "is_demo": True,
            "message": "Synchronized Gmail messages in Demo Mode. (Clearly labeled demo sample data).",
            "synced_count": 3,
            "extracted_competitions": 3,
            "extracted_materials": 1,
            "last_sync": now_iso,
        }

    try:
        res = await sync_live_gmail(account, max_messages=max_messages)
        return {"status": "success", **res}
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Gmail sync failed: {err}")


@app.get("/api/opportunities")
def get_opportunities(
    status_filter: Optional[str] = Query(None, alias="status"),
    include_demo: bool = Query(True),
    current_user: Optional[dict[str, Any]] = Depends(get_current_user_optional),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> list[dict[str, Any]]:
    """List competition opportunities with student's current participation status."""
    user_email = (current_user.get("email") if current_user else None) or x_user_email
    acc = get_google_account(email=user_email)
    student_id = user_email or (acc.get("email") if acc else "student.demo@univ.edu")
    return list_opportunities(
        student_id=student_id,
        status_filter=status_filter,
        include_demo=include_demo,
    )


@app.post("/api/opportunities")
def create_opportunity(
    payload: OpportunityCreateRequest,
    current_user: Optional[dict[str, Any]] = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Manually create a new academic competition opportunity."""
    try:
        saved = save_opportunity(payload.model_dump())
        return saved
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.patch("/api/opportunities/{opportunity_id}/status")
def update_opportunity_status(
    opportunity_id: int,
    payload: OpportunityStatusUpdateRequest,
    current_user: Optional[dict[str, Any]] = Depends(get_current_user_optional),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> dict[str, Any]:
    """Update student's personal participation status for an opportunity."""
    user_email = (current_user.get("email") if current_user else None) or x_user_email
    acc = get_google_account(email=user_email)
    student_id = user_email or (acc.get("email") if acc else "student.demo@univ.edu")
    try:
        updated = update_student_opportunity_status(
            student_id=student_id,
            opportunity_id=opportunity_id,
            status=payload.status,
            evidence_notes=payload.evidence_notes or "",
            confirmation_ref=payload.confirmation_source_ref or "",
            updated_by=student_id,
        )
        return updated
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.get("/api/teacher/opportunities-overview")
def get_teacher_opportunities_summary(
    current_user: Optional[dict[str, Any]] = Depends(get_current_user_optional),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
) -> dict[str, Any]:
    """Authorized teacher overview of student opportunity engagement."""
    effective_role = (current_user.get("role") if current_user else None) or (x_user_role or "").strip().lower()
    if effective_role != "teacher":
        raise HTTPException(
            status_code=403,
            detail="Access forbidden: Teacher role is required to view student opportunity participation overview.",
        )
    return get_teacher_opportunities_overview()


@app.post("/api/sync/classroom")
async def trigger_classroom_sync(
    current_user: Optional[dict[str, Any]] = Depends(get_current_user_optional),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> dict[str, Any]:
    """Synchronize Google Classroom courses, coursework, and submissions."""
    role = (current_user.get("role") if current_user else None) or (x_user_role or "student").strip().lower()
    email = (current_user.get("email") if current_user else None) or x_user_email
    account = get_google_account(email=email, role=role)
    if not account:
        account = get_google_account()

    if not account:
        raise HTTPException(
            status_code=400,
            detail="No connected Google account found. Please connect your Google account or enable Demo mode.",
        )

    if account.get("is_demo") or not is_live_google_configured():
        now_iso = datetime.now(timezone.utc).isoformat()
        account["last_sync_classroom"] = now_iso
        ingest_demo_data(student_email=account.get("email", "student.demo@univ.edu"))
        return {
            "status": "success",
            "is_demo": True,
            "message": "Synchronized Google Classroom in Demo Mode (Clearly labeled demo sample data).",
            "courses_count": 3,
            "coursework_count": 3,
            "submissions_count": 4,
            "last_sync": now_iso,
        }

    try:
        res = await sync_live_classroom(account)
        return {"status": "success", **res}
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Classroom sync failed: {err}")


@app.get("/api/classroom/courses")
def get_classroom_courses(
    role: Optional[str] = Query(None),
    include_demo: bool = Query(True),
    current_user: Optional[dict[str, Any]] = Depends(get_current_user_optional),
) -> list[dict[str, Any]]:
    """List accessible courses."""
    user_role = role or (current_user.get("role") if current_user else None)
    return list_classroom_courses(role=user_role, include_demo=include_demo)


@app.get("/api/classroom/coursework")
def get_classroom_coursework(
    course_id: Optional[str] = Query(None),
    include_demo: bool = Query(True),
) -> list[dict[str, Any]]:
    """List coursework assignments across courses."""
    return list_classroom_coursework(course_id=course_id, include_demo=include_demo)


@app.get("/api/classroom/submissions")
def get_classroom_submissions(
    course_id: Optional[str] = Query(None),
    include_demo: bool = Query(True),
    current_user: Optional[dict[str, Any]] = Depends(get_current_user_optional),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> list[dict[str, Any]]:
    """List student coursework submissions. Students only see their own submissions."""
    role = (current_user.get("role") if current_user else None) or (x_user_role or "student").strip().lower()
    email = (current_user.get("email") if current_user else None) or x_user_email
    acc = get_google_account(email=email)
    student_id = email or (acc.get("email") if acc else "student.demo@univ.edu")

    # If student, strictly isolate submissions to student's own ID
    student_filter = student_id if role == "student" else None
    return list_classroom_submissions(
        course_id=course_id,
        student_id=student_filter,
        include_demo=include_demo,
    )


@app.get("/api/teacher/coursework-overview")
def get_teacher_courses_overview(
    current_user: Optional[dict[str, Any]] = Depends(get_current_user_optional),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> list[dict[str, Any]]:
    """Return course-level progress indicators for courses the teacher is authorized to manage."""
    role = (current_user.get("role") if current_user else None) or (x_user_role or "").strip().lower()
    if role != "teacher":
        raise HTTPException(
            status_code=403,
            detail="Access forbidden: Teacher role is required to view course progress overview.",
        )
    email = (current_user.get("email") if current_user else None) or x_user_email
    return get_teacher_coursework_overview(teacher_email=email)


@app.get("/api/materials")
def get_study_materials(
    course_id: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    include_demo: bool = Query(True),
) -> list[dict[str, Any]]:
    """List accessible study materials from Gmail attachments and Classroom resources."""
    return list_study_materials(
        course_id=course_id,
        source_type=source_type,
        include_demo=include_demo,
    )


@app.post("/api/materials")
def create_study_material(payload: StudyMaterialCreateRequest) -> dict[str, Any]:
    """Store study material reference."""
    try:
        saved = save_study_material(payload.model_dump())
        return saved
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
