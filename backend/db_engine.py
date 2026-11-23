"""Dual-database engine connection and SQL compatibility layer for SMART.

Supports:
1. SQLite for local development (default when DATABASE_URL is unset).
2. PostgreSQL (Supabase) for production / cloud deployment (when DATABASE_URL is set).

Provides:
- Transparent SQL-aware placeholder scanning (? -> %s) preserving quotes and comments.
- Deterministic INSERT OR IGNORE -> ON CONFLICT DO NOTHING translation.
- Targeted RETURNING id injection and cursor.lastrowid emulation for autoincrement tables.
- Dual dictionary and indexed row access parity (row['col'], row[0], dict(row)).
- Full transaction context manager and commit/rollback semantics.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Iterator, Mapping, Optional, Sequence, Union

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_SQLITE_PATH = DEFAULT_DATA_DIR / "smart.db"

# Exactly the 12 tables whose helpers rely on cursor.lastrowid
LASTROWID_TABLES = {
    "academic_items",
    "users",
    "opportunities",
    "study_materials",
    "smart_courses",
    "course_invitations",
    "course_messages",
    "course_announcements",
    "course_polls",
    "notifications",
    "course_materials",
    "student_tracked_opportunities",
}

# Explicit conflict targets for INSERT OR IGNORE statements in SMART
CONFLICT_TARGETS: dict[str, str] = {
    "announcement_read_receipts": "(announcement_id, student_id)",
    "course_memberships": "(course_id, user_id)",
    "message_read_receipts": "(message_id, user_id)",
    "poll_votes": "(poll_id, user_id)",
    "student_opportunity_statuses": "(student_id, opportunity_id)",
    "users": "(email)",
    "google_accounts": "(email)",
    "classroom_courses": "(id)",
    "classroom_coursework": "(id)",
    "classroom_submissions": "(id)",
    "opportunities": "(id)",
    "smart_courses": "(code)",
    "schema_migrations": "(migration_name)",
}


# ==============================================================================
# SQL-Aware Lexical Scanner & Query Converter
# ==============================================================================

def convert_sqlite_to_postgres_sql(
    sql: str,
    params: Optional[Sequence[Any] | Mapping[str, Any]] = None,
) -> tuple[str, bool]:
    """Convert SQLite SQL syntax to PostgreSQL-compatible SQL.
    
    Performs:
    1. Lexical scanning of '?' placeholders outside strings, identifiers, and comments.
    2. Detection of bare 'RETURNING' clauses strictly outside string literals and comments.
    3. Verification of parameter count matching converted placeholders.
    4. Translation of verified 'INSERT OR IGNORE INTO <table>' to 'INSERT INTO ... ON CONFLICT ... DO NOTHING'.
    5. Detection and appending of 'RETURNING id' for verified lastrowid-dependent tables.

    Returns:
        (transformed_sql, returns_id_flag)
    """
    clean_sql = sql.strip()

    # --------------------------------------------------------------------------
    # 1. Lexical scan for '?' placeholders and bare RETURNING clause
    # --------------------------------------------------------------------------
    chars: list[str] = []
    i = 0
    n = len(clean_sql)
    placeholder_count = 0
    bare_words: list[str] = []
    current_word: list[str] = []

    state = "NORMAL"  # NORMAL, SINGLE_QUOTE, DOUBLE_QUOTE, LINE_COMMENT, BLOCK_COMMENT

    while i < n:
        ch = clean_sql[i]

        if state == "NORMAL":
            if ch.isalnum() or ch == "_":
                current_word.append(ch)
            else:
                if current_word:
                    bare_words.append("".join(current_word).upper())
                    current_word = []

            if ch == "'":
                state = "SINGLE_QUOTE"
                chars.append(ch)
            elif ch == '"':
                state = "DOUBLE_QUOTE"
                chars.append(ch)
            elif ch == "-" and i + 1 < n and clean_sql[i + 1] == "-":
                state = "LINE_COMMENT"
                chars.append(ch)
                chars.append("-")
                i += 1
            elif ch == "/" and i + 1 < n and clean_sql[i + 1] == "*":
                state = "BLOCK_COMMENT"
                chars.append(ch)
                chars.append("*")
                i += 1
            elif ch == "?":
                chars.append("%s")
                placeholder_count += 1
            else:
                chars.append(ch)

        elif state == "SINGLE_QUOTE":
            chars.append(ch)
            if ch == "'":
                if i + 1 < n and clean_sql[i + 1] == "'":
                    chars.append("'")
                    i += 1
                else:
                    state = "NORMAL"

        elif state == "DOUBLE_QUOTE":
            chars.append(ch)
            if ch == '"':
                if i + 1 < n and clean_sql[i + 1] == '"':
                    chars.append('"')
                    i += 1
                else:
                    state = "NORMAL"

        elif state == "LINE_COMMENT":
            chars.append(ch)
            if ch == "\n":
                state = "NORMAL"

        elif state == "BLOCK_COMMENT":
            chars.append(ch)
            if ch == "*" and i + 1 < n and clean_sql[i + 1] == "/":
                chars.append("/")
                i += 1
                state = "NORMAL"

        i += 1

    if current_word:
        bare_words.append("".join(current_word).upper())

    converted_sql = "".join(chars)
    has_returning_clause = "RETURNING" in bare_words

    # Verify parameter count when sequence params are passed
    if params is not None and isinstance(params, (list, tuple)):
        if len(params) != placeholder_count:
            raise ValueError(
                f"SQL parameter count mismatch: query contains {placeholder_count} '?' "
                f"placeholders, but {len(params)} parameters were supplied."
            )

    # --------------------------------------------------------------------------
    # 2. Translate INSERT OR IGNORE
    # --------------------------------------------------------------------------
    insert_ignore_match = re.search(
        r"\bINSERT\s+OR\s+IGNORE\s+INTO\s+([a-zA-Z0-9_]+)",
        converted_sql,
        re.IGNORECASE,
    )
    if insert_ignore_match:
        table_name = insert_ignore_match.group(1).lower()
        target = CONFLICT_TARGETS.get(table_name)
        conflict_clause = f" ON CONFLICT {target} DO NOTHING" if target else " ON CONFLICT DO NOTHING"
        
        # Replace prefix
        converted_sql = re.sub(
            r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
            "INSERT INTO",
            converted_sql,
            count=1,
            flags=re.IGNORECASE,
        )
        
        # Append conflict clause before trailing semicolon if any
        if converted_sql.endswith(";"):
            converted_sql = converted_sql[:-1].rstrip() + conflict_clause + ";"
        else:
            converted_sql = converted_sql + conflict_clause

    # --------------------------------------------------------------------------
    # 3. Check if table requires RETURNING id for lastrowid emulation
    # --------------------------------------------------------------------------
    returns_id = False
    insert_match = re.search(
        r"\bINSERT\s+INTO\s+([a-zA-Z0-9_]+)",
        converted_sql,
        re.IGNORECASE,
    )
    if insert_match:
        table_name = insert_match.group(1).lower()
        if table_name in LASTROWID_TABLES:
            if not has_returning_clause:
                returns_id = True
                if converted_sql.endswith(";"):
                    converted_sql = converted_sql[:-1].rstrip() + " RETURNING id;"
                else:
                    converted_sql = converted_sql + " RETURNING id"

    return converted_sql, returns_id


# ==============================================================================
# Dual-Access Row Facade for PostgreSQL
# ==============================================================================

class PostgresRowWrapper(Mapping[str, Any]):
    """Row wrapper providing 100% sqlite3.Row interface parity on PostgreSQL.
    
    Supports:
    - row['column_name'] and row['COLUMN_NAME'] (case-insensitive column lookup)
    - row[0] (integer column index lookup)
    - dict(row) (converts to dict mapping column names to values)
    - 'column_name' in row
    - row.keys(), row.values(), row.items(), row.get()
    """
    __slots__ = ("_data", "_keys", "_key_indices")

    def __init__(self, data: Sequence[Any], keys: Sequence[str]):
        self._data = tuple(data)
        self._keys = tuple(keys)
        self._key_indices = {k.lower(): i for i, k in enumerate(keys)}

    def __getitem__(self, item: Union[int, str]) -> Any:
        if isinstance(item, int):
            return self._data[item]
        idx = self._key_indices.get(str(item).lower())
        if idx is not None:
            return self._data[idx]
        raise KeyError(item)

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, str):
            return item.lower() in self._key_indices
        return False

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._data)

    def keys(self) -> Sequence[str]:
        return self._keys

    def values(self) -> Sequence[Any]:
        return self._data

    def items(self) -> Iterator[tuple[str, Any]]:
        return zip(self._keys, self._data)

    def get(self, key: str, default: Any = None) -> Any:
        idx = self._key_indices.get(key.lower())
        if idx is not None:
            return self._data[idx]
        return default

    def __repr__(self) -> str:
        return f"<PostgresRow {dict(self.items())}>"


# ==============================================================================
# PostgreSQL Connection and Cursor Facades
# ==============================================================================

class PostgresCursorWrapper:
    """Cursor wrapper that executes converted SQL and wraps result rows."""

    def __init__(self, pg_cursor: Any):
        self._cursor = pg_cursor
        self._lastrowid: Optional[int] = None
        self._rowcount: int = -1

    @property
    def lastrowid(self) -> Optional[int]:
        return self._lastrowid

    @property
    def rowcount(self) -> int:
        return self._rowcount

    @property
    def description(self) -> Any:
        return self._cursor.description

    def execute(
        self,
        sql: str,
        params: Optional[Sequence[Any] | Mapping[str, Any]] = None,
    ) -> PostgresCursorWrapper:
        """Translate SQL syntax and execute with parameters."""
        conv_sql, returns_id = convert_sqlite_to_postgres_sql(sql, params)
        
        self._cursor.execute(conv_sql, params)
        self._rowcount = self._cursor.rowcount

        if returns_id:
            row = self._cursor.fetchone()
            if row:
                # Value may be integer or tuple
                self._lastrowid = row[0] if isinstance(row, (tuple, list)) else (row.get("id") if isinstance(row, dict) else row)
            else:
                self._lastrowid = None
        else:
            self._lastrowid = None

        return self

    def executemany(
        self,
        sql: str,
        param_seq: Iterable[Sequence[Any] | Mapping[str, Any]],
    ) -> PostgresCursorWrapper:
        conv_sql, _ = convert_sqlite_to_postgres_sql(sql, None)
        self._cursor.executemany(conv_sql, param_seq)
        self._rowcount = self._cursor.rowcount
        return self

    def fetchone(self) -> Optional[PostgresRowWrapper]:
        row = self._cursor.fetchone()
        if row is None:
            return None
        col_names = [desc[0] for desc in self._cursor.description]
        return PostgresRowWrapper(row, col_names)

    def fetchall(self) -> list[PostgresRowWrapper]:
        rows = self._cursor.fetchall()
        if not rows:
            return []
        col_names = [desc[0] for desc in self._cursor.description]
        return [PostgresRowWrapper(r, col_names) for r in rows]

    def fetchmany(self, size: int = 1) -> list[PostgresRowWrapper]:
        rows = self._cursor.fetchmany(size)
        if not rows:
            return []
        col_names = [desc[0] for desc in self._cursor.description]
        return [PostgresRowWrapper(r, col_names) for r in rows]

    def close(self) -> None:
        self._cursor.close()

    def __iter__(self) -> Iterator[PostgresRowWrapper]:
        while True:
            row = self.fetchone()
            if row is None:
                break
            yield row


class PostgresConnectionWrapper:
    """Connection facade matching sqlite3.Connection behavior for SMART database helpers."""

    def __init__(self, raw_conn: Any):
        self._conn = raw_conn
        self._in_context = False

    def cursor(self) -> PostgresCursorWrapper:
        return PostgresCursorWrapper(self._conn.cursor())

    def execute(
        self,
        sql: str,
        params: Optional[Sequence[Any] | Mapping[str, Any]] = None,
    ) -> PostgresCursorWrapper:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> PostgresConnectionWrapper:
        self._in_context = True
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._in_context = False
        if exc_type is not None:
            self._conn.rollback()
        else:
            self._conn.commit()


# ==============================================================================
# Engine Factory & Dispatcher
# ==============================================================================

def get_engine_type() -> str:
    """Detect configured engine: 'postgresql' or 'sqlite'."""
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        return "sqlite"
    
    if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
        return "postgresql"

    raise ValueError(
        f"Unsupported DATABASE_URL configuration: scheme must be postgresql:// or postgres://, "
        f"got '{db_url.split('://', 1)[0] if '://' in db_url else db_url}'"
    )


def create_db_connection(
    db_path: Optional[Path | str] = None,
    timeout: float = 15.0,
) -> Any:
    """Establish and return an active database connection facade.
    
    Routes to PostgreSQL if DATABASE_URL is configured; otherwise SQLite.
    """
    engine_type = get_engine_type()

    if engine_type == "postgresql":
        db_url = os.environ["DATABASE_URL"].strip()
        if psycopg is None:
            raise ImportError(
                "PostgreSQL driver 'psycopg' (v3) is not installed. "
                "Install psycopg[binary] to use PostgreSQL with SMART."
            )
        # connect_timeout is the standard libpq / Psycopg 3 parameter (integer seconds).
        # prepare_threshold=None disables named server-side PREPARE statements,
        # ensuring 100% compatibility with Supabase transaction pooling (PgBouncer port 6543).
        raw_conn = psycopg.connect(
            db_url,
            connect_timeout=int(timeout),
            prepare_threshold=None,
        )
        return PostgresConnectionWrapper(raw_conn)

    # SQLite Mode
    resolved_path = Path(db_path) if db_path else Path(os.environ.get("SMART_DB_PATH", DEFAULT_SQLITE_PATH))
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved_path), timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        pass

    return conn
