"""SQLite Persistence and Academic Task Management Database Module.

Provides connection management, schema initialization, CRUD operations,
deduplication, and deterministic queries for SMART academic items.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Optional

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "smart.db"

ALLOWED_CATEGORIES = {"Assignment", "Exam", "Announcement", "Event", "Opportunity"}
ALLOWED_STATUSES = {"pending", "completed", "dismissed"}

IMMUTABLE_FIELDS = {
    "id",
    "source_text",
    "source_sender",
    "source_timestamp",
    "source_filename",
    "created_at",
}

EDITABLE_COLUMNS = {
    "title",
    "category",
    "description",
    "date_text",
    "due_date",
    "date_type",
    "date_status",
    "status",
    "review_required",
    "review_reasons",
}


def get_db_path() -> Path:
    """Return the active database path from environment or default location."""
    env_path = os.environ.get("SMART_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def is_valid_iso_date(val: Optional[str]) -> bool:
    """Check if a string is a valid ISO 8601 YYYY-MM-DD date."""
    if not val or not isinstance(val, str):
        return False
    if len(val) != 10 or val[4] != "-" or val[7] != "-":
        return False
    try:
        datetime.strptime(val, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def get_db_connection(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    """Create and configure a SQLite database connection with row factory."""
    resolved_path = Path(db_path) if db_path else get_db_path()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved_path), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db(db_path: Optional[Path | str] = None) -> None:
    """Safely initialize the academic items schema and indexes."""
    resolved_path = Path(db_path) if db_path else get_db_path()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    with get_db_connection(resolved_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS academic_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                date_text TEXT,
                due_date TEXT,
                date_type TEXT,
                date_status TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                source_sender TEXT,
                source_timestamp TEXT,
                source_text TEXT NOT NULL,
                source_filename TEXT,
                review_required INTEGER NOT NULL DEFAULT 0,
                review_reasons TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_academic_items_category ON academic_items(category);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_academic_items_status ON academic_items(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_academic_items_due_date ON academic_items(due_date);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_academic_items_dedup ON academic_items(source_text, source_timestamp, source_sender, category);"
        )
        conn.commit()


def row_to_item_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert an academic_items sqlite3.Row to a clean dictionary."""
    reasons_raw = row["review_reasons"]
    reasons: list[str] = []
    if reasons_raw:
        try:
            reasons = json.loads(reasons_raw)
            if not isinstance(reasons, list):
                reasons = [str(reasons)]
        except (json.JSONDecodeError, TypeError):
            reasons = [reasons_raw]

    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "description": row["description"] or "",
        "date_text": row["date_text"],
        "due_date": row["due_date"],
        "date_type": row["date_type"] or "unknown",
        "date_status": row["date_status"] or "not_found",
        "status": row["status"],
        "source_sender": row["source_sender"] or "",
        "source_timestamp": row["source_timestamp"] or "",
        "source_text": row["source_text"],
        "source_filename": row["source_filename"] or "",
        "review_required": bool(row["review_required"]),
        "review_reasons": reasons,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def find_duplicate_item(
    source_text: str,
    source_timestamp: Optional[str],
    source_sender: Optional[str],
    category: str,
    source_filename: Optional[str] = None,
    db_path: Optional[Path | str] = None,
) -> Optional[dict[str, Any]]:
    """Check if an item matching key source provenance already exists."""
    clean_text = (source_text or "").strip()
    clean_timestamp = (source_timestamp or "").strip()
    clean_sender = (source_sender or "").strip()
    clean_filename = (source_filename or "").strip()

    query = """
        SELECT * FROM academic_items
        WHERE TRIM(source_text) = ?
          AND category = ?
          AND (TRIM(COALESCE(source_timestamp, '')) = ?)
          AND (TRIM(COALESCE(source_sender, '')) = ?)
          AND (TRIM(COALESCE(source_filename, '')) = ?)
        LIMIT 1;
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            query,
            (clean_text, category, clean_timestamp, clean_sender, clean_filename),
        )
        row = cursor.fetchone()
        if row:
            return row_to_item_dict(row)
    return None


def save_academic_item(
    data: dict[str, Any],
    db_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Validate and insert an academic item into the database.

    Raises ValueError for schema/business validation errors.
    """
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("Item title is required.")

    category = (data.get("category") or "").strip()
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Allowed categories: {', '.join(sorted(ALLOWED_CATEGORIES))}"
        )

    source_text = (data.get("source_text") or "").strip()
    if not source_text:
        raise ValueError("Source text is required.")

    status = (data.get("status") or "pending").strip().lower()
    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Allowed statuses: {', '.join(sorted(ALLOWED_STATUSES))}"
        )

    due_date = data.get("due_date")
    if due_date:
        due_date = str(due_date).strip()
        if not is_valid_iso_date(due_date):
            raise ValueError(
                f"Invalid due_date format '{due_date}'. Expected YYYY-MM-DD."
            )
    else:
        due_date = None

    description = (data.get("description") or source_text).strip()
    date_text = data.get("date_text")
    date_text = str(date_text).strip() if date_text else None

    date_type = data.get("date_type")
    date_type = str(date_type).strip() if date_type else "unknown"

    date_status = data.get("date_status")
    date_status = str(date_status).strip() if date_status else "not_found"

    source_sender = data.get("source_sender")
    source_sender = str(source_sender).strip() if source_sender else ""

    source_timestamp = data.get("source_timestamp")
    source_timestamp = str(source_timestamp).strip() if source_timestamp else ""

    source_filename = data.get("source_filename")
    source_filename = str(source_filename).strip() if source_filename else ""

    review_required = 1 if data.get("review_required") else 0
    review_reasons = data.get("review_reasons") or []
    if isinstance(review_reasons, str):
        review_reasons_str = json.dumps([review_reasons])
    else:
        review_reasons_str = json.dumps(list(review_reasons))

    now_iso = datetime.now(timezone.utc).isoformat()

    insert_sql = """
        INSERT INTO academic_items (
            title, category, description, date_text, due_date, date_type,
            date_status, status, source_sender, source_timestamp, source_text,
            source_filename, review_required, review_reasons, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            insert_sql,
            (
                title,
                category,
                description,
                date_text,
                due_date,
                date_type,
                date_status,
                status,
                source_sender,
                source_timestamp,
                source_text,
                source_filename,
                review_required,
                review_reasons_str,
                now_iso,
                now_iso,
            ),
        )
        new_id = cursor.lastrowid
        conn.commit()

    saved = get_academic_item_by_id(new_id, db_path=db_path)
    if not saved:
        raise RuntimeError("Failed to retrieve item immediately after saving.")
    return saved


def get_academic_item_by_id(
    item_id: int,
    db_path: Optional[Path | str] = None,
) -> Optional[dict[str, Any]]:
    """Retrieve a single academic item by its primary key ID."""
    query = "SELECT * FROM academic_items WHERE id = ? LIMIT 1;"
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, (item_id,))
        row = cursor.fetchone()
        if row:
            return row_to_item_dict(row)
    return None


def list_academic_items(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    due_before: Optional[str] = None,
    due_after: Optional[str] = None,
    db_path: Optional[Path | str] = None,
) -> list[dict[str, Any]]:
    """Query and filter academic items with deterministic ordering.

    Orders upcoming dated items first chronologically, followed by undated items,
    with newest ID as tie-breaker.
    """
    conditions: list[str] = []
    params: list[Any] = []

    if category:
        category_clean = category.strip()
        if category_clean not in ALLOWED_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Allowed categories: {', '.join(sorted(ALLOWED_CATEGORIES))}"
            )
        conditions.append("category = ?")
        params.append(category_clean)

    if status:
        status_clean = status.strip().lower()
        if status_clean not in ALLOWED_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Allowed statuses: {', '.join(sorted(ALLOWED_STATUSES))}"
            )
        conditions.append("status = ?")
        params.append(status_clean)

    if search:
        search_pattern = f"%{search.strip()}%"
        conditions.append(
            "(title LIKE ? OR description LIKE ? OR source_text LIKE ?)"
        )
        params.extend([search_pattern, search_pattern, search_pattern])

    if due_before:
        due_before_clean = due_before.strip()
        if not is_valid_iso_date(due_before_clean):
            raise ValueError(
                f"Invalid due_before date format '{due_before}'. Expected YYYY-MM-DD."
            )
        conditions.append("due_date IS NOT NULL AND due_date != '' AND due_date <= ?")
        params.append(due_before_clean)

    if due_after:
        due_after_clean = due_after.strip()
        if not is_valid_iso_date(due_after_clean):
            raise ValueError(
                f"Invalid due_after date format '{due_after}'. Expected YYYY-MM-DD."
            )
        conditions.append("due_date IS NOT NULL AND due_date != '' AND due_date >= ?")
        params.append(due_after_clean)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT * FROM academic_items
        {where_clause}
        ORDER BY
            CASE WHEN due_date IS NOT NULL AND due_date != '' THEN 0 ELSE 1 END ASC,
            due_date ASC,
            id DESC;
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, tuple(params))
        rows = cursor.fetchall()
        return [row_to_item_dict(r) for r in rows]


def update_academic_item(
    item_id: int,
    updates: dict[str, Any],
    db_path: Optional[Path | str] = None,
) -> Optional[dict[str, Any]]:
    """Safely update an existing academic item's editable fields.

    Parameters:
    - item_id: primary key ID of the task to update.
    - updates: dictionary of column names to new values.
    - db_path: optional database path override.

    Requirements enforced:
    - Only supplied editable fields are modified; unsupplied fields remain untouched.
    - Explicit None is supported for nullable fields (e.g. clearing due_date).
    - Immutable provenance fields (source_text, source_sender, source_timestamp,
      source_filename, created_at, id) are rejected with ValueError.
    - Automatically updates updated_at to the current UTC ISO timestamp.
    - Uses parameterized SQL queries to prevent SQL injection.
    - Returns None if item_id does not exist.
    """
    if not isinstance(item_id, int) or item_id <= 0:
        return None

    # Check for immutable provenance fields
    for field in updates:
        if field in IMMUTABLE_FIELDS:
            raise ValueError(
                f"Field '{field}' is immutable provenance data and cannot be modified."
            )

    # Validate that all update keys are known editable columns
    for field in updates:
        if field not in EDITABLE_COLUMNS:
            raise ValueError(f"Unknown or uneditable field '{field}'.")

    # If updates is empty, verify item exists and return it
    if not updates:
        return get_academic_item_by_id(item_id, db_path=db_path)

    processed: dict[str, Any] = {}

    if "title" in updates:
        val = updates["title"]
        if val is None or not str(val).strip():
            raise ValueError("Item title cannot be null or empty.")
        processed["title"] = str(val).strip()

    if "category" in updates:
        val = updates["category"]
        if val is None:
            raise ValueError("Item category cannot be null.")
        clean_cat = str(val).strip()
        if clean_cat not in ALLOWED_CATEGORIES:
            raise ValueError(
                f"Invalid category '{clean_cat}'. Allowed categories: {', '.join(sorted(ALLOWED_CATEGORIES))}"
            )
        processed["category"] = clean_cat

    if "status" in updates:
        val = updates["status"]
        if val is None:
            raise ValueError("Item status cannot be null.")
        clean_status = str(val).strip().lower()
        if clean_status not in ALLOWED_STATUSES:
            raise ValueError(
                f"Invalid status '{clean_status}'. Allowed statuses: {', '.join(sorted(ALLOWED_STATUSES))}"
            )
        processed["status"] = clean_status

    if "due_date" in updates:
        val = updates["due_date"]
        if val is not None:
            clean_date = str(val).strip()
            if not clean_date:
                processed["due_date"] = None
            elif not is_valid_iso_date(clean_date):
                raise ValueError(
                    f"Invalid due_date format '{clean_date}'. Expected YYYY-MM-DD."
                )
            else:
                processed["due_date"] = clean_date
        else:
            processed["due_date"] = None

    if "description" in updates:
        val = updates["description"]
        processed["description"] = str(val).strip() if val is not None else ""

    if "date_text" in updates:
        val = updates["date_text"]
        processed["date_text"] = str(val).strip() if val is not None else None

    if "date_type" in updates:
        val = updates["date_type"]
        processed["date_type"] = str(val).strip() if val is not None else "unknown"

    if "date_status" in updates:
        val = updates["date_status"]
        processed["date_status"] = str(val).strip() if val is not None else "not_found"

    if "review_required" in updates:
        val = updates["review_required"]
        processed["review_required"] = 1 if val else 0

    if "review_reasons" in updates:
        val = updates["review_reasons"]
        if val is None:
            processed["review_reasons"] = "[]"
        elif isinstance(val, str):
            processed["review_reasons"] = json.dumps([val])
        else:
            processed["review_reasons"] = json.dumps(list(val))

    now_iso = datetime.now(timezone.utc).isoformat()
    processed["updated_at"] = now_iso

    set_clauses = [f"{col} = ?" for col in processed]
    params = list(processed.values())
    params.append(item_id)

    update_sql = f"""
        UPDATE academic_items
        SET {', '.join(set_clauses)}
        WHERE id = ?;
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(update_sql, tuple(params))
        conn.commit()
        if cursor.rowcount == 0:
            return None

    return get_academic_item_by_id(item_id, db_path=db_path)


