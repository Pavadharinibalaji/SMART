"""Google OAuth, Gmail & Classroom Integration Service for SMART 2.1.

Implements:
1. Google OAuth 2.0 authorization URL generation, CSRF state verification, and token exchange.
2. Token encryption via security.py and automatic refresh-token renewal.
3. Read-only Gmail API integration (messages, attachment metadata, competition extraction).
4. Read-only Classroom API integration (courses, coursework, student submissions).
5. Explicit error reporting for Workspace admin restrictions and permission denials.
6. Clearly labeled demo/sample fallback for offline local demonstration.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from typing import Any, Optional
import urllib.parse

import httpx

from competition_extractor import extract_competition_opportunity
from database import (
    get_google_account,
    save_classroom_course,
    save_classroom_coursework,
    save_classroom_submission,
    save_google_account,
    save_opportunity,
    save_study_material,
    update_student_opportunity_status,
)
from extractor import extract_academic_items
from security import (
    decrypt_token,
    encrypt_token,
    generate_oauth_state,
    validate_oauth_state,
)
from source_adapters import GmailAdapter

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_MESSAGES_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
CLASSROOM_COURSES_ENDPOINT = "https://classroom.googleapis.com/v1/courses"

READONLY_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
]


def get_oauth_credentials() -> tuple[str, str]:
    """Retrieve Google OAuth Client ID and Secret from environment."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    return client_id, client_secret


def is_live_google_configured() -> bool:
    """Return True if both Google Client ID and Secret are configured."""
    cid, sec = get_oauth_credentials()
    return bool(cid and sec)


