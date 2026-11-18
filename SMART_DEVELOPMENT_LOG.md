# SMART 2.0 — DEVELOPMENT LOG

## Phase 1: Task Editing and Backend Data Model

**Date:** 2026-11-18  
**Status:** Completed  
**Branch:** `feature/smart-v2-intelligence`  
**Test Suite:** 54/54 Pytest tests passing (41 baseline regression tests + 13 new Phase 1 editing tests)

---

### 1. Objective & Scope

Implement a reliable academic task editing capability in the FastAPI and SQLite backend.
Users can now correct extracted information (title, description, category, due date, date text, date type, etc.) in-place without deleting and recreating tasks, preserving task identity and source evidence.

---

### 2. Files Modified and Created

#### Files Modified:
- `backend/database.py`:
  - Added `IMMUTABLE_FIELDS` set (`id`, `source_text`, `source_sender`, `source_timestamp`, `source_filename`, `created_at`).
  - Added `EDITABLE_COLUMNS` set (`title`, `category`, `description`, `date_text`, `due_date`, `date_type`, `date_status`, `status`, `review_required`, `review_reasons`).
  - Implemented `update_academic_item(item_id, updates, db_path)` supporting partial updates with parameterized SQL, explicit `None` handling for nullable fields (clearing due_date or description), and automatic UTC `updated_at` refresh.
  - Refactored `update_academic_item_status` to delegate to `update_academic_item`.
- `backend/main.py`:
  - Added `AcademicItemUpdate` Pydantic model with strict field validators (`title` non-empty, `category` in `ALLOWED_CATEGORIES`, `due_date` valid ISO format) and `ConfigDict(extra="forbid")` to reject tampering with immutable provenance fields with HTTP 422.
  - Provided `AcademicItemStatusUpdate = AcademicItemUpdate` for backward compatibility.
  - Enhanced `PATCH /api/academic-items/{item_id}` endpoint to support full partial updates while maintaining backward compatibility for invalid status (HTTP 400).
  - Provided `update_task_status = update_task_item` function alias.
- `backend/tests/test_persistence.py`:
  - Added 13 new automated integration and unit test cases covering all Phase 1 requirements: title update, description update, category update, due date update, partial update preservation, multi-field update, explicit null handling, invalid category rejection, invalid date rejection, nonexistent task 404, immutable provenance rejection, deduplication preservation, and direct database-layer updates.

#### Files Created:
- `SMART_DEVELOPMENT_LOG.md`: This development log.

---

### 3. API Request and Response Examples

#### 3.1 Partial Update: Title and Category
**Request:**
```http
PATCH /api/academic-items/1 HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "title": "Distributed Systems Milestone 1",
  "category": "Assignment"
}
```

**Response (HTTP 200 OK):**
```json
{
  "id": 1,
  "title": "Distributed Systems Milestone 1",
  "category": "Assignment",
  "description": "Submit code and report on raft consensus",
  "date_text": "28/10/2026",
  "due_date": "2026-10-28",
  "date_type": "deadline",
  "date_status": "parsed",
  "status": "pending",
  "source_sender": "Prof. Alan Turing",
  "source_timestamp": "19/10/2026, 9:15 am",
  "source_text": "Assignment 1 on Distributed Consensus is released. Submission deadline is due on 28/10/2026.",
  "source_filename": "sample_chat.txt",
  "review_required": false,
  "review_reasons": [],
  "created_at": "2026-11-18T00:00:00+00:00",
  "updated_at": "2026-11-18T08:00:15.123456+00:00"
}
```

#### 3.2 Explicit Null Handling: Clearing a Due Date
**Request:**
```http
PATCH /api/academic-items/1 HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "due_date": null
}
```

**Response (HTTP 200 OK):**
```json
{
  "id": 1,
  "title": "Distributed Systems Milestone 1",
  "category": "Assignment",
  "description": "Submit code and report on raft consensus",
  "date_text": "28/10/2026",
  "due_date": null,
  "date_type": "deadline",
  "date_status": "parsed",
  "status": "pending",
  "source_sender": "Prof. Alan Turing",
  "source_timestamp": "19/10/2026, 9:15 am",
  "source_text": "Assignment 1 on Distributed Consensus is released. Submission deadline is due on 28/10/2026.",
  "source_filename": "sample_chat.txt",
  "review_required": false,
  "review_reasons": [],
  "created_at": "2026-11-18T00:00:00+00:00",
  "updated_at": "2026-11-18T08:00:30.987654+00:00"
}
```

