"""Pytest configuration and fixtures for SMART backend tests."""

import os
import pytest
from pathlib import Path

# Add backend directory to sys.path so modules can be imported directly
import sys
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from database import init_db


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path, monkeypatch):
    """Automatically isolate every test with a clean temporary SQLite database."""
    test_db_path = tmp_path / "test_smart.db"
    monkeypatch.setenv("SMART_DB_PATH", str(test_db_path))
    init_db(test_db_path)
    yield test_db_path
