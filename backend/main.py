"""FastAPI application for SMART (Academic Intelligence Dashboard).

Provides endpoints for health checks, chat parsing, candidate academic information
extraction from WhatsApp exports, SQLite persistence for academic tasks, and
RFC 5545 iCalendar export.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from calendar_export import generate_ics
from database import (
    ALLOWED_CATEGORIES,
    ALLOWED_CONFIDENCE_LEVELS,
    ALLOWED_STATUSES,
    delete_academic_item,
    find_duplicate_item,
    get_academic_item_by_id,
    get_confirmed_deadline_items,
    init_db,
    is_valid_iso_date,
    list_academic_items,
    save_academic_item,
    update_academic_item,
    update_academic_item_status,
)
from extractor import create_candidate_token, extract_academic_items, verify_candidate_token
from parser import parse_whatsapp_text

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
        payload["_trusted_confidence"] = "UNASSESSED"
        payload["_trusted_confidence_reasons"] = []
        payload["evidence_start_index"] = None
        payload["evidence_end_index"] = None

    effective_cat = trusted_category or item.category
    clean_cat = effective_cat.strip()
    if clean_cat not in ALLOWED_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{clean_cat}'. Allowed categories: {', '.join(sorted(ALLOWED_CATEGORIES))}",
        )

    clean_status = (item.status or "pending").strip().lower()
    if clean_status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{item.status}'. Allowed statuses: {', '.join(sorted(ALLOWED_STATUSES))}",
        )

    # Deduplication check
    existing = find_duplicate_item(
        source_text=item.source_text,
        source_timestamp=item.source_timestamp,
        source_sender=item.source_sender,
        category=clean_cat,
        source_filename=item.source_filename,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Academic item has already been saved (Task #{existing['id']}).",
        )

    try:
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
) -> list[dict[str, Any]]:
    """List and filter saved academic items with deterministic ordering."""
    try:
        items = list_academic_items(
            category=category,
            status=status_filter,
            search=search,
            due_before=due_before,
            due_after=due_after,
            confidence=confidence,
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
    """Retrieve a single academic item by ID."""
    item = get_academic_item_by_id(item_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"Academic item with ID {item_id} not found.",
        )
    return item


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

