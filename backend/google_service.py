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

import config  # Ensures root .env is loaded before accessing environment variables
import asyncio
import base64
from datetime import datetime, timedelta, timezone
import json
import os
import re
from typing import Any, Optional
import urllib.parse

import httpx

from competition_extractor import extract_competition_opportunity
from database import (
    find_associated_task,
    find_duplicate_item,
    get_academic_item_by_id,
    get_google_account,
    save_academic_item,
    save_academic_item_with_association,
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
    is_secure_persistence_configured,
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
    "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
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


_refresh_locks: dict[str, asyncio.Lock] = {}


def _get_refresh_lock(email: str) -> asyncio.Lock:
    """Retrieve or create an asyncio.Lock for a specific user email."""
    clean_email = (email or "default").strip().lower()
    if clean_email not in _refresh_locks:
        _refresh_locks[clean_email] = asyncio.Lock()
    return _refresh_locks[clean_email]


def is_token_expired(expiry_iso: Optional[str], buffer_seconds: int = 300) -> bool:
    """Check if token is expired or expiring within buffer_seconds (default 5 minutes).

    Returns True if expiry_iso is missing, malformed, or within buffer_seconds of expiry.
    """
    if not expiry_iso:
        return True
    try:
        clean_iso = expiry_iso.replace("Z", "+00:00")
        expiry_dt = datetime.fromisoformat(clean_iso)
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        return (expiry_dt - now_utc).total_seconds() <= buffer_seconds
    except Exception:
        return True


def build_authorization_url(
    role: str = "student",
    redirect_uri: Optional[str] = None,
    prompt: Optional[str] = None,
) -> dict[str, Any]:
    """Generate the Google OAuth 2.0 authorization URL with CSRF state token."""
    client_id, _ = get_oauth_credentials()
    clean_redirect = (redirect_uri or os.environ.get("GOOGLE_REDIRECT_URI", "")).strip()
    smart_env = os.environ.get("SMART_ENV", "development").strip().lower()

    if not clean_redirect:
        if smart_env == "production":
            raise ValueError("Production configuration error: GOOGLE_REDIRECT_URI is required in production environments.")
        clean_redirect = "http://localhost:8000/api/auth/google/callback"

    if not client_id:
        return {
            "configured": False,
            "auth_url": None,
            "message": "Google Client ID is not configured in environment (GOOGLE_CLIENT_ID). Live OAuth requires client credentials.",
        }

    selected_prompt = prompt or "consent"
    state = generate_oauth_state(role=role, redirect_uri=clean_redirect)
    params = {
        "client_id": client_id,
        "redirect_uri": clean_redirect,
        "response_type": "code",
        "scope": " ".join(READONLY_SCOPES),
        "access_type": "offline",
        "prompt": selected_prompt,
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

    redirect_uri = (state_payload.get("redirect_uri") or os.environ.get("GOOGLE_REDIRECT_URI", "")).strip()
    smart_env = os.environ.get("SMART_ENV", "development").strip().lower()
    if not redirect_uri:
        if smart_env == "production":
            raise ValueError("Production configuration error: GOOGLE_REDIRECT_URI is required in production environments.")
        redirect_uri = "http://localhost:8000/api/auth/google/callback"
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
        try:
            expires_in = int(tokens.get("expires_in", 3600))
        except (ValueError, TypeError):
            expires_in = 3600
        expiry_dt = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        expiry_iso = expiry_dt.isoformat()

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

        # Preserve existing encrypted refresh token if Google did not send a new one on re-consent
        existing_account = get_google_account(email=email)
        existing_enc_refresh = existing_account.get("encrypted_refresh_token") if existing_account else None

        account_record = {
            "email": email,
            "name": profile.get("name", email.split("@")[0]),
            "picture": profile.get("picture"),
            "encrypted_access_token": encrypt_token(access_token),
            "encrypted_refresh_token": encrypt_token(refresh_token) if refresh_token else existing_enc_refresh,
            "token_expiry": expiry_iso,
            "scopes": tokens.get("scope", " ".join(READONLY_SCOPES)),
            "role": role,
            "is_demo": 0,
        }
        saved = save_google_account(account_record)
        return saved


async def get_valid_access_token(
    account: dict[str, Any],
    force_refresh: bool = False,
) -> str:
    """Retrieve a valid Google OAuth access token, automatically refreshing if expired or expiring soon.

    Args:
        account: Connected Google account dictionary from database.
        force_refresh: If True, forces a refresh against Google's token endpoint.

    Returns:
        A valid decrypted plaintext access token.

    Raises:
        ValueError: If tokens are missing, expired without refresh token, or revoked.
    """
    enc_access = account.get("encrypted_access_token")
    enc_refresh = account.get("encrypted_refresh_token")
    token_expiry = account.get("token_expiry")
    email = (account.get("email") or "").strip().lower()

    if account.get("is_demo"):
        if enc_access:
            try:
                return decrypt_token(enc_access)
            except Exception:
                pass
        return "demo_access_token"

    if not enc_access and not enc_refresh:
        raise ValueError("No OAuth tokens stored for this account. Please connect your Google account.")

    # 1. Fast-path: Reuse existing decrypted access token if valid and not expiring soon
    if not force_refresh and enc_access and not is_token_expired(token_expiry, buffer_seconds=300):
        try:
            cached_token = decrypt_token(enc_access)
            if cached_token:
                return cached_token
        except Exception:
            pass  # Corrupted access token; fall through to refresh

    # 2. Check refresh token availability
    if not enc_refresh:
        raise ValueError(
            "Google account requires reconnection: refresh token is missing. Please reconnect your Google account in Settings."
        )

    # 3. Synchronize concurrent refresh requests for the same account email
    lock = _get_refresh_lock(email)
    async with lock:
        # Double-check inside lock: another concurrent task might have already refreshed
        latest_account = get_google_account(email=email) if email else None
        if not latest_account:
            latest_account = account

        if not force_refresh and latest_account.get("encrypted_access_token"):
            if not is_token_expired(latest_account.get("token_expiry"), buffer_seconds=300):
                try:
                    rechecked_token = decrypt_token(latest_account["encrypted_access_token"])
                    if rechecked_token:
                        account.update(latest_account)
                        return rechecked_token
                except Exception:
                    pass

        active_enc_refresh = latest_account.get("encrypted_refresh_token") or enc_refresh
        try:
            raw_refresh = decrypt_token(active_enc_refresh)
        except Exception as err:
            raise ValueError(f"Failed to decrypt stored refresh token: {err}. Please reconnect your Google account.")

        client_id, client_secret = get_oauth_credentials()
        if not client_id or not client_secret:
            raise ValueError("Google OAuth credentials are not configured on the server.")

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
                if not new_access:
                    raise ValueError("Google OAuth token refresh did not return an access token.")

                try:
                    expires_in = int(data.get("expires_in", 3600))
                except (ValueError, TypeError):
                    expires_in = 3600

                new_expiry_dt = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                new_expiry_iso = new_expiry_dt.isoformat()

                latest_account["encrypted_access_token"] = encrypt_token(new_access)
                latest_account["token_expiry"] = new_expiry_iso

                # Update rotated refresh token if Google sent a new one
                new_refresh = data.get("refresh_token")
                if new_refresh:
                    latest_account["encrypted_refresh_token"] = encrypt_token(new_refresh)

                saved = save_google_account(latest_account)
                if saved:
                    account.update(saved)
                else:
                    account.update(latest_account)
                return new_access

            # Parse error payload
            err_data = {}
            try:
                err_data = resp.json()
            except Exception:
                pass

            err_code = err_data.get("error", "")
            err_desc = err_data.get("error_description", "")

            if (
                err_code in ("invalid_grant", "unauthorized_client")
                or "revoked" in err_desc.lower()
                or "expired" in err_desc.lower()
            ):
                raise ValueError(
                    "Google authorization has expired or was revoked. Please reconnect your Google account in Settings."
                )

            raise ValueError(f"Google token refresh failed ({resp.status_code}): {err_desc or resp.text}")


def extract_urls_with_labels(text: str, html: Optional[str] = None) -> list[dict[str, str]]:
    """Extract, normalize, label, and deduplicate academic/action URLs from email text and HTML.

    Filters out mailto:, javascript:, and internal Gmail tracking / unsubscribe links.
    Strips tracking query parameters (utm_*) and classifies URL kinds.
    """
    raw_candidates: list[tuple[str, str]] = []  # (url, context_or_anchor)

    # 1. Extract from HTML anchor tags if provided
    if html:
        anchor_pattern = re.compile(r'<a\s+[^>]*href=["\'](https?://[^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
        for m in anchor_pattern.finditer(html):
            url = m.group(1).strip()
            anchor_text = re.sub(r'<[^>]+>', ' ', m.group(2)).strip()
            raw_candidates.append((url, anchor_text))

    # 2. Extract from plain text
    url_pattern = re.compile(r'https?://[^\s<>"\',;)]+', re.IGNORECASE)
    for m in url_pattern.finditer(text):
        url = m.group(0).rstrip(".,!?;:)]}>\"'")
        # Capture surrounding 60 chars context
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 30)
        context = text[start:end]
        raw_candidates.append((url, context))

    seen_urls = set()
    extracted: list[dict[str, str]] = []

    TRACKING_PARAMS = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "gclid", "fbclid", "mc_cid", "mc_eid"
    }

    for raw_url, context in raw_candidates:
        # Validate scheme
        if not (raw_url.startswith("http://") or raw_url.startswith("https://")):
            continue

        # Filter out tracking/unsubscribe/service links
        url_lower = raw_url.lower()
        if any(bad in url_lower for bad in (
            "unsubscribe", "mail.google.com/mail/u/", "google.com/url?", "notifications.google.com",
            "list-manage.com", "doubleclick.net", "facebook.com", "twitter.com", "instagram.com"
        )):
            continue

        # Strip tracking query parameters
        try:
            parsed = urllib.parse.urlparse(raw_url)
            query_tuples = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            cleaned_query = [
                (k, v) for k, v in query_tuples if k.lower() not in TRACKING_PARAMS
            ]
            new_query = urllib.parse.urlencode(cleaned_query)
            clean_url = urllib.parse.urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
            )
        except Exception:
            clean_url = raw_url

        # Clean trailing slashes for deduplication key
        clean_key = clean_url.rstrip("/")
        if clean_key in seen_urls:
            continue
        seen_urls.add(clean_key)

        clean_lower = clean_url.lower()
        ctx_lower = (context or "").lower()

        # Determine category kind and label
        kind = "generic"
        label = ""

        # Prioritize non-empty, non-URL anchor text if available
        if context and not context.startswith("http://") and not context.startswith("https://") and len(context) > 2:
            label = context

        if "forms.gle" in clean_lower or "docs.google.com/forms" in clean_lower:
            kind = "google_form"
            if not label:
                label = "Open Submission Form" if any(w in ctx_lower for w in ("submit", "assignment", "lab")) else "Open Google Form"
        elif "classroom.google.com" in clean_lower:
            kind = "classroom"
            if not label:
                label = "View in Google Classroom"
        elif "drive.google.com" in clean_lower or "docs.google.com" in clean_lower:
            kind = "drive"
            if not label:
                if "presentation" in clean_lower or "slide" in ctx_lower:
                    label = "View Presentation Slides"
                elif "sheet" in clean_lower or "spreadsheet" in ctx_lower:
                    label = "View Spreadsheet"
                else:
                    label = "Access Document / Material"
        elif any(w in clean_lower or w in ctx_lower for w in ("codeforces.com", "kaggle.com", "leetcode.com", "hackerearth.com", "devpost.com", "hackathon", "contest", "challenge")):
            kind = "competition"
            if not label:
                label = "Visit Competition Website"
        elif any(w in clean_lower or w in ctx_lower for w in ("meet.google.com", "zoom.us", "teams.microsoft.com", "webex.com")):
            kind = "meeting"
            if not label:
                label = "Join Video Meeting"
        elif any(w in ctx_lower for w in ("register", "registration", "signup", "sign up", "apply")):
            kind = "registration"
            if not label:
                label = "View Registration Page"
        elif any(w in clean_lower for w in ("github.com", "gitlab.com")):
            kind = "reference"
            if not label:
                label = "View Code Repository"
        elif any(w in ctx_lower for w in ("syllabus", "notes", "lecture", "slide", "study")):
            kind = "reference"
            if not label:
                label = "Access Study Material"

        if not label:
            try:
                domain = urllib.parse.urlparse(clean_url).netloc.replace("www.", "")
                label = f"Visit {domain}" if domain else "Open Resource Link"
            except Exception:
                label = "Open Resource Link"

        extracted.append({
            "url": clean_url,
            "label": label,
            "kind": kind,
        })

    return extracted


