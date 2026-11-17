"""API integration tests for FastAPI endpoints (backend/main.py)."""

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_health_check_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["project"] == "SMART"
    assert "message" in data


def test_upload_non_txt_file_rejected():
    files = {"file": ("chat.pdf", b"%PDF-1.4...", "application/pdf")}
    response = client.post("/api/extract-academic", files=files)
    assert response.status_code == 400
    assert "Please upload a WhatsApp .txt export" in response.json()["detail"]


def test_upload_empty_file_rejected():
    files = {"file": ("empty.txt", b"", "text/plain")}
    response = client.post("/api/extract-academic", files=files)
    assert response.status_code == 400
    assert "The uploaded file is empty" in response.json()["detail"]


def test_upload_whitespace_only_file_rejected():
    files = {"file": ("whitespace.txt", b"   \n\n  \t  ", "text/plain")}
    response = client.post("/api/extract-academic", files=files)
    assert response.status_code == 400
    assert "The uploaded file is empty" in response.json()["detail"]


def test_upload_oversized_file_rejected():
    # 5 MB + 10 bytes
    large_content = b"A" * (5 * 1024 * 1024 + 10)
    files = {"file": ("oversized.txt", io.BytesIO(large_content), "text/plain")}
    response = client.post("/api/extract-academic", files=files)
    assert response.status_code == 413
    assert "File is too large" in response.json()["detail"]


def test_upload_unrecognized_format_rejected():
    unrecognized = b"Hello world\nThis is not a whatsapp chat log at all\nNo dates here"
    files = {"file": ("chat.txt", io.BytesIO(unrecognized), "text/plain")}
    response = client.post("/api/extract-academic", files=files)
    assert response.status_code == 422
    assert "No recognised WhatsApp messages were found" in response.json()["detail"]


def test_extract_academic_with_sample_fixture():
    sample_file = FIXTURES_DIR / "sample_chat.txt"
    assert sample_file.exists(), "Sample chat fixture must exist"

    with open(sample_file, "rb") as f:
        files = {"file": ("sample_chat.txt", f, "text/plain")}
        response = client.post("/api/extract-academic", files=files)

    assert response.status_code == 200
    data = response.json()

    assert data["filename"] == "sample_chat.txt"
    assert data["total_messages"] > 0
    assert data["total_items"] > 0
    assert isinstance(data["items"], list)
    assert data["review_required_count"] >= 1
    assert "Assignment" in data["category_counts"]

    # Verify candidate item fields
    for item in data["items"]:
        assert "item_id" in item
        assert "category" in item
        assert "title" in item
        assert "source_text" in item
        assert "source_sender" in item
        assert "source_timestamp" in item
        assert "extraction_method" in item
        assert item["extraction_method"] == "rules"
        assert "review_required" in item
        assert "review_reasons" in item


def test_cors_headers_present():
    response = client.options(
        "/api/extract-academic",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
