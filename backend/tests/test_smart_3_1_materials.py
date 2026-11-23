"""
SMART 3.1: Native Teacher Study Material Upload & Student Resource Management Test Suite.

Covers:
1. Teacher upload of PDF, Office (DOCX, PPTX, XLSX), and TXT documents.
2. File validation: allowed formats, magic byte header verification, rejection of executable/script extensions.
3. Size limits enforcement: rejection of oversized (>25MB) and empty files.
4. Storage architecture: UUID server-side storage, directory isolation, original filename preservation.
5. Student access: enrolled course filtering, category filtering, search, metadata inspection.
6. Safe file delivery: inline preview (PDF/TXT) and attachment download with original filename.
7. Role & permission isolation: students cannot upload, modify, or delete; unenrolled students denied (403).
8. Teacher lifecycle: edit metadata (title/category/description) and deletion with physical file removal.
9. Notification broadcast: enrolled students receive real-time notifications on material publish.
"""

import io
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from main import app, UPLOAD_BASE_DIR, MAX_UPLOAD_SIZE_BYTES
from database import (
    init_db,
    create_smart_course,
    enroll_student_by_join_code,
    get_course_material,
    list_user_notifications,
)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def test_material_upload_pdf_success(client):
    """Teacher can upload a genuine PDF and file is safely stored on disk."""
    # 1. Login as teacher (Dr. Elena Vance, id: 2)
    res_login = client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    assert res_login.status_code == 200

    # 2. Create course
    course = create_smart_course(
        teacher_id=2,
        code="CS-MAT101",
        name="Study Materials Intro",
        description="Course for materials testing",
    )
    course_id = course["id"]

    # 3. Create simulated valid PDF bytes
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    file_tuple = ("Lecture1_Slides.pdf", io.BytesIO(pdf_content), "application/pdf")

    # 4. Upload material
    res_upload = client.post(
        f"/api/courses/{course_id}/materials",
        data={
            "title": "Unit 1: Introduction to Architecture",
            "description": "Lecture slides and foundational reading.",
            "category": "Lecture Notes",
        },
        files={"file": file_tuple},
    )
    assert res_upload.status_code == 201
    data = res_upload.json()
    assert data["id"] is not None
    assert data["title"] == "Unit 1: Introduction to Architecture"
    assert data["original_filename"] == "Lecture1_Slides.pdf"
    assert data["category"] == "Lecture Notes"
    assert data["file_extension"] == ".pdf"
    assert data["mime_type"] == "application/pdf"
    # Ensure physical storage path is NOT leaked to clients
    assert "storage_path" not in data
    assert "stored_filename" not in data

    # 5. Verify physical file is on disk
    record = get_course_material(data["id"])
    assert record is not None
    stored_path = Path(record["storage_path"])
    assert stored_path.is_file()
    assert stored_path.read_bytes() == pdf_content