def _decode_gmail_body_with_html(payload: dict[str, Any]) -> tuple[str, str]:
    """Recursively extract plain text and HTML body from a Gmail API message payload."""
    if not payload:
        return "", ""

    plain_text = ""
    html_content = ""

    body_data = payload.get("body", {}).get("data")
    mime = payload.get("mimeType", "")
    if body_data:
        try:
            decoded = base64.urlsafe_b64decode(body_data.encode("ASCII")).decode("utf-8", errors="replace")
            if mime == "text/html":
                html_content = decoded
            else:
                plain_text = decoded
        except Exception:
            pass

    parts = payload.get("parts", [])
    for part in parts:
        p_mime = part.get("mimeType", "")
        p_data = part.get("body", {}).get("data")
        if p_data:
            try:
                dec = base64.urlsafe_b64decode(p_data.encode("ASCII")).decode("utf-8", errors="replace")
                if p_mime == "text/plain" and not plain_text:
                    plain_text = dec
                elif p_mime == "text/html" and not html_content:
                    html_content = dec
            except Exception:
                pass
        elif p_mime.startswith("multipart/"):
            sub_plain, sub_html = _decode_gmail_body_with_html(part)
            if sub_plain and not plain_text:
                plain_text = sub_plain
            if sub_html and not html_content:
                html_content = sub_html

    if not plain_text and html_content:
        # Strip HTML tags for readable plain text
        clean = re.sub(r"<[^>]+>", " ", html_content)
        plain_text = " ".join(clean.split())

    return plain_text, html_content