def build_authorization_url(
    role: str = "student",
    redirect_uri: Optional[str] = None,
) -> dict[str, Any]:
    """Generate the Google OAuth 2.0 authorization URL with CSRF state token."""
    client_id, _ = get_oauth_credentials()
    clean_redirect = (redirect_uri or os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5173/auth/callback")).strip()

    if not client_id:
        return {
            "configured": False,
            "auth_url": None,
            "message": "Google Client ID is not configured in environment (GOOGLE_CLIENT_ID). Live OAuth requires client credentials.",
        }

    state = generate_oauth_state(role=role, redirect_uri=clean_redirect)
    params = {
        "client_id": client_id,
        "redirect_uri": clean_redirect,
        "response_type": "code",
        "scope": " ".join(READONLY_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    url = f"{GOOGLE_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"
    return {
        "configured": True,
        "auth_url": url,
        "state": state,
        "redirect_uri": clean_redirect,
    }


async def exchange_code_for_tokens(code: str, state: str) -> dict[str, Any]:
    """Validate OAuth CSRF state, exchange authorization code for tokens, and persist account."""
    state_payload = validate_oauth_state(state)
    if not state_payload:
        raise ValueError("Invalid or expired OAuth state parameter. Possible CSRF attempt.")

    client_id, client_secret = get_oauth_credentials()
    if not client_id or not client_secret:
        raise ValueError("Google OAuth credentials are not configured on the server.")

    redirect_uri = state_payload.get("redirect_uri") or os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5173/auth/callback")
    role = state_payload.get("role", "student")

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Token Exchange
        token_resp = await client.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise ValueError(f"Google Token Exchange failed ({token_resp.status_code}): {token_resp.text}")

        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in", 3600)
        expiry_iso = datetime.now(timezone.utc).isoformat()

        # User Info
        user_resp = await client.get(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_resp.status_code != 200:
            raise ValueError(f"Failed to fetch Google profile: {user_resp.text}")

        profile = user_resp.json()
        email = profile.get("email")
        if not email:
            raise ValueError("Google profile did not return an email address.")

        if not is_secure_persistence_configured():
            raise ValueError(
                "Secure token persistence is not configured: SMART_TOKEN_ENCRYPTION_KEY environment variable "
                "is absent. Persistent live OAuth storage is disabled to prevent unencrypted or ephemeral storage."
            )

        account_record = {
            "email": email,
            "name": profile.get("name", email.split("@")[0]),
            "picture": profile.get("picture"),
            "encrypted_access_token": encrypt_token(access_token),
            "encrypted_refresh_token": encrypt_token(refresh_token) if refresh_token else None,
            "token_expiry": expiry_iso,
            "scopes": tokens.get("scope", " ".join(READONLY_SCOPES)),
            "role": role,
            "is_demo": 0,
        }
        saved = save_google_account(account_record)
        return saved


async def get_valid_access_token(account: dict[str, Any]) -> str:
    """Decrypt access token or refresh it if expired."""
    enc_access = account.get("encrypted_access_token")
    enc_refresh = account.get("encrypted_refresh_token")

    if not enc_access and not enc_refresh:
        raise ValueError("No OAuth tokens stored for this account.")

    # Try existing decrypted access token
    if enc_access:
        try:
            return decrypt_token(enc_access)
        except Exception:
            pass

    # Attempt refresh
    if enc_refresh:
        raw_refresh = decrypt_token(enc_refresh)
        client_id, client_secret = get_oauth_credentials()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={
                    "refresh_token": raw_refresh,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                new_access = data.get("access_token")
                account["encrypted_access_token"] = encrypt_token(new_access)
                save_google_account(account)
                return new_access

    raise ValueError("Token is expired and could not be refreshed. Please reconnect your Google account.")


# ==============================================================================
# Live Gmail API Synchronization
# ==============================================================================


async def sync_live_gmail(account: dict[str, Any], max_messages: int = 15) -> dict[str, Any]:
    """Retrieve messages from authenticated user's Gmail and extract academic items & competitions."""
    token = await get_valid_access_token(account)
    email_address = account.get("email", "")

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    query = "subject:(assignment OR exam OR test OR project OR hackathon OR competition OR contest OR submission OR deadline OR internal)"

    async with httpx.AsyncClient(timeout=20.0) as client:
        list_resp = await client.get(
            GMAIL_MESSAGES_ENDPOINT,
            headers=headers,
            params={"q": query, "maxResults": max_messages},
        )
        if list_resp.status_code == 403:
            raise PermissionError("Gmail API access was denied by Google or your Google Workspace administrator.")
        if list_resp.status_code != 200:
            raise ValueError(f"Gmail message search failed ({list_resp.status_code}): {list_resp.text}")

        data = list_resp.json()
        msg_items = data.get("messages", [])
        if not msg_items:
            now_iso = datetime.now(timezone.utc).isoformat()
            account["last_sync_gmail"] = now_iso
            save_google_account(account)
            return {"synced_count": 0, "extracted_tasks": 0, "extracted_competitions": 0, "is_demo": False}

        raw_emails: list[dict[str, Any]] = []
        for it in msg_items:
            mid = it.get("id")
            detail_resp = await client.get(f"{GMAIL_MESSAGES_ENDPOINT}/{mid}", headers=headers)
            if detail_resp.status_code == 200:
                raw_emails.append(detail_resp.json())

    # Parse and extract
    adapter = GmailAdapter()
    source_messages = adapter.parse(raw_emails)
    message_dicts = [m.to_dict() for m in source_messages]

    # Academic tasks extraction
    extracted_items = extract_academic_items(message_dicts)

    # Competitions extraction
    opp_count = 0
    mat_count = 0
    for sm in source_messages:
        # Check for competition opportunity
        opp = extract_competition_opportunity(
            text=sm.source_text,
            source_id=sm.source_id,
            source_sender=sm.source_sender,
            source_timestamp=sm.source_timestamp,
            source_type="gmail",
            is_demo=False,
        )
        if opp:
            saved_opp = save_opportunity(opp)
            update_student_opportunity_status(
                student_id=email_address,
                opportunity_id=saved_opp["id"],
                status="discovered",
                evidence_notes="Auto-discovered via Gmail academic sync.",
            )
            opp_count += 1

        # Check for attachments in raw email metadata
        for em in raw_emails:
            if em.get("id") == sm.source_id:
                payload = em.get("payload", {})
                parts = payload.get("parts", [])
                for p in parts:
                    fname = p.get("filename")
                    if fname and len(fname) > 2:
                        body_info = p.get("body", {})
                        save_study_material({
                            "title": fname,
                            "file_name": fname,
                            "file_type": p.get("mimeType", "application/octet-stream"),
                            "file_size": body_info.get("size", 0),
                            "file_url": f"https://mail.google.com/mail/u/0/#inbox/{sm.source_id}",
                            "source_type": "gmail_attachment",
                            "source_id": sm.source_id,
                            "uploaded_by": sm.source_sender,
                            "is_demo": 0,
                        })
                        mat_count += 1

    now_iso = datetime.now(timezone.utc).isoformat()
    account["last_sync_gmail"] = now_iso
    save_google_account(account)

    return {
        "synced_count": len(source_messages),
        "extracted_tasks": len(extracted_items),
        "extracted_competitions": opp_count,
        "extracted_materials": mat_count,
        "last_sync": now_iso,
        "is_demo": False,
    }


# ==============================================================================
# Live Google Classroom API Synchronization
# ==============================================================================


async def sync_live_classroom(account: dict[str, Any]) -> dict[str, Any]:
    """Retrieve courses, coursework, and submissions from Google Classroom API."""
    token = await get_valid_access_token(account)
    email_address = account.get("email", "")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async with httpx.AsyncClient(timeout=25.0) as client:
        # 1. Fetch Courses
        courses_resp = await client.get(
            CLASSROOM_COURSES_ENDPOINT,
            headers=headers,
            params={"courseStates": "ACTIVE"},
        )
        if courses_resp.status_code == 403:
            raise PermissionError("Google Classroom API access was denied by Google or your Google Workspace administrator.")
        if courses_resp.status_code != 200:
            raise ValueError(f"Failed to fetch Classroom courses ({courses_resp.status_code}): {courses_resp.text}")

        courses = courses_resp.json().get("courses", [])
        saved_course_count = 0
        saved_coursework_count = 0
        saved_sub_count = 0

        for c in courses:
            cid = c.get("id")
            # Determine role: if ownerId is me or teacherFolder exists, teacher; else student
            role = account.get("role", "student")
            course_record = {
                "id": cid,
                "name": c.get("name"),
                "section": c.get("section"),
                "description_heading": c.get("descriptionHeading"),
                "room": c.get("room"),
                "owner_id": c.get("ownerId"),
                "user_role": role,
                "alternate_link": c.get("alternateLink"),
                "is_demo": 0,
            }
            save_classroom_course(course_record)
            saved_course_count += 1

            # 2. Fetch Coursework for course
            cw_resp = await client.get(
                f"{CLASSROOM_COURSES_ENDPOINT}/{cid}/courseWork",
                headers=headers,
            )
            if cw_resp.status_code == 200:
                cworks = cw_resp.json().get("courseWork", [])
                for cw in cworks:
                    cw_id = cw.get("id")
                    due = cw.get("dueDate", {})
                    time_dict = cw.get("dueTime", {})
                    due_date_str = None
                    if due.get("year") and due.get("month") and due.get("day"):
                        due_date_str = f"{due['year']:04d}-{due['month']:02d}-{due['day']:02d}"
                    due_time_str = None
                    if time_dict.get("hours") is not None:
                        due_time_str = f"{time_dict['hours']:02d}:{time_dict.get('minutes', 0):02d}"

                    cw_record = {
                        "id": cw_id,
                        "course_id": cid,
                        "title": cw.get("title"),
                        "description": cw.get("description"),
                        "due_date": due_date_str,
                        "due_time": due_time_str,
                        "max_points": cw.get("maxPoints"),
                        "work_type": cw.get("workType", "ASSIGNMENT"),
                        "state": cw.get("state", "PUBLISHED"),
                        "alternate_link": cw.get("alternateLink"),
                        "is_demo": 0,
                    }
                    save_classroom_coursework(cw_record)
                    saved_coursework_count += 1

                    # 3. Fetch submissions (if teacher or student)
                    sub_url = f"{CLASSROOM_COURSES_ENDPOINT}/{cid}/courseWork/{cw_id}/studentSubmissions"
                    sub_params = {}
                    if role == "student":
                        sub_params["userId"] = "me"
                    sub_resp = await client.get(sub_url, headers=headers, params=sub_params)
                    if sub_resp.status_code == 200:
                        subs = sub_resp.json().get("studentSubmissions", [])
                        for s in subs:
                            sub_rec = {
                                "id": s.get("id"),
                                "course_id": cid,
                                "coursework_id": cw_id,
                                "student_id": email_address,
                                "student_name": account.get("name", email_address),
                                "state": s.get("state", "NEW"),
                                "assigned_grade": s.get("assignedGrade"),
                                "late": 1 if s.get("late") else 0,
                                "alternate_link": s.get("alternateLink"),
                                "is_demo": 0,
                            }
                            save_classroom_submission(sub_rec)
                            saved_sub_count += 1

    now_iso = datetime.now(timezone.utc).isoformat()
    account["last_sync_classroom"] = now_iso
    save_google_account(account)

    return {
        "courses_count": saved_course_count,
        "coursework_count": saved_coursework_count,
        "submissions_count": saved_sub_count,
        "last_sync": now_iso,
        "is_demo": False,
    }


# ==============================================================================
# Transparent Demo / Sample Ingestion Layer (Offline Demonstration)
# ==============================================================================


DEMO_OPPORTUNITIES = [
    {
        "name": "Smart India Hackathon 2026",
        "organizer": "Ministry of Education & AICTE",
        "description": "National level hackathon for engineering and science students to solve real-world problems posted by ministries and industries.",
        "eligibility": "All enrolled college students (teams of 6).",
        "registration_deadline": "2026-12-15",
        "event_date": "2026-12-28",
        "registration_url": "https://sih.gov.in/register",
        "source_type": "gmail",
        "source_id": "demo_sih_2026",
        "source_sender": "Hackathon Coordinator <hackathon@univ.edu>",
        "source_timestamp": "2026-11-20 09:30",
        "evidence_text": "Smart India Hackathon 2026 registration deadline is 2026-12-15. Open to all students.",
        "confidence": "HIGH",
        "review_status": "confirmed",
        "is_demo": 1,
    },
    {
        "name": "ACM Inter-College Coding Cup",
        "organizer": "ACM Student Chapter",
        "description": "Annual competitive programming contest covering dynamic programming, graph algorithms, and data structures.",
        "eligibility": "Undergraduate students, individual participation.",
        "registration_deadline": "2026-12-05",
        "event_date": "2026-12-10",
        "registration_url": "https://acm.univ.edu/coding-cup-2026",
        "source_type": "gmail",
        "source_id": "demo_acm_cup",
        "source_sender": "ACM Faculty Sponsor <acm_lead@univ.edu>",
        "source_timestamp": "2026-11-21 14:00",
        "evidence_text": "ACM Inter-College Coding Cup last date to register is 2026-12-05.",
        "confidence": "HIGH",
        "review_status": "confirmed",
        "is_demo": 1,
    },
    {
        "name": "Google Solution Challenge 2026",
        "organizer": "Google Developer Student Clubs",
        "description": "Build solutions for the UN Sustainable Development Goals using Google Cloud, Android, and Flutter technologies.",
        "eligibility": "College students members of GDSC chapters.",
        "registration_deadline": "2026-12-20",
        "event_date": "2027-01-15",
        "registration_url": "https://developers.google.com/community/gdsc-solution-challenge",
        "source_type": "gmail",
        "source_id": "demo_gdsc_challenge",
        "source_sender": "GDSC Faculty Lead <gdsc@univ.edu>",
        "source_timestamp": "2026-11-22 10:15",
        "evidence_text": "Google Solution Challenge 2026 submission window closes on 2026-12-20.",
        "confidence": "HIGH",
        "review_status": "confirmed",
        "is_demo": 1,
    },
]

DEMO_COURSES = [
    {
        "id": "demo_cs401",
        "name": "CS401: Distributed Systems",
        "section": "Section A",
        "description_heading": "Consensus, Raft, Paxos & Scalable Architectures",
        "room": "Hall 301",
        "owner_id": "e.vance@university.edu",
        "teacher_email": "e.vance@university.edu",
        "user_role": "teacher",
        "alternate_link": "https://classroom.google.com/c/demo_cs401",
        "is_demo": 1,
    },
    {
        "id": "demo_cs302",
        "name": "CS302: Compiler Design",
        "section": "Section B",
        "description_heading": "Lexical Analysis, LL/LR Parsers, Code Generation",
        "room": "Lab 4",
        "owner_id": "e.vance@university.edu",
        "teacher_email": "e.vance@university.edu",
        "user_role": "teacher",
        "alternate_link": "https://classroom.google.com/c/demo_cs302",
        "is_demo": 1,
    },
    {
        "id": "demo_cs505_teach",
        "name": "CS505: Cloud Computing Lab",
        "section": "Graduate Section",
        "description_heading": "Kubernetes, Microservices & Serverless",
        "room": "Cloud Lab 2",
        "owner_id": "e.vance@university.edu",
        "teacher_email": "e.vance@university.edu",
        "user_role": "teacher",
        "alternate_link": "https://classroom.google.com/c/demo_cs505_teach",
        "is_demo": 1,
    },
]

DEMO_COURSEWORK = [
    {
        "id": "demo_cw_cs401_lab2",
        "course_id": "demo_cs401",
        "title": "Lab 2: Raft Leader Election Implementation",
        "description": "Implement consensus leader election and heartbeats in Python or Go.",
        "due_date": "2026-12-02",
        "due_time": "23:59",
        "max_points": 100,
        "work_type": "ASSIGNMENT",
        "state": "PUBLISHED",
        "alternate_link": "https://classroom.google.com/c/demo_cs401/a/lab2",
        "is_demo": 1,
    },
    {
        "id": "demo_cw_cs302_parser",
        "course_id": "demo_cs302",
        "title": "Assignment 3: LALR(1) Parser Table Generator",
        "description": "Construct grammar parsing tables and verify conflicts.",
        "due_date": "2026-11-30",
        "due_time": "17:00",
        "max_points": 50,
        "work_type": "ASSIGNMENT",
        "state": "PUBLISHED",
        "alternate_link": "https://classroom.google.com/c/demo_cs302/a/asg3",
        "is_demo": 1,
    },
    {
        "id": "demo_cw_cs505_k8s",
        "course_id": "demo_cs505_teach",
        "title": "Lab 1: Docker Swarm vs Kubernetes Deployment",
        "description": "Deploy microservices stack with auto-scaling and ingress.",
        "due_date": "2026-12-08",
        "due_time": "23:59",
        "max_points": 100,
        "work_type": "ASSIGNMENT",
        "state": "PUBLISHED",
        "alternate_link": "https://classroom.google.com/c/demo_cs505_teach/a/lab1",
        "is_demo": 1,
    },
]

DEMO_SUBMISSIONS = [
    {
        "id": "demo_sub_1",
        "course_id": "demo_cs401",
        "coursework_id": "demo_cw_cs401_lab2",
        "student_id": "alex.morgan@university.edu",
        "student_name": "Alex Morgan",
        "state": "TURNED_IN",
        "assigned_grade": None,
        "late": 0,
        "alternate_link": "https://classroom.google.com/c/demo_cs401/s/1",
        "is_demo": 1,
    },
    {
        "id": "demo_sub_2",
        "course_id": "demo_cs302",
        "coursework_id": "demo_cw_cs302_parser",
        "student_id": "alex.morgan@university.edu",
        "student_name": "Alex Morgan",
        "state": "RETURNED",
        "assigned_grade": 48.0,
        "late": 0,
        "alternate_link": "https://classroom.google.com/c/demo_cs302/s/2",
        "is_demo": 1,
    },
    {
        "id": "demo_sub_teach_1",
        "course_id": "demo_cs505_teach",
        "coursework_id": "demo_cw_cs505_k8s",
        "student_id": "riya.sharma@univ.edu",
        "student_name": "Riya Sharma",
        "state": "TURNED_IN",
        "assigned_grade": 92.0,
        "late": 0,
        "alternate_link": "https://classroom.google.com/c/demo_cs505_teach/s/3",
        "is_demo": 1,
    },
    {
        "id": "demo_sub_teach_2",
        "course_id": "demo_cs401",
        "coursework_id": "demo_cw_cs401_lab2",
        "student_id": "marcus.chen@univ.edu",
        "student_name": "Marcus Chen",
        "state": "RETURNED",
        "assigned_grade": 95.0,
        "late": 0,
        "alternate_link": "https://classroom.google.com/c/demo_cs401/s/2",
        "is_demo": 1,
    },
]

DEMO_STUDY_MATERIALS = [
    {
        "title": "CS401 Lecture 8 - Consensus & Raft Slides.pdf",
        "file_name": "CS401_Lec8_Raft.pdf",
        "file_type": "application/pdf",
        "file_size": 2450000,
        "file_url": "https://classroom.google.com/c/demo_cs401/m/raft_slides",
        "source_type": "classroom_material",
        "source_id": "demo_mat_1",
        "course_id": "demo_cs401",
        "course_name": "CS401: Distributed Systems",
        "uploaded_by": "Prof. Rao",
        "is_demo": 1,
    },
    {
        "title": "Smart India Hackathon Problem Statements 2026.pdf",
        "file_name": "SIH_2026_Problem_Statements.pdf",
        "file_type": "application/pdf",
        "file_size": 1850000,
        "file_url": "https://mail.google.com/mail/u/0/#inbox/demo_sih_2026",
        "source_type": "gmail_attachment",
        "source_id": "demo_sih_2026",
        "course_id": None,
        "course_name": None,
        "uploaded_by": "Hackathon Coordinator",
        "is_demo": 1,
    },
    {
        "title": "CS302 Lex & Yacc Reference Manual.pdf",
        "file_name": "Lex_Yacc_Manual.pdf",
        "file_type": "application/pdf",
        "file_size": 950000,
        "file_url": "https://classroom.google.com/c/demo_cs302/m/manual",
        "source_type": "classroom_material",
        "source_id": "demo_mat_3",
        "course_id": "demo_cs302",
        "course_name": "CS302: Compiler Design",
        "uploaded_by": "Dr. Smith",
        "is_demo": 1,
    },
]


def ingest_demo_data(student_email: str = "alex.morgan@university.edu") -> dict[str, Any]:
    """Ingest clearly labeled, realistic demo data for offline local demonstration.

    All demo records explicitly have is_demo = 1.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # Demo Student Google Account
    demo_student_account = {
        "email": student_email,
        "name": "Alex Morgan (Student Demo)",
        "picture": "https://lh3.googleusercontent.com/a/default-user",
        "encrypted_access_token": encrypt_token("demo_access_token_xyz"),
        "encrypted_refresh_token": encrypt_token("demo_refresh_token_xyz"),
        "token_expiry": "2099-01-01T00:00:00Z",
        "scopes": " ".join(READONLY_SCOPES),
        "role": "student",
        "is_demo": 1,
        "last_sync_gmail": now_iso,
        "last_sync_classroom": now_iso,
    }
    save_google_account(demo_student_account)

    # Demo Teacher Google Account
    demo_teacher_account = {
        "email": "e.vance@university.edu",
        "name": "Dr. Elena Vance (Faculty Demo)",
        "picture": "https://lh3.googleusercontent.com/a/default-teacher",
        "encrypted_access_token": encrypt_token("demo_teacher_token_xyz"),
        "encrypted_refresh_token": encrypt_token("demo_teacher_refresh_token_xyz"),
        "token_expiry": "2099-01-01T00:00:00Z",
        "scopes": " ".join(READONLY_SCOPES),
        "role": "teacher",
        "is_demo": 1,
        "last_sync_gmail": now_iso,
        "last_sync_classroom": now_iso,
    }
    save_google_account(demo_teacher_account)

    # Demo Opportunities
    for opp in DEMO_OPPORTUNITIES:
        saved_opp = save_opportunity(opp)
        # Seed participation status for both alex.morgan@university.edu and fallback student.demo@univ.edu
        init_status = "interested" if "Hackathon" in opp["name"] else "discovered"
        update_student_opportunity_status(
            student_id=student_email,
            opportunity_id=saved_opp["id"],
            status=init_status,
            evidence_notes="Sample opportunity participation status for local testing.",
        )
        if student_email != "student.demo@univ.edu":
            update_student_opportunity_status(
                student_id="student.demo@univ.edu",
                opportunity_id=saved_opp["id"],
                status=init_status,
                evidence_notes="Sample opportunity participation status for local testing.",
            )

    # Demo Classroom Courses, Coursework, Submissions, Materials
    for c in DEMO_COURSES:
        save_classroom_course(c)

    for cw in DEMO_COURSEWORK:
        save_classroom_coursework(cw)

    for s in DEMO_SUBMISSIONS:
        save_classroom_submission(s)

    for m in DEMO_STUDY_MATERIALS:
        save_study_material(m)

    return {
        "status": "success",
        "message": "Demo data initialized successfully with explicit is_demo=True labels.",
        "account_email": student_email,
        "opportunities_count": len(DEMO_OPPORTUNITIES),
        "courses_count": len(DEMO_COURSES),
        "coursework_count": len(DEMO_COURSEWORK),
        "submissions_count": len(DEMO_SUBMISSIONS),
        "materials_count": len(DEMO_STUDY_MATERIALS),
    }
