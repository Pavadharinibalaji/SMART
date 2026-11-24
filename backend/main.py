"""FastAPI application for SMART (Academic Intelligence Dashboard).

Provides endpoints for health checks, chat parsing, candidate academic information
extraction from WhatsApp exports, SQLite persistence for academic tasks, and
RFC 5545 iCalendar export.
"""

from __future__ import annotations

import config  # Ensures root .env is loaded before accessing environment variables
from config import (
    get_cookie_settings,
    get_cors_origins,
    get_frontend_url,
    is_demo_login_allowed,
    is_institutional_email,
    is_production,
    validate_production_config,
)
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
from typing import Any, Optional
import urllib.parse
import uuid

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from calendar_export import generate_ics
from database import (
    ALLOWED_CATEGORIES,
    ALLOWED_CONFIDENCE_LEVELS,
    ALLOWED_IMPORTANCE_LEVELS,
    ALLOWED_SOURCE_TYPES,
    ALLOWED_STATUSES,
    accept_course_invitation,
    acknowledge_announcement,
    check_and_dispatch_opportunity_reminders,
    close_course_poll,
    create_course_announcement,
    create_course_invitation,
    create_course_poll,
    create_notification,
    create_smart_course,
    create_user_session,
    delete_academic_item,
    delete_course_material,
    delete_google_account,
    delete_tracked_opportunity,
    delete_user_session,
    enroll_student_by_join_code,
    find_associated_task,
    find_duplicate_item,
    get_academic_item_by_id,
    get_confirmed_deadline_items,
    get_course_enrolled_student_ids,
    get_course_engagement_analytics,
    get_course_material,
    get_course_opportunities_analytics,
    get_db_connection,
    get_google_account,
    get_poll_details,
    get_session_with_user,
    get_smart_course,
    get_smart_course_by_code,
    get_smart_course_by_join_code,
    get_student_personal_analytics,
    get_task_relationships,
    get_teacher_coursework_overview,
    get_teacher_opportunities_overview,
    get_tracked_opportunity,
    get_unread_message_count,
    get_unread_notification_count,
    get_user_by_email,
    get_user_by_id,
    grade_classroom_submission,
    init_db,
    is_user_course_teacher,
    is_user_enrolled,
    is_valid_iso_date,
    list_academic_items,
    list_classroom_courses,
    list_classroom_coursework,
    list_classroom_submissions,
    list_course_announcements,
    list_course_invitations,
    list_course_materials,
    list_course_members,
    list_course_messages,
    list_course_opportunity_participations,
    list_course_polls,
    list_opportunities,
    list_student_pending_invitations,
    list_student_tracked_opportunities,
    list_study_materials,
    list_user_notifications,
    list_user_smart_courses,
    mark_all_notifications_read,
    mark_messages_read,
    mark_notification_read,
    provision_user,
    regenerate_course_join_code,
    remove_student_from_course,
    save_academic_item,
    save_academic_item_with_association,
    save_course_material,
    save_course_message,
    save_opportunity,
    save_study_material,
    save_tracked_opportunity,
    submit_poll_vote,
    turn_in_classroom_submission,
    update_academic_item,
    update_academic_item_status,
    update_course_material,
    update_smart_course,
    update_student_opportunity_status,
    update_tracked_opportunity,
    update_user_profile,
    VALID_MATERIAL_CATEGORIES,
    VALID_OPPORTUNITY_CATEGORIES,
    VALID_TRACKING_STATUSES,
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
    verify_google_id_token,
)
from source_adapters import get_source_adapter

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB upload limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Safely initialize database schema on application startup."""
    init_db()
    if is_production():
        validate_production_config()
    yield


# Initialize schema safely on import
init_db()

app = FastAPI(
    title="SMART API",
    description="Academic Intelligence Dashboard backend for parsing, extracting, persisting, and exporting academic items from chat exports.",
    version="0.2.0",
    lifespan=lifespan,
)


# Configurable CORS origins with credential support
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_origin_regex=r"^https://smart-academic-lake\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Ensure unhandled server exceptions return a structured JSON response with CORS headers."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
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
def health_check(response: Response):
    """Health check endpoint to verify backend service and database readiness."""
    db_connected = False
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1;")
            row = cur.fetchone()
            if row and row[0] == 1:
                db_connected = True
    except Exception:
        db_connected = False

    if not db_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "project": "SMART",
            "version": "0.2.0",
            "database": "disconnected",
        }

    return {
        "status": "healthy",
        "project": "SMART",
        "version": "0.2.0",
        "database": "connected",
        "message": "SMART backend is running",
    }


@app.get("/api/health/live")
def health_liveness():
    """Liveness probe: verifies process is running."""
    return {"status": "alive"}


@app.get("/api/health/ready")
def health_readiness(response: Response):
    """Readiness probe: verifies database connection is ready to serve traffic."""
    db_connected = False
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1;")
            row = cur.fetchone()
            if row and row[0] == 1:
                db_connected = True
    except Exception:
        db_connected = False

    if not db_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "database": "disconnected",
        }

    return {
        "status": "ready",
        "database": "connected",
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


def apply_session_cookie(response: Response, session_id: str) -> None:
    """Set authenticated session cookie with environment-appropriate security attributes."""
    cfg = get_cookie_settings()
    cookie_kwargs: dict[str, Any] = {
        "key": SESSION_COOKIE_NAME,
        "value": session_id,
        "httponly": cfg["httponly"],
        "samesite": cfg["samesite"],
        "secure": cfg["secure"],
        "max_age": SESSION_DURATION_HOURS * 3600,
        "path": cfg["path"],
    }
    if cfg.get("partitioned"):
        cookie_kwargs["partitioned"] = True
    try:
        response.set_cookie(**cookie_kwargs)
    except TypeError:
        cookie_kwargs.pop("partitioned", None)
        response.set_cookie(**cookie_kwargs)


def clear_session_cookie(response: Response) -> None:
    """Clear session cookie ensuring matching path, samesite, and secure attributes."""
    cfg = get_cookie_settings()
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path=cfg["path"],
        samesite=cfg["samesite"],
        secure=cfg["secure"],
        httponly=cfg["httponly"],
    )


class LoginRequest(BaseModel):
    """Payload for user login / demo sign-in."""
    email: str
    id_token: Optional[str] = None  # Google ID token required for institutional non-demo accounts


def get_current_user_optional(
    request: Request,
    smart_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> Optional[dict[str, Any]]:
    """Retrieve current authenticated user from session cookie or header.

    Falls back to provisioned user record matching legacy header only if no session
    token is present and the target user is active & provisioned (for test backward compatibility).
    """
    token = smart_session or (request.cookies.get(SESSION_COOKIE_NAME) if request else None)
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
    if not token and x_session_id:
        token = x_session_id.strip()

    if token:
        session_data = get_session_with_user(token)
        if session_data:
            if "id" not in session_data and "user_id" in session_data:
                session_data["id"] = session_data["user_id"]
            if "user_id" not in session_data and "id" in session_data:
                session_data["user_id"] = session_data["id"]
            return session_data

    # Controlled legacy fallback for test harnesses without cookies
    if x_user_email and not IS_PRODUCTION:
        user = get_user_by_email(x_user_email)
        if user and user.get("status") == "active":
            if "id" not in user and "user_id" in user:
                user["id"] = user["user_id"]
            if "user_id" not in user and "id" in user:
                user["user_id"] = user["id"]
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

    # In production, check if demo accounts are permitted
    raw_allow_demo = os.environ.get("ALLOW_DEMO_LOGINS", "").strip().lower()
    demo_explicitly_allowed = raw_allow_demo in ("1", "true", "yes")
    demo_explicitly_disallowed = raw_allow_demo in ("0", "false", "no")
    is_prod = IS_PRODUCTION or is_production()

    if user.get("is_demo") and is_prod and not demo_explicitly_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo authentication identities are disabled in production environments.",
        )
    if user.get("is_demo") and demo_explicitly_disallowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo authentication identities are disabled in production environments.",
        )

    if user.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended or deactivated. Contact your institution administrator.",
        )

    # For non-demo institutional accounts, verify cryptographic Google authentication proof
    if not user.get("is_demo"):
        id_token = payload.id_token
        if not id_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication proof required: Institutional accounts cannot authenticate by email alone. Please provide a verified Google ID token.",
            )
        try:
            verify_google_id_token(id_token=id_token, expected_email=email)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Google authentication failed: {err}",
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

    apply_session_cookie(response, session_id)

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
    clear_session_cookie(response)
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


class TurnInSubmissionRequest(BaseModel):
    """Payload for turning in an assignment coursework submission."""
    coursework_id: str = Field(..., min_length=1)
    alternate_link: Optional[str] = None


class GradeSubmissionRequest(BaseModel):
    """Payload for grading an assignment submission."""
    assigned_grade: float = Field(..., ge=0)


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
    raw: Optional[bool] = Query(False, description="Return raw JSON instead of redirecting to frontend"),
) -> Any:
    """Handle Google OAuth 2.0 redirect callback, validate CSRF state, and store tokens.

    In browser flow, redirects back to the frontend workspace at http://localhost:5173 with status query param.
    If raw=True or request asks for application/json without HTML, returns JSON.
    """
    frontend_base = get_frontend_url()

    if error:
        err_msg = f"Google OAuth authorization was denied or failed: {error}"
        if raw:
            raise HTTPException(status_code=400, detail=err_msg)
        return RedirectResponse(url=f"{frontend_base}/?google_auth_error={urllib.parse.quote(err_msg)}")

    if not code or not state:
        err_msg = "Missing OAuth 'code' or 'state' query parameter in callback."
        if raw:
            raise HTTPException(status_code=400, detail=err_msg)
        return RedirectResponse(url=f"{frontend_base}/?google_auth_error={urllib.parse.quote(err_msg)}")

    try:
        account = await exchange_code_for_tokens(code=code, state=state)
        redirect_res = RedirectResponse(url=f"{frontend_base}/?google_auth_success=1&email={urllib.parse.quote(account.get('email', ''))}")
        # Synchronize Google profile name/picture to provisioned SMART user if available
        if account.get("email"):
            clean_email = account["email"].strip().lower()
            prov_user = get_user_by_email(clean_email)
            if not prov_user:
                if not is_institutional_email(clean_email):
                    err_msg = (
                        f"Access denied: '{clean_email}' is not an authorized institutional account. "
                        "Please sign in with your official university Google Workspace account or contact your administrator."
                    )
                    if raw:
                        raise HTTPException(status_code=403, detail=err_msg)
                    return RedirectResponse(
                        url=f"{frontend_base}/?google_auth_error={urllib.parse.quote(err_msg)}"
                    )

                req_role = (account.get("role") or "student").strip().lower()
                if req_role not in ("student", "teacher"):
                    req_role = "student"
                prov_user = provision_user(
                    email=clean_email,
                    name=account.get("name") or clean_email.split("@")[0].capitalize(),
                    role=req_role,
                    status="active",
                    is_demo=0,
                )
            else:
                update_user_profile(
                    user_id=prov_user["id"],
                    name=account.get("name") or prov_user.get("name"),
                    picture=account.get("picture") or prov_user.get("picture"),
                )

            if prov_user.get("status") == "active":
                session_id = generate_session_id()
                csrf_token = generate_csrf_token()
                expires_dt = datetime.now(timezone.utc) + timedelta(hours=SESSION_DURATION_HOURS)
                create_user_session(
                    user_id=prov_user["id"],
                    session_id=session_id,
                    csrf_token=csrf_token,
                    expires_at_iso=expires_dt.isoformat(),
                )
                apply_session_cookie(redirect_res, session_id)
            else:
                err_msg = "Account is suspended or deactivated. Contact your institution administrator."
                if raw:
                    raise HTTPException(status_code=403, detail=err_msg)
                return RedirectResponse(url=f"{frontend_base}/?google_auth_error={urllib.parse.quote(err_msg)}")
        if raw:
            return {
                "status": "connected",
                "message": "Google account connected successfully.",
                "account": sanitize_account_for_response(account),
            }
        return redirect_res
    except ValueError as err:
        if raw:
            raise HTTPException(status_code=400, detail=str(err))
        return RedirectResponse(url=f"{frontend_base}/?google_auth_error={urllib.parse.quote(str(err))}")
    except Exception as err:
        if raw:
            raise HTTPException(status_code=500, detail=f"Failed to complete Google OAuth exchange: {err}")
        return RedirectResponse(url=f"{frontend_base}/?google_auth_error={urllib.parse.quote(f'Failed to complete Google OAuth exchange: {err}')}")


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
    current_user: Optional[dict[str, Any]] = Depends(get_current_user_optional),
    x_user_role: Optional[str] = Header("student", alias="X-User-Role"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> dict[str, Any]:
    """Manually trigger Gmail synchronization for authenticated user's account.

    Strictly prevents teachers from accessing or syncing private student Gmail inboxes.
    """
    role = (current_user.get("role") if current_user else None) or (x_user_role or "student").strip().lower()
    if role == "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Teachers cannot access or trigger sync for private student Gmail inboxes.",
        )
    email = (current_user.get("email") if current_user else None) or x_user_email
    account = get_google_account(email=email, role=role)
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
    """List student coursework submissions.

    Students only see their own submissions. Teachers only see submissions for their authorized courses.
    """
    role = (current_user.get("role") if current_user else None) or (x_user_role or "student").strip().lower()
    email = (current_user.get("email") if current_user else None) or x_user_email
    acc = get_google_account(email=email)
    student_id = email or (acc.get("email") if acc else "student.demo@univ.edu")

    # If student, strictly isolate submissions to student's own ID
    student_filter = student_id if role == "student" else None
    teacher_filter = email if role == "teacher" else None

    return list_classroom_submissions(
        course_id=course_id,
        student_id=student_filter,
        teacher_email=teacher_filter,
        include_demo=include_demo,
    )


@app.post("/api/classroom/submissions/turn-in")
def turn_in_submission(
    payload: TurnInSubmissionRequest,
    current_user: Optional[dict[str, Any]] = Depends(get_current_user_optional),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> dict[str, Any]:
    """Turn in a student coursework assignment submission."""
    role = (current_user.get("role") if current_user else None) or (x_user_role or "student").strip().lower()
    if role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Only students can turn in coursework submissions.",
        )
    email = (current_user.get("email") if current_user else None) or x_user_email
    acc = get_google_account(email=email)
    student_id = email or (acc.get("email") if acc else "student.demo@univ.edu")
    student_name = current_user.get("name") if current_user else None

    try:
        res = turn_in_classroom_submission(
            coursework_id=payload.coursework_id,
            student_id=student_id,
            student_name=student_name,
            alternate_link=payload.alternate_link,
        )
        return res
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.patch("/api/classroom/submissions/{submission_id}/grade")
def grade_submission(
    submission_id: str,
    payload: GradeSubmissionRequest,
    current_user: Optional[dict[str, Any]] = Depends(get_current_user_optional),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> dict[str, Any]:
    """Grade a student submission and return it to the student.

    Verifies that the teacher is authorized to grade submissions for the associated course.
    """
    role = (current_user.get("role") if current_user else None) or (x_user_role or "").strip().lower()
    if role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Teacher role is required to grade submissions.",
        )
    email = (current_user.get("email") if current_user else None) or x_user_email

    try:
        graded = grade_classroom_submission(
            submission_id=submission_id,
            assigned_grade=payload.assigned_grade,
            teacher_email=email,
        )
        return graded
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


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


# ==============================================================================
# SMART 3.0: Collaboration Models & Real-Time WebSocket Infrastructure
# ==============================================================================


class CreateCourseRequest(BaseModel):
    code: str
    name: Optional[str] = None
    title: Optional[str] = None
    section: Optional[str] = None
    description: Optional[str] = None
    theme_color: Optional[str] = None


class UpdateCourseRequest(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    section: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[int] = None


class JoinCourseRequest(BaseModel):
    join_code: str


class InviteStudentRequest(BaseModel):
    student_email: Optional[str] = None
    email: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str = ""
    recipient_id: Optional[int] = None
    attachment_url: Optional[str] = None
    attachment_name: Optional[str] = None


class MarkMessagesReadRequest(BaseModel):
    message_ids: Optional[list[int]] = None


class CreateAnnouncementRequest(BaseModel):
    title: str
    content: str
    target_student_ids: Optional[list[int]] = None
    attachment_urls: Optional[list[dict[str, str]]] = None
    is_pinned: bool = False


class CreatePollRequest(BaseModel):
    question: str
    options: list[str] = []
    poll_type: str = "multiple_choice"
    is_anonymous: bool = False
    results_visible_before_close: bool = True
    closes_at: Optional[str] = None


class SubmitVoteRequest(BaseModel):
    option_id: Optional[int] = None
    feedback_text: Optional[str] = None
    short_feedback: Optional[str] = None


class ConnectionManager:
    """Manages active course WebSocket rooms and message broadcasting."""

    def __init__(self):
        self.active_rooms: dict[int, list[WebSocket]] = {}

    async def connect(self, course_id: int, websocket: WebSocket):
        await websocket.accept()
        if course_id not in self.active_rooms:
            self.active_rooms[course_id] = []
        self.active_rooms[course_id].append(websocket)

    def disconnect(self, course_id: int, websocket: WebSocket):
        if course_id in self.active_rooms:
            if websocket in self.active_rooms[course_id]:
                self.active_rooms[course_id].remove(websocket)
            if not self.active_rooms[course_id]:
                del self.active_rooms[course_id]

    async def broadcast(self, course_id: int, message: dict[str, Any]):
        if course_id in self.active_rooms:
            dead_sockets = []
            for connection in list(self.active_rooms[course_id]):
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_sockets.append(connection)
            for dead in dead_sockets:
                self.disconnect(course_id, dead)


ws_manager = ConnectionManager()


@app.websocket("/ws/courses/{course_id}/messages")
async def websocket_course_chat(
    websocket: WebSocket,
    course_id: int,
    session_id: Optional[str] = Query(None),
):
    """Real-time authenticated course chat WebSocket endpoint."""
    smart_session = websocket.cookies.get(SESSION_COOKIE_NAME) or session_id
    user = None
    if smart_session:
        user = get_session_with_user(smart_session)

    if not user and not IS_PRODUCTION:
        x_email = websocket.headers.get("x-user-email")
        if x_email:
            user = get_user_by_email(x_email)

    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = user["id"]
    if not is_user_enrolled(course_id, user_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(course_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            content = data.get("content", "")
            recipient_id = data.get("recipient_id")
            attachment_url = data.get("attachment_url")
            attachment_name = data.get("attachment_name")

            if content or attachment_url:
                saved = save_course_message(
                    course_id=course_id,
                    sender_id=user_id,
                    content=content,
                    recipient_id=recipient_id,
                    attachment_url=attachment_url,
                    attachment_name=attachment_name,
                )
                await ws_manager.broadcast(course_id, {
                    "type": "new_message",
                    "message": saved,
                })
    except WebSocketDisconnect:
        ws_manager.disconnect(course_id, websocket)
    except Exception:
        ws_manager.disconnect(course_id, websocket)


# ==============================================================================
# SMART 3.0: Course & Student Management REST APIs
# ==============================================================================


@app.post("/api/courses", status_code=status.HTTP_201_CREATED)
def create_course_endpoint(
    payload: CreateCourseRequest,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Create a new SMART course with unique enrollment join code (Teacher only)."""
    try:
        course_name = (payload.name or payload.title or "").strip()
        if not course_name:
            raise HTTPException(status_code=400, detail="Course name/title cannot be empty.")
        course = create_smart_course(
            teacher_id=current_user["id"],
            code=payload.code,
            name=course_name,
            section=payload.section,
            description=payload.description,
        )
        if "name" in course and "title" not in course:
            course["title"] = course["name"]
        return course
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.get("/api/courses")
def list_courses_endpoint(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all SMART courses accessible to the authenticated student or teacher."""
    role = current_user.get("role", "student")
    user_id = current_user["id"]
    courses = list_user_smart_courses(user_id=user_id, role=role)
    for c in courses:
        if "name" in c and "title" not in c:
            c["title"] = c["name"]
        if "student_count" in c and "enrolled_count" not in c:
            c["enrolled_count"] = c["student_count"]
    return courses


@app.get("/api/courses/{course_id}")
def get_course_endpoint(
    course_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get single course details with membership verification."""
    course = get_smart_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Course {course_id} not found.")

    user_id = current_user["id"]
    if not is_user_enrolled(course_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied: You are not enrolled in this course.")

    return course


@app.put("/api/courses/{course_id}")
def update_course_endpoint(
    course_id: int,
    payload: UpdateCourseRequest,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Update course metadata (Teacher only)."""
    try:
        updated = update_smart_course(
            course_id=course_id,
            updates=payload.model_dump(exclude_unset=True),
            teacher_id=current_user["id"],
        )
        if not updated:
            raise HTTPException(status_code=404, detail=f"Course {course_id} not found.")
        return updated
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.post("/api/courses/{course_id}/regenerate-code")
def regenerate_join_code_endpoint(
    course_id: int,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Regenerate a course's student enrollment join code (Teacher only)."""
    try:
        return regenerate_course_join_code(course_id=course_id, teacher_id=current_user["id"])
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.post("/api/courses/join")
def join_course_endpoint(
    payload: JoinCourseRequest,
    current_user: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    """Enroll a student into a course using a valid join code."""
    try:
        enrolled = enroll_student_by_join_code(
            user_id=current_user["id"],
            join_code=payload.join_code,
        )
        return enrolled
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.get("/api/courses/{course_id}/members")
def list_course_members_endpoint(
    course_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all enrolled students and instructors in a course."""
    if not is_user_enrolled(course_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Access denied: You are not enrolled in this course.")
    return list_course_members(course_id)


@app.delete("/api/courses/{course_id}/members/{target_user_id}")
def remove_course_member_endpoint(
    course_id: int,
    target_user_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Remove student from course (Teacher removing student or Student dropping self)."""
    try:
        success = remove_student_from_course(
            course_id=course_id,
            user_id=target_user_id,
            requester_id=current_user["id"],
            requester_role=current_user.get("role", "student"),
        )
        if not success:
            raise HTTPException(status_code=404, detail="Membership not found.")
        return {"status": "success", "course_id": course_id, "user_id": target_user_id}
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.post("/api/courses/{course_id}/invitations")
def invite_student_endpoint(
    course_id: int,
    payload: InviteStudentRequest,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Invite a student by email address to join a course (Teacher only)."""
    try:
        target_email = (payload.student_email or payload.email or "").strip().lower()
        if not target_email:
            raise HTTPException(status_code=400, detail="Student email cannot be empty.")
        inv = create_course_invitation(
            course_id=course_id,
            inviter_id=current_user["id"],
            student_email=target_email,
        )
        return inv
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.get("/api/courses/{course_id}/invitations")
def list_course_invitations_endpoint(
    course_id: int,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> list[dict[str, Any]]:
    """List pending invitations issued for a course (Teacher only)."""
    return list_course_invitations(course_id)


@app.get("/api/invitations")
@app.get("/api/student/invitations")
def list_student_invitations_endpoint(
    current_user: dict[str, Any] = Depends(require_role("student")),
) -> list[dict[str, Any]]:
    """List pending course invitations issued to the logged-in student."""
    return list_student_pending_invitations(current_user["email"])


@app.post("/api/invitations/{invitation_id}/accept")
@app.post("/api/student/invitations/{invitation_id}/accept")
def accept_invitation_endpoint(
    invitation_id: int,
    current_user: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    """Accept a pending course invitation."""
    try:
        return accept_course_invitation(
            invitation_id=invitation_id,
            student_user_id=current_user["id"],
            student_email=current_user["email"],
        )
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


# ==============================================================================
# SMART 3.0: Communication & Messages REST APIs
# ==============================================================================


@app.get("/api/courses/{course_id}/messages")
def list_messages_endpoint(
    course_id: int,
    recipient_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    before_id: Optional[int] = Query(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Retrieve message history for a course or direct message thread."""
    try:
        return list_course_messages(
            course_id=course_id,
            user_id=current_user["id"],
            recipient_id=recipient_id,
            limit=limit,
            before_id=before_id,
        )
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))


@app.post("/api/courses/{course_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message_endpoint(
    course_id: int,
    payload: SendMessageRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Send a message via REST and broadcast to active WebSocket clients."""
    try:
        saved = save_course_message(
            course_id=course_id,
            sender_id=current_user["id"],
            content=payload.content,
            recipient_id=payload.recipient_id,
            attachment_url=payload.attachment_url,
            attachment_name=payload.attachment_name,
        )
        await ws_manager.broadcast(course_id, {
            "type": "new_message",
            "message": saved,
        })
        return saved
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.post("/api/courses/{course_id}/messages/read")
def mark_messages_read_endpoint(
    course_id: int,
    payload: MarkMessagesReadRequest = MarkMessagesReadRequest(),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark messages as read."""
    count = mark_messages_read(
        course_id=course_id,
        user_id=current_user["id"],
        message_ids=payload.message_ids,
    )
    return {"status": "success", "marked_read": count}


@app.get("/api/messages/unread-count")
def get_unread_messages_endpoint(
    course_id: Optional[int] = Query(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, int]:
    """Get count of unread messages."""
    user_id = current_user.get("id") or current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid authenticated user profile required.",
        )
    cnt = get_unread_message_count(user_id=user_id, course_id=course_id)
    return {"unread_count": cnt}


# ==============================================================================
# SMART 3.0: Course Announcements REST APIs
# ==============================================================================


@app.post("/api/courses/{course_id}/announcements", status_code=status.HTTP_201_CREATED)
def create_announcement_endpoint(
    course_id: int,
    payload: CreateAnnouncementRequest,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Broadcast an official announcement to course students (Teacher only)."""
    try:
        ann = create_course_announcement(
            course_id=course_id,
            teacher_id=current_user["id"],
            title=payload.title,
            content=payload.content,
            target_student_ids=payload.target_student_ids,
            attachment_urls=payload.attachment_urls,
            is_pinned=payload.is_pinned,
        )
        return ann
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.get("/api/courses/{course_id}/announcements")
def list_announcements_endpoint(
    course_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List announcements for a course with user-specific read indicators."""
    if not is_user_enrolled(course_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Access denied: You are not enrolled in this course.")
    return list_course_announcements(course_id=course_id, user_id=current_user["id"])


@app.post("/api/announcements/{announcement_id}/acknowledge")
@app.post("/api/courses/{course_id}/announcements/{announcement_id}/acknowledge")
def acknowledge_announcement_endpoint(
    announcement_id: int,
    course_id: Optional[int] = None,
    current_user: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    """Acknowledge / mark as read an announcement."""
    try:
        return acknowledge_announcement(announcement_id=announcement_id, student_id=current_user["id"])
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


# ==============================================================================
# SMART 3.0: Interactive Polls REST APIs
# ==============================================================================


@app.post("/api/courses/{course_id}/polls", status_code=status.HTTP_201_CREATED)
def create_poll_endpoint(
    course_id: int,
    payload: CreatePollRequest,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Create a structured course poll (Teacher only)."""
    try:
        poll = create_course_poll(
            course_id=course_id,
            creator_id=current_user["id"],
            question=payload.question,
            options=payload.options,
            poll_type=payload.poll_type,
            is_anonymous=payload.is_anonymous,
            results_visible_before_close=payload.results_visible_before_close,
            closes_at=payload.closes_at,
        )
        return poll
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.get("/api/courses/{course_id}/polls")
def list_polls_endpoint(
    course_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all polls for a course with vote distributions and user's vote."""
    if not is_user_enrolled(course_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Access denied: You are not enrolled in this course.")
    return list_course_polls(course_id=course_id, user_id=current_user["id"])


@app.get("/api/polls/{poll_id}")
def get_poll_endpoint(
    poll_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve single poll details."""
    poll = get_poll_details(poll_id=poll_id, user_id=current_user["id"])
    if not poll:
        raise HTTPException(status_code=404, detail=f"Poll {poll_id} not found.")
    return poll


@app.post("/api/polls/{poll_id}/vote")
@app.post("/api/courses/{course_id}/polls/{poll_id}/vote")
def submit_poll_vote_endpoint(
    poll_id: int,
    payload: SubmitVoteRequest,
    course_id: Optional[int] = None,
    current_user: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    """Submit a vote or feedback in a course poll."""
    try:
        feedback = payload.feedback_text or payload.short_feedback
        updated_poll = submit_poll_vote(
            poll_id=poll_id,
            user_id=current_user["id"],
            option_id=payload.option_id,
            feedback_text=feedback,
        )
        return updated_poll
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.post("/api/polls/{poll_id}/close")
@app.post("/api/courses/{course_id}/polls/{poll_id}/close")
def close_poll_endpoint(
    poll_id: int,
    course_id: Optional[int] = None,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Close an active poll early (Teacher only)."""
    try:
        return close_course_poll(poll_id=poll_id, teacher_id=current_user["id"])
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


# ==============================================================================
# SMART 3.0: Unified Notifications REST APIs
# ==============================================================================


@app.get("/api/notifications")
def list_notifications_endpoint(
    course_id: Optional[int] = Query(None),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List persistent notifications for the authenticated user."""
    return list_user_notifications(
        user_id=current_user["id"],
        course_id=course_id,
        unread_only=unread_only,
        limit=limit,
    )


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read_endpoint(
    notification_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark a notification as read."""
    success = mark_notification_read(notification_id=notification_id, user_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return {"status": "success", "id": notification_id}


@app.post("/api/notifications/read-all")
def mark_all_notifications_read_endpoint(
    course_id: Optional[int] = Query(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark all notifications as read."""
    count = mark_all_notifications_read(user_id=current_user["id"], course_id=course_id)
    return {"status": "success", "marked_read": count}


@app.get("/api/notifications/unread-count")
def get_unread_notifications_count_endpoint(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, int]:
    """Get count of unread notifications for the authenticated user."""
    user_id = current_user.get("id") or current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid authenticated user profile required.",
        )
    cnt = get_unread_notification_count(user_id=user_id)
    return {"unread_count": cnt}


# ==============================================================================
# SMART 3.0: Engagement Analytics REST APIs
# ==============================================================================


@app.get("/api/courses/{course_id}/analytics")
def get_course_analytics_endpoint(
    course_id: int,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Compute real-time data-driven course engagement analytics (Teacher only)."""
    try:
        analytics = get_course_engagement_analytics(
            course_id=course_id,
            teacher_id=current_user["id"],
        )
        return analytics
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.get("/api/student/analytics")
def get_student_analytics_endpoint(
    current_user: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    """Retrieve personal engagement and completion progress for the student."""
    return get_student_personal_analytics(student_id=current_user["id"])


# ==============================================================================
# SMART 3.1: Native Teacher Study Materials & Resource Management
# ==============================================================================

MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "25"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
UPLOAD_BASE_DIR = Path(__file__).resolve().parent / "uploads" / "course_materials"
UPLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".txt": "text/plain",
}

BLOCKED_DANGEROUS_EXTENSIONS: set[str] = {
    ".exe", ".bat", ".cmd", ".sh", ".py", ".js", ".mjs", ".html", ".htm",
    ".php", ".vbs", ".ps1", ".jar", ".msi", ".dll", ".com", ".scr", ".svg",
    ".bin", ".elf", ".apk", ".app", ".dmg", ".iso"
}


def validate_file_content_and_signature(filename: str, initial_chunk: bytes, total_size: int) -> tuple[str, str]:
    """Verify file size, extension safety, and header magic bytes.
    
    Returns (clean_lowercase_extension, canonical_mime_type).
    """
    if total_size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_SIZE_MB} MB.",
        )

    _, ext = os.path.splitext(filename or "")
    ext = ext.lower().strip()

    if ext in BLOCKED_DANGEROUS_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security alert: Prohibited executable or script file extension '{ext}'.",
        )

    if ext not in ALLOWED_EXTENSIONS_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed: PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, TXT.",
        )

    canonical_mime = ALLOWED_EXTENSIONS_MAP[ext]

    # Validate file magic bytes
    if ext == ".pdf":
        if b"%PDF-" not in initial_chunk[:1024]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file: Header does not match genuine PDF structure.",
            )
    elif ext in (".docx", ".pptx", ".xlsx"):
        if not initial_chunk.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file: Header does not match valid {ext[1:].upper()} OpenXML archive structure.",
            )
    elif ext in (".doc", ".ppt", ".xls"):
        if not initial_chunk.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file: Header does not match valid Microsoft Compound Document format.",
            )
    elif ext == ".txt":
        if b"\x00" in initial_chunk[:1024]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file: Plain text file contains binary null bytes.",
            )
        try:
            initial_chunk.decode("utf-8")
        except UnicodeDecodeError:
            try:
                initial_chunk.decode("latin-1")
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid file: Text content cannot be decoded.",
                )

    return ext, canonical_mime


class CourseMaterialUpdatePayload(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None


@app.post("/api/courses/{course_id}/materials", status_code=status.HTTP_201_CREATED)
async def upload_course_material_endpoint(
    course_id: int,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    category: str = Form("Study Materials"),
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Upload and publish a course study material (Teacher only)."""
    course = get_smart_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    if not is_user_course_teacher(course_id, current_user["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the course instructor can upload study materials.",
        )

    clean_title = (title or "").strip()
    if not clean_title:
        clean_title = os.path.splitext(file.filename or "Untitled Resource")[0]

    initial_chunk = await file.read(4096)
    if not initial_chunk:
        raise HTTPException(status_code=400, detail="Cannot upload an empty file.")

    chunks = [initial_chunk]
    total_size = len(initial_chunk)

    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_SIZE_MB} MB.",
            )
        chunks.append(chunk)

    clean_ext, detected_mime = validate_file_content_and_signature(
        file.filename or "",
        initial_chunk,
        total_size,
    )

    # Secure course upload folder
    course_dir = (UPLOAD_BASE_DIR / str(course_id)).resolve()
    course_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}{clean_ext}"
    target_path = (course_dir / stored_filename).resolve()

    if not target_path.is_relative_to(course_dir):
        raise HTTPException(status_code=400, detail="Path traversal attempt detected.")

    with open(target_path, "wb") as f:
        for c in chunks:
            f.write(c)

    # Persist in DB
    clean_cat = category.strip() if category and category.strip() in VALID_MATERIAL_CATEGORIES else "Study Materials"
    material = save_course_material(
        course_id=course_id,
        uploaded_by=current_user["id"],
        title=clean_title,
        description=description,
        original_filename=file.filename or f"material{clean_ext}",
        stored_filename=stored_filename,
        storage_path=str(target_path),
        file_extension=clean_ext,
        mime_type=detected_mime,
        file_size=total_size,
        category=clean_cat,
    )

    # Broadcast notification to enrolled students
    student_ids = get_course_enrolled_student_ids(course_id)
    instructor_name = current_user.get("name") or "Instructor"
    for sid in student_ids:
        try:
            create_notification(
                user_id=sid,
                course_id=course_id,
                title=f"[{course['name']}] New {clean_cat}: {clean_title}",
                message=f"Prof. {instructor_name} uploaded '{clean_title}'.",
                notification_type="announcement",
                reference_id=f"/materials?course={course_id}&material={material['id']}",
            )
        except Exception:
            pass

    return {
        "id": material["id"],
        "course_id": material["course_id"],
        "uploaded_by": material["uploaded_by"],
        "title": material["title"],
        "description": material["description"],
        "original_filename": material["original_filename"],
        "file_extension": material["file_extension"],
        "mime_type": material["mime_type"],
        "file_size": material["file_size"],
        "category": material["category"],
        "created_at": material["created_at"],
        "updated_at": material["updated_at"],
        "uploader_name": material["uploader_name"],
        "uploader_role": material["uploader_role"],
        "course_name": material["course_name"],
        "course_code": material["course_code"],
    }


@app.get("/api/courses/{course_id}/materials")
def list_course_materials_endpoint(
    course_id: int,
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List study materials for a course (Enrolled students and instructors)."""
    course = get_smart_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    if not is_user_enrolled(course_id, current_user["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be enrolled in this course to view its study materials.",
        )

    return list_course_materials(course_id=course_id, category=category, search=search)


@app.get("/api/materials/{material_id}")
def get_material_metadata_endpoint(
    material_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve metadata for a specific study material (Authorized course members)."""
    material = get_course_material(material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Study material not found.")

    if not is_user_enrolled(material["course_id"], current_user["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be enrolled in the course to view this study material.",
        )

    return {
        "id": material["id"],
        "course_id": material["course_id"],
        "uploaded_by": material["uploaded_by"],
        "title": material["title"],
        "description": material["description"],
        "original_filename": material["original_filename"],
        "file_extension": material["file_extension"],
        "mime_type": material["mime_type"],
        "file_size": material["file_size"],
        "category": material["category"],
        "created_at": material["created_at"],
        "updated_at": material["updated_at"],
        "uploader_name": material["uploader_name"],
        "uploader_role": material["uploader_role"],
        "course_name": material["course_name"],
        "course_code": material["course_code"],
    }


@app.get("/api/materials/{material_id}/download")
def download_course_material_endpoint(
    material_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Download the original uploaded study material file."""
    material = get_course_material(material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Study material not found.")

    if not is_user_enrolled(material["course_id"], current_user["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be enrolled in the course to download this study material.",
        )

    file_path = Path(material["storage_path"]).resolve()
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Physical material file not found on server.")

    encoded_filename = urllib.parse.quote(material["original_filename"])
    return FileResponse(
        path=str(file_path),
        media_type=material.get("mime_type", "application/octet-stream"),
        filename=material["original_filename"],
        headers={
            "Content-Disposition": f'attachment; filename="{encoded_filename}"; filename*=UTF-8\'\'{encoded_filename}'
        },
    )


@app.get("/api/materials/{material_id}/preview")
def preview_course_material_endpoint(
    material_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Preview supported documents (PDF, plain text) inline in browser/SMART UI."""
    material = get_course_material(material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Study material not found.")

    if not is_user_enrolled(material["course_id"], current_user["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be enrolled in the course to preview this study material.",
        )

    file_path = Path(material["storage_path"]).resolve()
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Physical material file not found on server.")

    ext = material["file_extension"].lower()
    encoded_filename = urllib.parse.quote(material["original_filename"])

    if ext in (".pdf", ".txt"):
        return FileResponse(
            path=str(file_path),
            media_type=material["mime_type"],
            headers={
                "Content-Disposition": f'inline; filename="{encoded_filename}"; filename*=UTF-8\'\'{encoded_filename}'
            },
        )
    else:
        return FileResponse(
            path=str(file_path),
            media_type=material["mime_type"],
            filename=material["original_filename"],
            headers={
                "Content-Disposition": f'attachment; filename="{encoded_filename}"; filename*=UTF-8\'\'{encoded_filename}'
            },
        )


@app.patch("/api/materials/{material_id}")
def update_course_material_endpoint(
    material_id: int,
    payload: CourseMaterialUpdatePayload,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Update title, description, or category for a study material (Instructor only)."""
    material = get_course_material(material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Study material not found.")

    if not is_user_course_teacher(material["course_id"], current_user["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the course instructor can modify study materials.",
        )

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return material

    updated = update_course_material(
        material_id=material_id,
        updates=updates,
        teacher_id=current_user["id"],
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Could not update study material.")

    return updated


@app.delete("/api/materials/{material_id}")
def delete_course_material_endpoint(
    material_id: int,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Delete study material record and securely delete the stored file from disk (Instructor only)."""
    material = get_course_material(material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Study material not found.")

    if not is_user_course_teacher(material["course_id"], current_user["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the course instructor can delete study materials.",
        )

    deleted_rec = delete_course_material(
        material_id=material_id,
        teacher_id=current_user["id"],
    )
    if not deleted_rec:
        raise HTTPException(status_code=404, detail="Material could not be deleted.")

    try:
        fpath = Path(deleted_rec["storage_path"]).resolve()
        if fpath.is_file():
            fpath.unlink(missing_ok=True)
    except Exception:
        pass

    return {"status": "deleted", "id": material_id}


# ==============================================================================
# SMART 3.2: Student Competitions & Opportunities Tracking with Faculty Analytics
# ==============================================================================


class TrackOpportunityPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    organizer: Optional[str] = None
    category: str = Field("Competition")
    description: Optional[str] = None
    registration_url: Optional[str] = None
    registration_deadline: Optional[str] = None
    event_date: Optional[str] = None
    tracking_status: str = Field("Interested")
    course_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    source_platform: str = Field("manual")
    source_reference: Optional[str] = None


class UpdateTrackedOpportunityPayload(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    organizer: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    registration_url: Optional[str] = None
    registration_deadline: Optional[str] = None
    event_date: Optional[str] = None
    tracking_status: Optional[str] = None
    course_id: Optional[int] = None


@app.get("/api/student/opportunities")
def list_student_opportunities_endpoint(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    course_id: Optional[int] = Query(None),
    current_user: dict[str, Any] = Depends(require_role("student")),
) -> list[dict[str, Any]]:
    """Retrieve all opportunities tracked by the authenticated student.
    
    Proactively checks and dispatches due reminders (7d, 3d, 1d) on retrieval.
    """
    student_id = current_user["id"]
    # Check and dispatch due reminders
    check_and_dispatch_opportunity_reminders(student_id=student_id)

    return list_student_tracked_opportunities(
        student_id=student_id,
        category=category,
        status=status,
        search=search,
        course_id=course_id,
    )


@app.post("/api/student/opportunities", status_code=status.HTTP_201_CREATED)
def track_opportunity_endpoint(
    payload: TrackOpportunityPayload,
    current_user: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    """Save/track an opportunity for the student, with optional course association."""
    student_id = current_user["id"]

    # If course_id is provided, verify student is enrolled in that course
    if payload.course_id is not None:
        if not is_user_enrolled(payload.course_id, student_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must be actively enrolled in the course to associate it with this opportunity.",
            )

    try:
        tracked = save_tracked_opportunity(
            student_id=student_id,
            title=payload.title,
            organizer=payload.organizer,
            category=payload.category,
            description=payload.description,
            registration_url=payload.registration_url,
            registration_deadline=payload.registration_deadline,
            event_date=payload.event_date,
            tracking_status=payload.tracking_status,
            course_id=payload.course_id,
            opportunity_id=payload.opportunity_id,
            source_platform=payload.source_platform,
            source_reference=payload.source_reference,
        )
        return tracked
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.patch("/api/student/opportunities/{tracked_id}")
def update_tracked_opportunity_endpoint(
    tracked_id: int,
    payload: UpdateTrackedOpportunityPayload,
    current_user: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    """Update details or participation status of a tracked opportunity."""
    student_id = current_user["id"]

    existing = get_tracked_opportunity(tracked_id, student_id=student_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Tracked opportunity not found.")

    if payload.course_id is not None:
        if not is_user_enrolled(payload.course_id, student_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must be actively enrolled in the course to associate it.",
            )

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updated = update_tracked_opportunity(
        tracked_id=tracked_id,
        student_id=student_id,
        updates=updates,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Could not update opportunity.")
    return updated


@app.delete("/api/student/opportunities/{tracked_id}")
def delete_tracked_opportunity_endpoint(
    tracked_id: int,
    current_user: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    """Remove a tracked opportunity from the student's personal list."""
    student_id = current_user["id"]
    success = delete_tracked_opportunity(tracked_id=tracked_id, student_id=student_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tracked opportunity not found.")
    return {"status": "deleted", "id": tracked_id}


@app.post("/api/student/opportunities/check-reminders")
def check_student_opportunity_reminders_endpoint(
    current_user: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    """Check registration deadlines and generate reminders (7d, 3d, 1d) for the student."""
    count = check_and_dispatch_opportunity_reminders(student_id=current_user["id"])
    return {"status": "success", "dispatched_reminders": count}


@app.get("/api/courses/{course_id}/opportunities/analytics")
def get_course_opportunities_analytics_endpoint(
    course_id: int,
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> dict[str, Any]:
    """Retrieve aggregated opportunity participation analytics for authorized course faculty."""
    try:
        return get_course_opportunities_analytics(
            course_id=course_id,
            teacher_id=current_user["id"],
        )
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))


@app.get("/api/courses/{course_id}/opportunities/participation")
def list_course_opportunities_participation_endpoint(
    course_id: int,
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: dict[str, Any] = Depends(require_role("teacher")),
) -> list[dict[str, Any]]:
    """Retrieve student opportunity participation records for an authorized course."""
    try:
        return list_course_opportunity_participations(
            course_id=course_id,
            teacher_id=current_user["id"],
            category=category,
            status=status,
        )
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