def _decode_gmail_body(payload: dict[str, Any]) -> str:
    """Recursively extract plain text body from a Gmail API message payload."""
    text, _ = _decode_gmail_body_with_html(payload)
    return text


def _extract_gmail_headers(payload: dict[str, Any]) -> dict[str, str]:
    """Extract standard email headers (From, Subject, Date) from Gmail message payload."""
    headers = {}
    for h in payload.get("headers", []):
        name = h.get("name", "").lower()
        if name in ("from", "subject", "date", "to", "cc"):
            headers[name] = h.get("value", "")
    return headers


# ==============================================================================
# Live Gmail API Synchronization
# ==============================================================================


async def sync_live_gmail(account: dict[str, Any], max_messages: int = 15) -> dict[str, Any]:
    """Retrieve messages from authenticated user's Gmail and extract academic items & competitions."""
    token = await get_valid_access_token(account)
    email_address = account.get("email", "")

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    query = "subject:(assignment OR exam OR test OR project OR hackathon OR competition OR contest OR submission OR deadline OR internal OR class OR lecture)"

    async with httpx.AsyncClient(timeout=20.0) as client:
        list_resp = await client.get(
            GMAIL_MESSAGES_ENDPOINT,
            headers=headers,
            params={"q": query, "maxResults": max_messages},
        )
        if list_resp.status_code == 401:
            # Token might have expired mid-session or been revoked; force refresh and retry once
            token = await get_valid_access_token(account, force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            list_resp = await client.get(
                GMAIL_MESSAGES_ENDPOINT,
                headers=headers,
                params={"q": query, "maxResults": max_messages},
            )

        if list_resp.status_code == 403:
            raise PermissionError("Gmail API access was denied by Google or your Google Workspace administrator.")
        if list_resp.status_code == 401:
            raise ValueError(
                "Google authorization has expired or credentials are invalid. Please reconnect your Google account in Settings."
            )
        if list_resp.status_code != 200:
            raise ValueError(f"Gmail message search failed ({list_resp.status_code}): {list_resp.text}")

        data = list_resp.json()
        msg_items = data.get("messages", [])
        if not msg_items:
            now_iso = datetime.now(timezone.utc).isoformat()
            account["last_sync_gmail"] = now_iso
            save_google_account(account)
            return {"synced_count": 0, "extracted_tasks": 0, "extracted_competitions": 0, "extracted_materials": 0, "last_sync": now_iso, "is_demo": False}

        raw_emails: list[dict[str, Any]] = []
        normalized_emails: list[dict[str, Any]] = []

        for it in msg_items:
            mid = it.get("id")
            detail_resp = await client.get(f"{GMAIL_MESSAGES_ENDPOINT}/{mid}", headers=headers)
            if detail_resp.status_code == 401:
                token = await get_valid_access_token(account, force_refresh=True)
                headers["Authorization"] = f"Bearer {token}"
                detail_resp = await client.get(f"{GMAIL_MESSAGES_ENDPOINT}/{mid}", headers=headers)
            if detail_resp.status_code == 200:
                raw_msg = detail_resp.json()
                raw_emails.append(raw_msg)
                payload = raw_msg.get("payload", {})
                h = _extract_gmail_headers(payload)
                body_plain, body_html = _decode_gmail_body_with_html(payload)
                body = body_plain or raw_msg.get("snippet", "")
                thread_id = raw_msg.get("threadId") or mid

                # Extract shared links from email body and html
                extracted_urls = extract_urls_with_labels(body, body_html)

                # Direct Gmail message/conversation URL using actual threadId
                gmail_deep_link = f"https://mail.google.com/mail/u/0/#all/{thread_id}"

                normalized_emails.append({
                    "id": mid,
                    "sender": h.get("from", "Unknown Sender"),
                    "timestamp": h.get("date", ""),
                    "subject": h.get("subject", ""),
                    "body": body,
                    "labels": raw_msg.get("labelIds", []),
                    "threadId": thread_id,
                    "gmail_deep_link": gmail_deep_link,
                    "extracted_urls": extracted_urls,
                })

    # Parse via GmailAdapter
    adapter = GmailAdapter()
    source_messages = adapter.parse(normalized_emails)
    message_dicts = [m.to_dict() for m in source_messages]

    # Academic tasks extraction
    extracted_items = extract_academic_items(message_dicts)
    saved_tasks_count = 0

    for item in extracted_items:
        # Match email metadata to associate deep link and URLs
        source_id = item.get("source_id")
        matching_norm = next((em for em in normalized_emails if em.get("id") == source_id), None)
        task_meta = item.get("source_metadata") or {}
        if not isinstance(task_meta, dict):
            task_meta = {}

        if matching_norm:
            task_meta["threadId"] = matching_norm.get("threadId")
            task_meta["gmail_deep_link"] = matching_norm.get("gmail_deep_link")
            task_meta["extracted_urls"] = matching_norm.get("extracted_urls", [])

        # Build trusted save payload with source provenance
        trusted_payload = {
            "title": item.get("title"),
            "category": item.get("category", "General"),
            "description": item.get("description") or item.get("source_text", ""),
            "date_text": item.get("date_text"),
            "due_date": item.get("due_date"),
            "date_type": item.get("date_type"),
            "date_status": item.get("date_status"),
            "status": "pending",
            "source_sender": item.get("source_sender"),
            "source_timestamp": item.get("source_timestamp"),
            "source_text": item.get("source_text"),
            "source_filename": "Gmail Live Sync",
            "source_type": "gmail",
            "source_id": source_id,
            "source_metadata": task_meta,
            "review_required": item.get("review_required", False),
            "review_reasons": item.get("review_reasons", []),
            "evidence_text": item.get("evidence_text"),
            "evidence_start_index": item.get("evidence_start_index"),
            "evidence_end_index": item.get("evidence_end_index"),
            "_trusted_confidence": item.get("confidence", "HIGH"),
            "_trusted_confidence_reasons": item.get("confidence_reasons") or [],
            "_trusted_evidence": True,
            "is_actionable": item.get("is_actionable", True),
            "actionability_type": item.get("actionability_type", "action_required"),
            "importance": item.get("importance", "UNASSESSED"),
            "academic_intent": item.get("academic_intent"),
        }

        # Deduplication check
        dup = find_duplicate_item(
            source_text=item.get("source_text"),
            source_timestamp=item.get("source_timestamp"),
            source_sender=item.get("source_sender"),
            category=item.get("category"),
            source_filename="Gmail Live Sync",
            source_type="gmail",
            source_id=item.get("source_id"),
            title=item.get("title"),
            evidence_text=item.get("evidence_text"),
            evidence_start_index=item.get("evidence_start_index"),
            due_date=item.get("due_date"),
        )
        if not dup:
            eff_update_type = item.get("update_type")
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
                associated = find_associated_task(trusted_payload)
                if associated and associated.get("id"):
                    target_id = associated["id"]
                    target_task = get_academic_item_by_id(target_id)
                    if target_task:
                        target_old_reasons = target_task.get("review_reasons") or []
                        trusted_payload["replaces_task_id"] = target_id
                        if eff_update_type == "cancellation":
                            c_reason = "Deadline cancelled by subsequent announcement."
                            if c_reason not in target_old_reasons:
                                target_old_reasons.append(c_reason)
                            trusted_payload["status"] = "cancelled"
                        elif not trusted_payload.get("previous_due_date"):
                            trusted_payload["previous_due_date"] = associated.get("due_date")

            if target_id:
                save_academic_item_with_association(
                    data=trusted_payload,
                    target_id=target_id,
                    target_status="cancelled" if eff_update_type == "cancellation" else "superseded",
                    target_review_required=True if eff_update_type == "cancellation" else None,
                    target_review_reasons=target_old_reasons if eff_update_type == "cancellation" else None,
                )
            else:
                save_academic_item(trusted_payload)
            saved_tasks_count += 1

    # Competitions and study materials extraction
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
        "extracted_tasks": saved_tasks_count,
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
        if courses_resp.status_code == 401:
            token = await get_valid_access_token(account, force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            courses_resp = await client.get(
                CLASSROOM_COURSES_ENDPOINT,
                headers=headers,
                params={"courseStates": "ACTIVE"},
            )
        if courses_resp.status_code == 403:
            raise PermissionError("Google Classroom API access was denied by Google or your Google Workspace administrator.")
        if courses_resp.status_code == 401:
            raise ValueError(
                "Google authorization has expired or credentials are invalid. Please reconnect your Google account in Settings."
            )
        if courses_resp.status_code != 200:
            raise ValueError(f"Failed to fetch Classroom courses ({courses_resp.status_code}): {courses_resp.text}")

        courses = courses_resp.json().get("courses", [])
        saved_course_count = 0
        saved_coursework_count = 0
        saved_sub_count = 0
        saved_material_count = 0

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

                    # Index attached course materials if present in coursework
                    for mat_item in cw.get("materials", []):
                        drive_file = mat_item.get("driveFile", {}).get("driveFile", {})
                        if drive_file:
                            f_title = drive_file.get("title") or "Classroom Attachment"
                            save_study_material({
                                "title": f_title,
                                "file_name": f_title,
                                "file_type": "application/pdf",
                                "file_size": 0,
                                "file_url": drive_file.get("alternateLink") or cw.get("alternateLink"),
                                "source_type": "classroom_material",
                                "source_id": drive_file.get("id") or cw_id,
                                "course_id": cid,
                                "course_name": c.get("name"),
                                "uploaded_by": c.get("name"),
                                "is_demo": 0,
                            })
                        link_item = mat_item.get("link", {})
                        if link_item:
                            l_title = link_item.get("title") or "Classroom Resource Link"
                            save_study_material({
                                "title": l_title,
                                "file_name": l_title,
                                "file_type": "text/html",
                                "file_size": 0,
                                "file_url": link_item.get("url"),
                                "source_type": "classroom_material",
                                "source_id": f"link_{cw_id}_{l_title[:10]}",
                                "course_id": cid,
                                "course_name": c.get("name"),
                                "uploaded_by": c.get("name"),
                                "is_demo": 0,
                            })

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

            # 3. Fetch Course Study Materials (courses.courseWorkMaterials.list)
            mat_page_token = None
            while True:
                mat_params = {"courseMaterialStates": "PUBLISHED"}
                if mat_page_token:
                    mat_params["pageToken"] = mat_page_token
                cwm_resp = await client.get(
                    f"{CLASSROOM_COURSES_ENDPOINT}/{cid}/courseWorkMaterials",
                    headers=headers,
                    params=mat_params,
                )
                if cwm_resp.status_code == 200:
                    cwm_data = cwm_resp.json()
                    for cwm in cwm_data.get("courseWorkMaterial", []):
                        cwm_id = cwm.get("id")
                        cwm_title = cwm.get("title") or "Course Material"
                        cwm_desc = cwm.get("description") or ""
                        cwm_materials = cwm.get("materials", [])
                        cwm_link = cwm.get("alternateLink")

                        # If no nested items, save the entry itself
                        if not cwm_materials:
                            save_study_material({
                                "title": cwm_title,
                                "file_name": cwm_title,
                                "file_type": "text/html",
                                "file_size": 0,
                                "file_url": cwm_link,
                                "source_type": "classroom_material",
                                "source_id": cwm_id,
                                "course_id": cid,
                                "course_name": c.get("name"),
                                "uploaded_by": c.get("name"),
                                "is_demo": 0,
                            })
                            saved_material_count += 1

                        for m_idx, mat_item in enumerate(cwm_materials):
                            # Drive File attachment
                            drive_file = mat_item.get("driveFile", {}).get("driveFile", {})
                            if drive_file:
                                f_title = drive_file.get("title") or cwm_title
                                f_type = "application/pdf" if f_title.lower().endswith(".pdf") else "application/octet-stream"
                                save_study_material({
                                    "title": f_title,
                                    "file_name": f_title,
                                    "file_type": f_type,
                                    "file_size": 0,
                                    "file_url": drive_file.get("alternateLink") or cwm_link,
                                    "source_type": "classroom_material",
                                    "source_id": drive_file.get("id") or f"{cwm_id}_drive_{m_idx}",
                                    "course_id": cid,
                                    "course_name": c.get("name"),
                                    "uploaded_by": c.get("name"),
                                    "is_demo": 0,
                                    "description": cwm_desc,
                                })
                                saved_material_count += 1

                            # External Link
                            link_item = mat_item.get("link", {})
                            if link_item:
                                l_title = link_item.get("title") or cwm_title
                                save_study_material({
                                    "title": l_title,
                                    "file_name": l_title,
                                    "file_type": "text/html",
                                    "file_size": 0,
                                    "file_url": link_item.get("url"),
                                    "source_type": "classroom_material",
                                    "source_id": f"link_{cwm_id}_{m_idx}",
                                    "course_id": cid,
                                    "course_name": c.get("name"),
                                    "uploaded_by": c.get("name"),
                                    "is_demo": 0,
                                    "description": cwm_desc,
                                })
                                saved_material_count += 1

                            # YouTube Video
                            yt_item = mat_item.get("youtubeVideo", {})
                            if yt_item:
                                yt_title = yt_item.get("title") or f"{cwm_title} (Video)"
                                save_study_material({
                                    "title": yt_title,
                                    "file_name": yt_title,
                                    "file_type": "video/youtube",
                                    "file_size": 0,
                                    "file_url": yt_item.get("alternateLink"),
                                    "source_type": "classroom_material",
                                    "source_id": yt_item.get("id") or f"yt_{cwm_id}_{m_idx}",
                                    "course_id": cid,
                                    "course_name": c.get("name"),
                                    "uploaded_by": c.get("name"),
                                    "is_demo": 0,
                                    "description": cwm_desc,
                                })
                                saved_material_count += 1

                            # Google Form
                            form_item = mat_item.get("form", {})
                            if form_item:
                                form_title = form_item.get("title") or f"{cwm_title} (Form)"
                                save_study_material({
                                    "title": form_title,
                                    "file_name": form_title,
                                    "file_type": "application/x-google-form",
                                    "file_size": 0,
                                    "file_url": form_item.get("formUrl") or form_item.get("responseUrl"),
                                    "source_type": "classroom_material",
                                    "source_id": f"form_{cwm_id}_{m_idx}",
                                    "course_id": cid,
                                    "course_name": c.get("name"),
                                    "uploaded_by": c.get("name"),
                                    "is_demo": 0,
                                    "description": cwm_desc,
                                })
                                saved_material_count += 1

                    mat_page_token = cwm_data.get("nextPageToken")
                    if not mat_page_token:
                        break
                else:
                    break

    now_iso = datetime.now(timezone.utc).isoformat()
    account["last_sync_classroom"] = now_iso
    save_google_account(account)

    return {
        "courses_count": saved_course_count,
        "coursework_count": saved_coursework_count,
        "submissions_count": saved_sub_count,
        "materials_count": saved_material_count,
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