def update_academic_item_status(
    item_id: int,
    new_status: str,
    db_path: Optional[Path | str] = None,
) -> Optional[dict[str, Any]]:
    """Update task status ('pending', 'completed', 'dismissed') and timestamp."""
    clean_status = (new_status or "").strip().lower()
    if clean_status not in ALLOWED_STATUSES:
        raise ValueError(
            f"Invalid status '{new_status}'. Allowed statuses: {', '.join(sorted(ALLOWED_STATUSES))}"
        )

    return update_academic_item(item_id, {"status": clean_status}, db_path=db_path)


def delete_academic_item(
    item_id: int,
    db_path: Optional[Path | str] = None,
) -> bool:
    """Delete a saved academic item by ID. Returns True if deleted, False if not found."""
    delete_sql = "DELETE FROM academic_items WHERE id = ?;"
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(delete_sql, (item_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_confirmed_deadline_items(
    db_path: Optional[Path | str] = None,
) -> list[dict[str, Any]]:
    """Fetch saved items that have a confirmed due date and date_type='deadline'.

    Strictly excludes mentioned dates, event dates, unknown dates, or undated records.
    """
    query = """
        SELECT * FROM academic_items
        WHERE due_date IS NOT NULL
          AND due_date != ''
          AND date_type = 'deadline'
        ORDER BY due_date ASC, id ASC;
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        # Verify valid ISO date formatting
        confirmed = []
        for r in rows:
            item = row_to_item_dict(r)
            if is_valid_iso_date(item["due_date"]):
                confirmed.append(item)
        return confirmed


# Ensure default database schema is safely initialized on import
try:
    init_db()
except Exception:
    pass