#### 3.3 Security Rejection: Immutable Provenance Field
**Request:**
```http
PATCH /api/academic-items/1 HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "source_text": "Forged evidence message",
  "source_sender": "Impersonator"
}
```

**Response (HTTP 422 Unprocessable Entity):**
```json
{
  "detail": [
    {
      "type": "extra_forbidden",
      "loc": ["body", "source_text"],
      "msg": "Extra inputs are not permitted",
      "input": "Forged evidence message"
    },
    {
      "type": "extra_forbidden",
      "loc": ["body", "source_sender"],
      "msg": "Extra inputs are not permitted",
      "input": "Impersonator"
    }
  ]
}
```

#### 3.4 Validation Rejection: Invalid Date Format
**Request:**
```http
PATCH /api/academic-items/1 HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "due_date": "31-12-2026"
}
```

**Response (HTTP 422 Unprocessable Entity):**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "due_date"],
      "msg": "Value error, Invalid due_date format '31-12-2026'. Expected YYYY-MM-DD.",
      "input": "31-12-2026"
    }
  ]
}
```

---

### 4. Database Schema Impact

- **Schema Changes:** None required.
- **Backward Compatibility:** All editable columns (`title`, `category`, `description`, `date_text`, `due_date`, `date_type`, `date_status`, `status`, `review_required`, `review_reasons`, `updated_at`) were already present in the SQLite `academic_items` table.
- **Integrity Preserved:** No database reset or schema migration was needed. Existing database records and sequences remain completely untouched.

---

### 5. Test Results

- **Test Suite Command:** `py -m pytest -v`
- **Result:** **54 passed, 1 warning in 16.24s** (100% pass rate)
  - 41 Baseline Regression Tests: All PASSED.
  - 13 New Phase 1 Update Tests: All PASSED.

#### Detailed New Test Coverage:
1. `test_update_task_title` — Validates updating title while preserving category and due date.
2. `test_update_task_description` — Validates expanding or editing detailed instructions.
3. `test_update_task_category` — Validates updating category (e.g., Announcement -> Event).
4. `test_update_task_due_date` — Validates changing ISO due date.
5. `test_partial_update_preserves_other_fields` — Validates that unsupplied fields (source provenance, timestamps, date types) remain intact.
6. `test_multiple_fields_updated_together` — Validates updating title, category, description, date_type, and status concurrently.
7. `test_update_explicit_null_handling` — Validates explicitly setting `due_date: null` (clears date) and `description: null` (clears description).
8. `test_update_invalid_category_rejected` — Validates that unapproved categories return HTTP 422.
9. `test_update_invalid_date_rejected` — Validates that non-ISO dates return HTTP 422.
10. `test_update_nonexistent_task_id_returns_404` — Validates that invalid task IDs return HTTP 404.
11. `test_immutable_provenance_fields_cannot_be_modified` — Validates that attempts to mutate `source_text`, `source_sender`, `source_timestamp`, `source_filename`, `created_at`, or `id` return HTTP 422 and leave the database record unchanged.
12. `test_existing_creation_and_deduplication_unaffected` — Validates that task creation and 409 Conflict deduplication continue working alongside edits.
13. `test_database_update_academic_item_direct` — Validates database layer error handling and empty update behavior directly.

---

### 6. Remaining Limitations for Future Phases

1. **Frontend Integration (Scheduled for Phase 3):** The React frontend currently lacks an "Edit Task" modal to allow users to trigger these update capabilities from the UI.
2. **Contextual Intelligence across Messages (Scheduled for Phase 4):** Grouping and linking across separate WhatsApp messages (e.g., updates, cancellations, or reminders sent hours or days later).

---

## Phase 2: Enhanced Parsing and Extraction Intelligence

**Date:** 2026-11-18  
**Status:** Completed  
**Branch:** `feature/smart-v2-intelligence`  
**Test Suite:** 79/79 Pytest tests passing (54 baseline regression tests + 25 new Phase 2 extraction tests)  
**Frontend Suite:** Production build passing, lint 0 errors, 0 warnings

---

### 1. Objective & Scope

Upgrade SMART's WhatsApp message processing and academic extraction engine to handle realistic, complex multi-intent messages:
1. **Multi-Item Extraction:** Extract multiple independent academic items (assignments, exams, announcements, events, opportunities) from a single WhatsApp message.
2. **Multiple Date Extraction & Association:** Detect all date expressions in a message, associating each date with its specific academic task without cross-task leakage.
3. **Deadline Time Extraction:** Parse 12-hour and 24-hour time expressions (e.g. `11:59 PM`, `9:30 AM`, `14:30`, `23:59`, `9 AM`, `5 PM`) into structured fields (`time_text`, `deadline_time` normalized to `HH:MM`).
4. **Relative Weekday Resolution:** Accurately resolve bare weekdays ("Friday", "Monday"), prefixed weekdays ("this Friday", "coming Wednesday", "next Monday", "next Friday"), and relative terms ("today", "tomorrow", "day after tomorrow") using the message timestamp date as anchor, including calendar year boundaries.
5. **Academic Intent Distinction:** Differentiate submission deadlines, examination dates, registration deadlines, and event dates (`deadline`, `event_date`, `mentioned_date`).
6. **Source Evidence Preservation:** Retain full original message text, sender, timestamp, and review justifications for all extracted candidate items.
7. **Single-Task Integrity:** Avoid duplicate candidate generation for multiline or multi-sentence descriptions of a single task.

---

### 2. Files Modified

#### Files Modified:
- `backend/extractor.py`:
  - Added `WEEKDAY_MAP` mapping day names and 3-letter abbreviations to ISO weekday indices (0..6).
  - Added `PATTERN_RELATIVE_WEEKDAY` supporting bare weekdays and "this", "coming", "next" modifiers.
  - Added `TIME_12H_WITH_MINUTES`, `TIME_12H_NO_MINUTES`, and `TIME_24H` regular expressions with non-digit lookahead protection.
  - Implemented `extract_time(text)` returning `time_text` and normalized 24-hour `deadline_time` (`HH:MM`).
  - Implemented `resolve_weekday(text, message_date)` using modular weekday arithmetic `(target_w - msg_w) % 7` with `is_next` week offset handling.
  - Implemented `detect_all_dates(text, timestamp_text)` returning non-overlapping date spans sorted by text order.
  - Updated `detect_date(text, timestamp_text)` to utilize `detect_all_dates`, flagging ambiguous multi-date single tasks for human review.
  - Implemented `split_message_into_segments(text)` protecting title abbreviations (`Dr.`, `Prof.`, `e.g.`, etc.) and splitting on punctuation, linebreaks, and coordinating conjunctions before academic keywords.
  - Implemented multi-item task clustering in `extract_academic_items(messages)`: groups continuation lines while isolating distinct academic items, associating respective dates, times, and categories.
  - Extended `DEADLINE_INDICATORS` to detect registration deadlines (`registration closes on`, `closes on`, `apply before`, `register before`, etc.).
  - Extended `CATEGORY_PATTERNS["Assignment"]` to recognize project demos, presentations, and evaluations.
- `backend/tests/test_extractor.py`:
  - Added 25 new tests across 5 requirement groups (Multi-item extraction, multiple dates, deadline times, relative weekdays, international dates).
- `SMART_DEVELOPMENT_LOG.md`:
  - Updated with Phase 2 implementation summary, before/after examples, and test suite verification.

---

### 3. Architecture & Algorithmic Rules

#### 3.1 Sentence & Clause Segmentation
Messages are segmented into candidate clauses while protecting known abbreviations (`Dr.`, `Prof.`, `Mr.`, `Mrs.`, `Ms.`, `vs.`, `e.g.`, `i.e.`, `etc.`):
```python
# Boundaries: . + uppercase/digit, !, ?, ;, newlines, or coordinating conjunctions before academic keywords
split_regex = re.compile(
    r"(?:\.\s+(?=[A-Z0-9])|[!?]\s+|;\s*|\n+|\s+(?:and|but)\s+(?=(?:the\s+)?(?:assignment|exam|internal|workshop|seminar|conference|hackathon|internship|submission|quiz|registration)\b))",
    re.IGNORECASE,
)
```

#### 3.2 Task Clustering & Anti-Duplication
A segment starts a NEW task if:
- It is the first academic segment; OR
- It has an academic category different from the current task (`Assignment` vs `Exam`); OR
- It has the same category, but both current task and segment have independent dates with distinct types (e.g. registration `deadline` vs `event_date`) or distinct dates.
Otherwise, segments merge into the current task. This guarantees that multi-line assignments (e.g., Release announcement + Deadline line + Submission instructions) produce exactly **1** clean academic item.

#### 3.3 Weekday Resolution Formula
Given message timestamp date $D$ with weekday $w_{\text{msg}} \in [0..6]$ and target weekday $w_{\text{target}} \in [0..6]$:
$$\Delta = (w_{\text{target}} - w_{\text{msg}}) \pmod 7$$
If $\Delta = 0$, then $\Delta \leftarrow 7$ (referencing the upcoming occurrence).  
If the modifier is `"next"` and $w_{\text{msg}} + \Delta \le 6$ (meaning the day falls within the current week), an additional $+7$ days is added to target the following calendar week:
$$\Delta \leftarrow \Delta + 7$$
The date is then resolved as $D + \Delta \text{ days}$.

#### 3.4 Ambiguous Date Handling
When a single task statement contains multiple non-identical candidate dates (e.g. `"The demo will be held on either 10/11/2026 or 12/11/2026"`):
- `due_date` is set to `None`.
- `date_status` is set to `"needs_review"`.
- `review_required` is set to `True`.
- `review_reasons` records: `"Multiple candidate dates detected in task text (...); marked for human review."`
The system never guesses arbitrarily.

---

### 4. Before & After Extraction Examples

#### Example 1: Multi-Item Message
- **Input Text:** `"DBMS assignment submission is Friday. CN internal exam is Monday."` (Timestamp: Mon 19/10/2026, 9:00 am)
- **Phase 1 Behavior:** Extracted 1 combined item categorized as `Assignment` (based on priority order), missing the second task.
- **Phase 2 Behavior:** Extracted 2 distinct items:
  1. Title: `"DBMS assignment submission is Friday."`, Category: `"Assignment"`, Due Date: `"2026-10-23"`, Date Type: `"deadline"`.
  2. Title: `"CN internal exam is Monday."`, Category: `"Exam"`, Due Date: `"2026-10-26"`, Date Type: `"event_date"`.

#### Example 2: Registration Deadline & Event Date
- **Input Text:** `"Workshop registration closes on Wednesday. The workshop will be held on Saturday."` (Timestamp: Mon 19/10/2026, 9:00 am)
- **Phase 1 Behavior:** Extracted 1 item with the first matched date.
- **Phase 2 Behavior:** Extracted 2 distinct items:
  1. Title: `"Workshop registration closes on Wednesday."`, Date Type: `"deadline"`, Due Date: `"2026-10-21"`.
  2. Title: `"The workshop will be held on Saturday."`, Date Type: `"event_date"`, Due Date: `"2026-10-24"`.

#### Example 3: Deadline Time Extraction
- **Input Text:** `"Submit the assignment by 11:59 PM on Friday."`
- **Phase 1 Behavior:** `time_text` and `deadline_time` did not exist.
- **Phase 2 Behavior:** `time_text = "11:59 PM"`, `deadline_time = "23:59"`.

#### Example 4: Multiline Single Task (Anti-Duplication)
- **Input Text:**
  ```
  Assignment 1 is released.
  The deadline is 28/10/2026.
  Submit code on portal.
  ```
- **Phase 2 Behavior:** Extracted exactly 1 item: Category: `"Assignment"`, Due Date: `"2026-10-28"`, Title: `"Assignment 1 is released."`.

---

### 5. Test Suite Verification

- **Command:** `py -m pytest -v`
- **Result:** **79 passed, 1 warning in 11.02s** (100% pass rate)
  - 8 API Integration Tests (`test_api.py`): PASSED
  - 44 Extractor Unit Tests (`test_extractor.py`): PASSED (19 baseline + 25 new Phase 2 tests)
  - 8 WhatsApp Parser Tests (`test_parser.py`): PASSED
  - 19 Persistence & Editing Tests (`test_persistence.py`): PASSED
- **Frontend Verification:**
  - `npm run lint`: 0 errors, 0 warnings
  - `npm run build`: Production build completed successfully in 483ms.