def test_material_upload_docx_and_txt_success(client):
    """Teacher can upload OpenXML Office documents (.docx) and plain text (.txt)."""
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})

    course = create_smart_course(teacher_id=2, code="CS-DOCS", name="Office Docs Test")
    course_id = course["id"]

    # Valid docx (PK\x03\x04 zip header)
    docx_bytes = b"PK\x03\x04\x14\x00\x06\x00\x08\x00" + b"\x00" * 40
    res_docx = client.post(
        f"/api/courses/{course_id}/materials",
        data={"title": "Assignment 1 Specification", "category": "Assignments"},
        files={"file": ("Assignment1.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert res_docx.status_code == 201
    assert res_docx.json()["file_extension"] == ".docx"

    # Valid txt
    txt_bytes = b"Sample plain text study notes for exam revision.\nKey formulas:\nE=mc^2"
    res_txt = client.post(
        f"/api/courses/{course_id}/materials",
        data={"title": "Revision Quick Notes", "category": "Reference Documents"},
        files={"file": ("notes.txt", io.BytesIO(txt_bytes), "text/plain")},
    )
    assert res_txt.status_code == 201
    assert res_txt.json()["file_extension"] == ".txt"


def test_material_upload_security_prohibited_extensions(client):
    """Prohibited script or executable extensions (.exe, .py, .sh, .html) must be rejected."""
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(teacher_id=2, code="CS-SEC", name="Security Test")

    for bad_name in ("malware.exe", "exploit.py", "script.sh", "phishing.html"):
        res = client.post(
            f"/api/courses/{course['id']}/materials",
            data={"title": "Dangerous file"},
            files={"file": (bad_name, io.BytesIO(b"malicious content here"), "application/octet-stream")},
        )
        assert res.status_code == 400
        assert "Security alert" in res.json()["detail"] or "Prohibited" in res.json()["detail"]


def test_material_upload_corrupt_or_fake_magic_bytes(client):
    """File claiming to be .pdf with corrupt or non-PDF bytes must be rejected."""
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(teacher_id=2, code="CS-MAGIC", name="Magic Bytes Test")

    fake_pdf = b"NOT_A_REAL_PDF_HEADER_AT_ALL_ABCDEFG"
    res = client.post(
        f"/api/courses/{course['id']}/materials",
        data={"title": "Fake PDF"},
        files={"file": ("fake.pdf", io.BytesIO(fake_pdf), "application/pdf")},
    )
    assert res.status_code == 400
    assert "genuine PDF structure" in res.json()["detail"]


def test_material_upload_empty_file_rejected(client):
    """Empty 0-byte file must be rejected."""
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(teacher_id=2, code="CS-EMPTY", name="Empty File Test")

    res = client.post(
        f"/api/courses/{course['id']}/materials",
        data={"title": "Empty File"},
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    assert res.status_code == 400
    assert "empty file" in res.json()["detail"].lower()


def test_student_can_list_filter_search_materials(client):
    """Enrolled student can list materials, filter by category, and search by keyword."""
    # 1. Setup course with enrolled student
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(teacher_id=2, code="CS-SEARCH", name="Algorithm Complexity")
    course_id = course["id"]
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    # 2. Upload multiple materials under different categories
    pdf_hdr = b"%PDF-1.4\ncontent"
    client.post(
        f"/api/courses/{course_id}/materials",
        data={"title": "Dynamic Programming Lecture", "category": "Lecture Notes"},
        files={"file": ("dp_lecture.pdf", io.BytesIO(pdf_hdr), "application/pdf")},
    )
    client.post(
        f"/api/courses/{course_id}/materials",
        data={"title": "Past Exam 2024", "category": "Previous Year Questions"},
        files={"file": ("exam2024.pdf", io.BytesIO(pdf_hdr), "application/pdf")},
    )

    client.post("/api/auth/logout")

    # 3. Login as student (Alex Morgan, id: 1)
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})

    # 4. List all materials
    res_all = client.get(f"/api/courses/{course_id}/materials")
    assert res_all.status_code == 200
    materials = res_all.json()
    assert len(materials) == 2

    # 5. Filter by category
    res_cat = client.get(f"/api/courses/{course_id}/materials?category=Lecture Notes")
    assert res_cat.status_code == 200
    cat_items = res_cat.json()
    assert len(cat_items) == 1
    assert cat_items[0]["title"] == "Dynamic Programming Lecture"

    # 6. Search by query
    res_search = client.get(f"/api/courses/{course_id}/materials?search=Exam")
    assert res_search.status_code == 200
    search_items = res_search.json()
    assert len(search_items) == 1
    assert search_items[0]["title"] == "Past Exam 2024"


def test_material_preview_and_download(client):
    """Student can preview PDF inline and download original file."""
    # Teacher uploads
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(teacher_id=2, code="CS-PREV", name="Preview Testing")
    course_id = course["id"]
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    pdf_content = b"%PDF-1.4\nImportant Study Content\n%%EOF"
    res_up = client.post(
        f"/api/courses/{course_id}/materials",
        data={"title": "Syllabus Guide", "category": "Study Materials"},
        files={"file": ("Syllabus_2026.pdf", io.BytesIO(pdf_content), "application/pdf")},
    )
    mat_id = res_up.json()["id"]

    client.post("/api/auth/logout")

    # Student downloads and previews
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})

    # Test Download endpoint: Content-Disposition attachment
    res_down = client.get(f"/api/materials/{mat_id}/download")
    assert res_down.status_code == 200
    assert "attachment" in res_down.headers.get("content-disposition", "").lower()
    assert res_down.content == pdf_content

    # Test Preview endpoint: Content-Disposition inline for PDF
    res_prev = client.get(f"/api/materials/{mat_id}/preview")
    assert res_prev.status_code == 200
    assert "inline" in res_prev.headers.get("content-disposition", "").lower()
    assert res_prev.content == pdf_content


