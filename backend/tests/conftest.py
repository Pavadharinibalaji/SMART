"""Pytest configuration and fixtures for SMART backend tests."""

import os
import pytest
from pathlib import Path
import sys

# Add backend directory to sys.path so modules can be imported directly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import config  # Ensures root .env is loaded before accessing environment variables
from database import init_db


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path, monkeypatch, request):
    """Automatically isolate tests with a clean temporary SQLite database unless running live Postgres tests."""
    is_postgres_test = "test_phase2_postgres" in request.node.nodeid
    if not is_postgres_test:
        # Guarantee SQLite regression tests run strictly on isolated SQLite DB
        monkeypatch.delenv("DATABASE_URL", raising=False)

    test_db_path = tmp_path / "test_smart.db"
    monkeypatch.setenv("SMART_DB_PATH", str(test_db_path))

    db_url = os.environ.get("DATABASE_URL", "").strip()
    is_live_pg = is_postgres_test and (db_url.startswith("postgresql://") or db_url.startswith("postgres://")) and "[" not in db_url

    if not is_live_pg:
        init_db(test_db_path)

    yield test_db_path
