"""Unit tests for WhatsApp chat parser (backend/parser.py)."""

import pytest
from parser import clean_line, parse_whatsapp_text


def test_android_style_parsing():
    raw = "19/10/26, 9:00 am - Class Rep: Please submit Assignment 1."
    messages = parse_whatsapp_text(raw)
    assert len(messages) == 1
    msg = messages[0]
    assert msg["message_id"] == 1
    assert msg["sender"] == "Class Rep"
    assert msg["text"] == "Please submit Assignment 1."
    assert "19/10/26" in msg["timestamp_text"]
    assert "9:00 am" in msg["timestamp_text"]


def test_ios_style_parsing():
    raw = "[19/10/2026, 9:00:00 AM] Dr. Smith: Examination schedule released."
    messages = parse_whatsapp_text(raw)
    assert len(messages) == 1
    msg = messages[0]
    assert msg["sender"] == "Dr. Smith"
    assert msg["text"] == "Examination schedule released."
    assert "19/10/2026" in msg["timestamp_text"]


def test_ios_style_with_narrow_spaces_and_unicode_lrm():
    # iOS 15+ exports often include \u200e and \u202f
    raw = "\u200e[19/10/2026, 9:00:00\u202fAM] Alice: Check this out."
    messages = parse_whatsapp_text(raw)
    assert len(messages) == 1
    assert messages[0]["sender"] == "Alice"
    assert messages[0]["text"] == "Check this out."


def test_multiline_messages():
    raw = (
        "19/10/2026, 10:00 am - Prof. Alan: Important Instructions:\n"
        "1. Write legibly.\n"
        "2. Bring calculators.\n"
        "3. Good luck!"
    )
    messages = parse_whatsapp_text(raw)
    assert len(messages) == 1
    lines = messages[0]["text"].splitlines()
    assert len(lines) == 4
    assert lines[1] == "1. Write legibly."
    assert lines[3] == "3. Good luck!"


def test_system_notifications_without_sender():
    raw = (
        "19/10/2026, 9:00 am - Messages and calls are end-to-end encrypted.\n"
        "19/10/2026, 9:01 am - You created group 'CS 2026'\n"
        "19/10/2026, 9:02 am - Bob joined using this group's invite link\n"
        "19/10/2026, 9:05 am - Bob: Hello everyone!"
    )
    messages = parse_whatsapp_text(raw)
    assert len(messages) == 4
    assert messages[0]["sender"] == "System"
    assert "encrypted" in messages[0]["text"]
    assert messages[1]["sender"] == "System"
    assert messages[2]["sender"] == "System"
    assert messages[3]["sender"] == "Bob"
    assert messages[3]["text"] == "Hello everyone!"


def test_messages_with_additional_colons():
    raw = "19/10/2026, 11:00 am - Teaching Assistant: Note: Submission portal is open: https://example.edu"
    messages = parse_whatsapp_text(raw)
    assert len(messages) == 1
    assert messages[0]["sender"] == "Teaching Assistant"
    assert messages[0]["text"] == "Note: Submission portal is open: https://example.edu"


def test_empty_and_whitespace_input():
    assert parse_whatsapp_text("") == []
    assert parse_whatsapp_text("   \n\n  ") == []


def test_unrecognized_format_input():
    raw = "Random text line 1\nRandom text line 2 without timestamps"
    assert parse_whatsapp_text(raw) == []