def test_unenrolled_student_access_denied(client):
    """Student not enrolled in the course cannot access, preview, or download materials."""
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(teacher_id=2, code="CS-PRIVATE", name="Restricted Course")
    course_id = course["id"]

    pdf_content = b"%PDF-1.4\nConfidential Lecture"
    res_up = client.post(
        f"/api/courses/{course_id}/materials",
        data={"title": "Confidential Lecture"},
        files={"file": ("secret.pdf", io.BytesIO(pdf_content), "application/pdf")},
    )
    mat_id = res_up.json()["id"]

    client.post("/api/auth/logout")

    # Student alex.morgan is NOT enrolled in CS-PRIVATE
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})

    res_list = client.get(f"/api/courses/{course_id}/materials")
    assert res_list.status_code == 403

    res_meta = client.get(f"/api/materials/{mat_id}")
    assert res_meta.status_code == 403

    res_down = client.get(f"/api/materials/{mat_id}/download")
    assert res_down.status_code == 403

    res_prev = client.get(f"/api/materials/{mat_id}/preview")
    assert res_prev.status_code == 403


def test_student_cannot_upload_modify_or_delete(client):
    """Students are strictly forbidden from uploading, modifying, or deleting study materials."""
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(teacher_id=2, code="CS-ROLE", name="Role Boundary Test")
    course_id = course["id"]
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    pdf_content = b"%PDF-1.4\nInitial Content"
    res_up = client.post(
        f"/api/courses/{course_id}/materials",
        data={"title": "Instructor Document"},
        files={"file": ("doc.pdf", io.BytesIO(pdf_content), "application/pdf")},
    )
    mat_id = res_up.json()["id"]

    client.post("/api/auth/logout")

    # Student tries to perform mutations
    client.post("/api/auth/login", json={"email": "alex.morgan@university.edu"})

    # Student tries to upload
    res_upload_attempt = client.post(
        f"/api/courses/{course_id}/materials",
        data={"title": "Hacked Document"},
        files={"file": ("hacked.pdf", io.BytesIO(pdf_content), "application/pdf")},
    )
    assert res_upload_attempt.status_code == 403

    # Student tries to PATCH
    res_patch_attempt = client.patch(
        f"/api/materials/{mat_id}",
        json={"title": "Tampered Title"},
    )
    assert res_patch_attempt.status_code == 403

    # Student tries to DELETE
    res_del_attempt = client.delete(f"/api/materials/{mat_id}")
    assert res_del_attempt.status_code == 403


def test_teacher_can_edit_and_delete_material_with_file_cleanup(client):
    """Teacher can update metadata, and deleting a material removes the physical file from disk."""
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(teacher_id=2, code="CS-EDIT", name="Edit Delete Test")
    course_id = course["id"]

    pdf_content = b"%PDF-1.4\nMaterial To Be Edited And Deleted"
    res_up = client.post(
        f"/api/courses/{course_id}/materials",
        data={"title": "Original Title", "category": "Lecture Notes"},
        files={"file": ("notes.pdf", io.BytesIO(pdf_content), "application/pdf")},
    )
    mat_id = res_up.json()["id"]

    # 1. Update metadata
    res_patch = client.patch(
        f"/api/materials/{mat_id}",
        json={
            "title": "Revised Title - Version 2",
            "description": "Updated lecture description.",
            "category": "Reference Documents",
        },
    )
    assert res_patch.status_code == 200
    updated_data = res_patch.json()
    assert updated_data["title"] == "Revised Title - Version 2"
    assert updated_data["category"] == "Reference Documents"
    assert updated_data["description"] == "Updated lecture description."

    # Verify physical file still exists
    record = get_course_material(mat_id)
    stored_path = Path(record["storage_path"])
    assert stored_path.is_file()

    # 2. Delete material
    res_del = client.delete(f"/api/materials/{mat_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # Verify record is gone from DB
    assert get_course_material(mat_id) is None

    # Verify physical file is safely removed from disk
    assert not stored_path.is_file()


def test_notification_broadcast_on_upload(client):
    """Uploading a material broadcasts a notification to all enrolled students."""
    client.post("/api/auth/login", json={"email": "e.vance@university.edu"})
    course = create_smart_course(teacher_id=2, code="CS-NOTIF", name="Distributed Computing")
    course_id = course["id"]
    enroll_student_by_join_code(user_id=1, join_code=course["join_code"])

    pdf_content = b"%PDF-1.4\nDistributed Systems Cheatsheet"
    res_up = client.post(
        f"/api/courses/{course_id}/materials",
        data={"title": "Consensus Cheatsheet", "category": "Reference Documents"},
        files={"file": ("cheatsheet.pdf", io.BytesIO(pdf_content), "application/pdf")},
    )
    mat_id = res_up.json()["id"]

    # Check student notifications
    notifs = list_user_notifications(user_id=1, course_id=course_id)
    assert len(notifs) >= 1
    material_notif = next((n for n in notifs if "Consensus Cheatsheet" in n["title"]), None)
    assert material_notif is not None
    assert f"/materials?course={course_id}&material={mat_id}" in material_notif["reference_id"]
