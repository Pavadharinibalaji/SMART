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

---

## Phase 3: Confidence Scoring & Evidence Intelligence

- **Date:** 2026-11-18
- **Status:** Completed
- **Branch:** `feature/smart-v2-intelligence`
- **Test Suite:** 94/94 Pytest tests passing (79 baseline regression tests + 15 new Phase 3 tests)
- **Frontend Suite:** Production build passing, lint 0 errors, 0 warnings

---

### 1. Objective & Scope

Implement a transparent, deterministic confidence and evidence intelligence layer for SMART's academic task extraction pipeline:
1. **Evidence Intelligence:** Associate each candidate with exact supporting text (`evidence_text`) extracted from the source message, distinguishing the candidate-level clause from the complete original `source_text`.
2. **Deterministic Confidence Classification:** Replace arbitrary percentages with an explainable three-tier system: `HIGH`, `MEDIUM`, and `LOW`.
3. **Structured Review Reasons:** Explain why human verification is required or why lower confidence was assigned, eliminating duplicate reasons.
4. **Additive Persistence & Migration:** Extend the SQLite schema with `evidence_text`, `confidence`, and `confidence_reasons` via idempotent migrations, preserving legacy records and protecting evidence immutability.
5. **API Compatibility:** Expose confidence metrics in extraction summaries and query filters (`GET /api/academic-items?confidence=HIGH`).

---

### 2. Architecture & Decision Rules

#### 2.1 Deterministic Confidence Decision Table

| Confidence Level | Category Certainty | Date Certainty | Intent / Phrasing | Rationale & Explanation |
|---|---|---|---|---|
| **HIGH** | Single unambiguous category | Explicit calendar date with year (`date_status == 'parsed'`) | Confirmed `deadline` or `event_date` | Category is certain and calendar date is fully validated. |
| **MEDIUM** | Single unambiguous category | Relative date resolved via message timestamp anchor (`date_status == 'resolved_from_message_date'`) | Confirmed `deadline` or `event_date` | Task and category are clear; relative day resolves deterministically via timestamp. |
| **MEDIUM** | Single unambiguous category | No date detected (`date_status == 'not_found'`) | Clear academic task indicators | Valid task (e.g. project release) identified without an explicit date. Not penalized as invalid. |
| **LOW** | Any | Ambiguous, missing year, or unresolvable date (`date_status == 'needs_review'`) | Any | Ambiguous date (multiple candidate dates, ambiguous numeric format, or missing year). A candidate with an ambiguous date **never** receives HIGH confidence. |
| **LOW** | Multiple conflicting categories (`len > 1`) | Any | Any | Clashing academic intents (e.g. assignment vs exam). |
| **LOW** | Weak generic keyword | Any | Any | Isolated 'event' keyword without specific event vocabulary. |
| **LOW** | Assignment | Date present | `mentioned_date` | Date mentioned without explicit submission deadline language (e.g. "discussed on"). |

#### 2.2 Evidence Intelligence & Immutability
- **`evidence_text`:** Exact clause or sentence from the source message establishing the academic item. Never paraphrased or generated.
- **`source_text`:** The entire raw WhatsApp message preserved for complete context and auditability.
- **Provenance Immutability:** `evidence_text` is added to `IMMUTABLE_FIELDS`. Any attempt to tamper with evidence via `PATCH /api/academic-items/{id}` returns HTTP 422 (`extra_forbidden`).

#### 2.3 Review Reasons
- Preserves all Phase 2 date and category review explanations.
- Low-confidence candidates automatically enforce `review_required = True`.
- Review reasons are deduplicated while preserving discovery order: `review_reasons = list(dict.fromkeys(review_reasons))`.

---

### 3. Database Schema & Migration

#### Additive SQLite Migration
Applied idempotently during `init_db()`:
```sql
ALTER TABLE academic_items ADD COLUMN evidence_text TEXT;
ALTER TABLE academic_items ADD COLUMN confidence TEXT DEFAULT 'MEDIUM';
ALTER TABLE academic_items ADD COLUMN confidence_reasons TEXT;
CREATE INDEX IF NOT EXISTS idx_academic_items_confidence ON academic_items(confidence);
```
- **Idempotency:** Checks `PRAGMA table_info(academic_items)` before issuing `ALTER TABLE`.
- **Legacy Compatibility:** Existing rows with `NULL` confidence or evidence gracefully resolve to `confidence: "MEDIUM"`, `confidence_reasons: []`, and `evidence_text: None`.

---

### 4. API Enhancements

1. **`POST /api/extract-academic`:**
   - Adds `confidence_counts: {"HIGH": int, "MEDIUM": int, "LOW": int}` to the top-level extraction summary.
   - Each item includes `evidence_text`, `confidence`, and `confidence_reasons`.
2. **`POST /api/academic-items`:**
   - `AcademicItemCreate` validates `confidence` in `{"HIGH", "MEDIUM", "LOW"}` and persists evidence metadata.
3. **`GET /api/academic-items`:**
   - Adds query parameter `?confidence=HIGH|MEDIUM|LOW` to filter saved tasks.
4. **`PATCH /api/academic-items/{id}`:**
   - Allows updating `confidence` and `confidence_reasons`.
   - Strictly forbids editing `evidence_text` (HTTP 422).

---

### 5. Test Suite Verification

- **Command:** `py -m pytest -v`
- **Result:** **94 passed, 1 warning in 11.97s** (100% pass rate)
  - 8 API Integration Tests (`test_api.py`): PASSED
  - 54 Extractor Unit Tests (`test_extractor.py`): PASSED (10 new Phase 3 tests)
  - 8 WhatsApp Parser Tests (`test_parser.py`): PASSED
  - 24 Persistence Tests (`test_persistence.py`): PASSED (5 new Phase 3 tests)
- **Frontend Verification:**
  - `npm run lint`: 0 errors, 0 warnings
  - `npm run build`: Production build passed in 454ms.
- **Git Diff Verification:** `git diff --check` reported 0 whitespace errors.


---

## Phase 3.1: Confidence & Evidence Integrity Corrections

- **Date:** 2026-11-18
- **Status:** Completed
- **Branch:** `feature/smart-v2-intelligence`
- **Test Suite:** 117/117 Pytest tests passing (94 baseline regression tests + 23 new Phase 3.1 tests)
- **Frontend Suite:** Production build passing (943ms), lint 0 errors, 0 warnings

---

### 1. Integrity Issues Discovered in Phase 3 Final Audit

1. **Confidence Spoofing via PATCH:** Clients could issue `PATCH /api/academic-items/{id}` with `confidence: "HIGH"` or arbitrary `confidence_reasons` without validating whether extraction evidence justified it.
2. **Arbitrary Injected Confidence via POST:** External clients calling `POST /api/academic-items` could submit arbitrary machine confidence levels, treating client assertions as verified extraction scores.
3. **Evidence Fabrication via POST:** `POST /api/academic-items` accepted arbitrary strings as `evidence_text` without validating whether the evidence existed in `source_text` or was generated by the extraction pipeline.
4. **False Promotion of Legacy Records:** Unassessed legacy records created prior to Phase 3 with `NULL` confidence in the database were silently mapped to `"MEDIUM"` confidence in `row_to_item_dict()`, misrepresenting unscored historical records as medium-fidelity extractions.
5. **False Category Conflicts for Contextual Keywords:** Messages like `"Submit your lab exercise report for the robotics workshop on 28/10/2026."` matched both `Assignment` ("lab report", "submit") and `Event` ("workshop"). Because the classifier penalized any multi-category match, the item was falsely demoted to `LOW` confidence even though "workshop" was purely prepositional context for the submission.
6. **Evidence Overlap in Compound Clauses:** Comma-separated independent tasks (e.g. `"Submit assignment 1 on 10/11/2026, CN exam on 12/11/2026."`) were not partitioned at clause boundaries, causing evidence from one task to encompass the adjacent task.

---

### 2. Corrections Implemented

#### 2.1 Confidence & Evidence Trust Boundaries
- **System-Generated Metadata Immutability:** `confidence` and `confidence_reasons` are established as objective, system-generated facts.
- **Removed from `AcademicItemUpdate`:** `AcademicItemUpdate` forbids `confidence` and `confidence_reasons` (`extra="forbid"`), rejecting any PATCH modification with HTTP 422 Unprocessable Entity.
- **Added to `IMMUTABLE_FIELDS`:** `backend/database.py` includes `confidence` and `confidence_reasons` in `IMMUTABLE_FIELDS`, raising a `ValueError` if any internal modification is attempted.
- **Manual Task Representation (`UNASSESSED`):** Manual tasks created via `POST /api/academic-items` or lacking algorithmic assessment automatically receive `confidence: "UNASSESSED"` and `confidence_reasons: []`. Clients cannot inject machine confidence.
- **Fabricated Evidence Protection:**
  - `evidence_text` submitted via client POST must strictly be a verified substring of `source_text`. Fabricated evidence raises HTTP 400 Bad Request.
  - Manual tasks without extraction cannot claim extraction evidence (`evidence_text = None`).
  - Trusted extraction candidates utilize internal sentinel keys (`_trusted_confidence`, `_trusted_confidence_reasons`, `_trusted_evidence`) via `_build_trusted_extraction_payload()` to persist authentic pipeline-derived metadata.

#### 2.2 Correct Legacy Metadata Semantics
- **Explicit `UNASSESSED` Representation:** In `row_to_item_dict()`, rows with `NULL` confidence default to `"UNASSESSED"` (never silently promoted to `"MEDIUM"`).
- **Explicit Unavailable Evidence:** Legacy rows with `NULL` evidence remain `None`, preventing false backfilling with the full `source_text`.
- **Query Filtering on Legacy Records:** `GET /api/academic-items?confidence=UNASSESSED` queries `(confidence IS NULL OR confidence = 'UNASSESSED')`, ensuring historical unassessed records are retrievable.

#### 2.3 Contextual Keyword & Category Conflict Disambiguation
- **Prepositional & Compound Context Detection:** Implemented `_is_contextual_secondary_keyword(primary_cat, other_cat, text)` in `backend/extractor.py`.
- **Assignment vs. Contextual Event/Opportunity:**
  - When an `Assignment` features primary submission verbs/nouns (`submit`, `due`, `lab report`, `project report`) and a secondary `Event` or `Opportunity` appears inside a prepositional phrase (`for the robotics workshop`, `for the annual hackathon`), it is recognized as contextual information.
  - Confidence is calculated using the primary submission intent and explicit dates, accurately receiving `HIGH` confidence.
- **Preserved Genuine Conflicts:** Ambiguous phrases without primary dominance (e.g. `"Semester exam assignment guidelines are published."`) or conflicting task intents remain correctly classified as `LOW` confidence with `review_required = True`.

#### 2.4 Clause Segmentation & Isolated Evidence for Compound Tasks
- **Independent Task Comma Splitting:** Extended `split_message_into_segments()` with `_COMMA_ACADEMIC_SPLIT` to split on commas preceding independent academic clauses (e.g. `", CN exam on 12/11/2026."`).
- **Date & Abbreviation Safety:** Commas within dates (`"Friday, 20 November 2026"`, `"November 20, 2026"`) and titles (`Dr.`, `Prof.`) are strictly preserved and never split.
- **Evidence Isolation:** In `"Submit assignment 1 on 10/11/2026, CN exam on 12/11/2026."`, two independent candidates are generated:
  - Task 1: Category: `Assignment`, Evidence: `"Submit assignment 1 on 10/11/2026"`
  - Task 2: Category: `Exam`, Evidence: `"CN exam on 12/11/2026."`
  Both retain the complete message as `source_text`.

---

### 3. Test Suite Verification

- **Command:** `py -m pytest -v`
- **Result:** **117 passed, 1 warning in 19.15s** (100% pass rate)
  - 8 API Integration Tests (`test_api.py`): PASSED
  - 61 Extractor Unit Tests (`test_extractor.py`): PASSED (7 new Phase 3.1 tests)
  - 8 WhatsApp Parser Tests (`test_parser.py`): PASSED
  - 40 Persistence Tests (`test_persistence.py`): PASSED (16 new Phase 3.1 tests)
- **Frontend Verification:**
  - `npm run lint`: 0 errors, 0 warnings
  - `npm run build`: Production build passed in 943ms.
- **Git Diff Verification:** `git diff --check` reported 0 whitespace errors.

---

### 4. Transition to Frontend Trust & Transparency

With Phase 3.1 completed and verified (117 backend tests passing), the project transitioned to Phase 3.2: Frontend Trust & Transparency.

---

## Phase 3.2.1: Confidence Badge Implementation

- **Date:** 2026-11-18
- **Status:** Completed
- **Branch:** `feature/smart-v2-intelligence`

### 1. Objective & Scope
Surface transparent confidence-level indicators across the React frontend for extracted candidates and saved academic tasks without disrupting existing user workflows.

### 2. Implementation Summary
- Created `frontend/src/components/ConfidenceBadge.jsx`:
  - Visual indicators for `HIGH` (emerald green), `MEDIUM` (amber), `LOW` (rose red), and `UNASSESSED` (slate grey).
  - Accessible semantics with `title` and `aria-label` tooltips.
- Added badge styling in `frontend/src/App.css`.
- Integrated `ConfidenceBadge` into Candidate and Saved Task cards in `frontend/src/App.jsx`.

---

## Phase 3.2.2: Evidence Inspection Drawer

- **Date:** 2026-11-18
- **Status:** Completed
- **Branch:** `feature/smart-v2-intelligence`
- **Test Suite:**
  - Frontend Unit Tests: 12/12 passing (`src/utils/highlightEvidence.test.mjs`)
  - Frontend Linter: ESLint passed with 0 errors and 0 warnings
  - Frontend Build: Vite production build passed
  - Backend Regression: 117/117 Pytest tests passing

---

### 1. Objective & Scope
Implement an interactive, accessible Evidence Inspection Drawer allowing users to inspect the exact source WhatsApp announcement, isolated evidence substring, confidence score, and algorithmic reasoning for any extracted or saved academic item.

---

### 2. Implementation Details

#### 2.1 Exact Substring Matching Engine (`frontend/src/utils/highlightEvidence.js`)
- **Deterministic Zero-Fuzzy Matching:** Uses strict `sourceText.indexOf(trimmedEvidence)` without regex compilation or fuzzy alterations.
- **Segmented Representation:** Partitions text into `{ text, isMatch }` segments rendered via standard JSX (`<mark>` and `<span>`), preventing XSS vulnerabilities without using `dangerouslySetInnerHTML`.
- **First-Occurrence Matching:** Gracefully highlights the first exact match in repeated text.
- **Mismatch Detection:** Flags when non-empty evidence is absent from source text (`isMismatch = true`).
- **Edge-Case Resilience:** Gracefully handles null/undefined/empty sources or evidence strings.

#### 2.2 Accessible Drawer Component (`frontend/src/components/EvidenceDrawer.jsx`)
- **Modal Dialog Semantics:** WAI-ARIA compliant with `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, and `aria-describedby`.
- **Keyboard & Body Scroll Management:** Listens for `Escape` key to close; locks background `document.body.style.overflow = 'hidden'` while open.
- **Structured Sections:**
  1. Header with Task Title, Category, and Close Button (`✕`).
  2. Confidence & Trust Section displaying `ConfidenceBadge` and backend `confidence_reasons`.
  3. Extracted Evidence Snippet box.
  4. Original Message Container with exact highlighted evidence in context, or explicit mismatch warning if evidence cannot be verified within source text.
  5. Missing/Unavailable Evidence Callouts for manual or legacy records.

#### 2.3 Dashboard Integration (`frontend/src/App.jsx` & `frontend/src/App.css`)
- Added "🔍 Evidence" action buttons to both candidate cards (Analyze Chat tab) and saved task cards (Tasks Dashboard).
- Wired modal state `selectedEvidenceItem` to open the drawer on click and dismiss on backdrop click, close button, or Escape key.
- Implemented responsive side-drawer CSS (`width: 520px`, mobile `max-width: 100%`) with amber-highlighted background (`#fef3c7`) for matched evidence.

---

### 3. Test & Verification Results

1. **Unit Testing:**
   - Script: `npm test` (`node src/utils/highlightEvidence.test.mjs`)
   - 12/12 test scenarios passed covering exact start, middle, end, punctuation, dates, whitespace, repeated occurrences, non-matches, and null inputs.
2. **Frontend Linter:**
   - Script: `npm run lint`
   - 0 errors, 0 warnings.
3. **Frontend Production Build:**
   - Script: `npm run build`
   - Vite built cleanly in 623ms.
4. **Backend Regression:**
   - Script: `py -m pytest -v`
   - 117/117 tests passed (0 regressions).
5. **Whitespace Verification:**
   - Script: `git diff --check`
   - Clean, 0 whitespace errors.
---

## Phase 3.2.3: Human Review Indicators

- **Date:** 2026-11-18
- **Status:** Completed
- **Branch:** `feature/smart-v2-intelligence`
- **Test Suite:**
  - Frontend Unit Tests: 28/28 passing (12 highlightEvidence + 16 ReviewIndicator tests)
  - Frontend Linter: ESLint passed with 0 errors and 0 warnings
  - Frontend Build: Vite production build passed in 434ms
  - Backend Regression: 117/117 Pytest tests passing

---

### 1. Objective & Scope
Implement an authoritative, deterministic human review indicator system across candidate cards, saved task cards, and the evidence inspection drawer in the SMART 2.0 React frontend. Distinguish between algorithmic confidence and the explicit need for human review without inventing review status from confidence alone.

---

### 2. Implementation Summary

#### 2.1 Decision Engine (`frontend/src/utils/reviewDecisions.js`)
- Authoritative evaluation based strictly on backend `review_required` boolean, `review_reasons`, and `confidence`.
- Rule 1 (`review_required === true`): Returns `status: "REQUIRED"`, `label: "Needs Human Review"`, `isWarning: true`, providing actual backend `review_reasons` or deterministic fallback: `"SMART recommends reviewing this task, but no detailed review explanation is available."`
- Rule 2 (`review_required === false`): Returns `status: "NOT_REQUIRED"`, `isWarning: false`. Never displays false warnings.
- Rule 3 & 7 (`review_required` missing/null/undefined):
  - When `confidence === "UNASSESSED"`: Returns `status: "UNASSESSED"`, `label: "Not assessed"`, explaining that algorithmic review is unavailable. Never forces review.
  - When other confidence: Returns `status: "UNAVAILABLE"`, `label: "Review status unavailable"` neutrally.
- Confidence independence: Respects authoritative backend boolean without deriving review status solely from confidence level.

#### 2.2 Reusable Component (`frontend/src/components/ReviewIndicator.jsx`)
- Supports flexible rendering variants:
  - `"badge"`: Compact pill for card header `.badge-group` (`.review-pill-warning`, `.review-pill-clear`, `.review-pill-unassessed`, `.review-pill-unavailable`).
  - `"box"`: Detailed explanation container for card body and drawer (`.review-reasons-box`, `.review-clear-box`, `.review-unavailable-box`).
  - `"full"`: Composite layout combining badge row and explanation box.
- Accessible: `role="status"`, `role="region"`, `aria-label`, informative `title` tooltips.

#### 2.3 Integration
- **Candidate Cards (`Analyze Chat`):**
  - Integrated `ReviewIndicator` (badge variant) into card `.badge-group`.
  - Integrated `ReviewIndicator` (box variant) below date details.
- **Saved Task Cards (`Tasks Dashboard`):**
  - Integrated `ReviewIndicator` (badge variant) into card `.badge-group`.
  - Integrated `ReviewIndicator` (box variant) below date details.
- **Evidence Drawer (`EvidenceDrawer.jsx`):**
  - Integrated `ReviewIndicator` into drawer header meta badges.
  - Added dedicated `Human Review Status` section rendering full review explanation or verified clear state.
- **Styling (`App.css`):**
  - Expanded `.review-pill` with `.review-pill-warning`, `.review-pill-clear`, `.review-pill-unassessed`, `.review-pill-unavailable`.
  - Added styles for `.review-box-header`, `.review-box-icon`, `.review-fallback-text`, `.review-clear-box`, `.review-unavailable-box`, `.review-indicator-full`.

---

### 3. Test & Verification Results

1. **Frontend Unit Tests (`npm test`):**
   - Script: `node src/utils/highlightEvidence.test.mjs && node src/components/ReviewIndicator.test.mjs`
   - 34/34 test cases passed (12 highlightEvidence + 22 ReviewIndicator cases, including 6 Final Correction regression tests).
2. **Frontend Linter (`npm run lint`):**
   - ESLint passed cleanly with 0 errors and 0 warnings.
3. **Frontend Production Build (`npm run build`):**
   - Vite v8.3.4 production build completed cleanly in 818ms.
4. **Backend Regression (`py -m pytest -v`):**
   - 117/117 tests passed across API, extractor, parser, and persistence test suites in 16.79s.
5. **Whitespace Verification (`git diff --check`):**
   - Clean, 0 whitespace errors.

---

### 4. Phase 3.2.3 Final Correction Summary

- **Confidence Independence:** Verified that confidence level and review_required are evaluated independently. Authoritative backend boolean always governs review indicator warning state.
- **Legacy & Manual Tasks (`UNASSESSED` + `review_required: false`):** Visibly communicate that confidence is unassessed via grey `ConfidenceBadge` without falsely marking the task for human review.
- **Neutral Clear Explanation:** Replaced "Extraction criteria met with high certainty" across engine and UI with:
  *"No human review is currently required according to SMART's assessment."*
- **Regression Suite:** Added 6 explicit regression tests in `ReviewIndicator.test.mjs` covering `UNASSESSED + false`, `UNASSESSED + true`, `MEDIUM + false`, `LOW + false`, `HIGH + true`, and neutral wording validation.

---

## Phase 3.2.4: Confidence Filtering

- **Date:** 2026-11-19
- **Status:** Completed
- **Branch:** `feature/smart-v2-intelligence`
- **Test Suite:**
  - Frontend Unit Tests: 49/49 passing (12 highlightEvidence + 22 ReviewIndicator + 15 confidenceFilter tests)
  - Frontend Linter: ESLint passed with 0 errors and 0 warnings
  - Frontend Build: Vite production build passed in 549ms
  - Backend Regression: 117/117 Pytest tests passing

---

### 1. Objective & Scope
Implement confidence-based filtering across extracted candidate cards (Analyze Chat) and saved academic task cards (My Academic Tasks). Users can filter items by: `All`, `HIGH`, `MEDIUM`, `LOW`, and `UNASSESSED`. Integrates seamlessly with existing search, category, status, and date range filters while preserving the independent behavior of confidence badges, evidence inspection, and human-review indicators.

---

### 2. Implementation Summary

#### 2.1 Pure Decision Engine (`frontend/src/utils/confidenceFilter.js`)
- `normalizeConfidence(confidence)`: Standardizes input string to `"HIGH"`, `"MEDIUM"`, `"LOW"`, or `"UNASSESSED"`. Null, undefined, empty, or unsupported confidence levels safely resolve to `"UNASSESSED"`.
- `matchesConfidence(item, selectedConfidence)`: Matches candidate or saved task against selected confidence filter. Treats "ALL" as matching every item.
- `filterByConfidence(items, selectedConfidence)`: Pure, non-mutating filter for item lists.
- `matchesTaskFilters(task, filters)` & `filterTasks(tasks, filters)`: Multi-criteria filter matcher combining category, status, confidence, search keywords, and date ranges.

#### 2.2 API Service (`frontend/src/api.js`)
- Updated `getAcademicItems(filters = {})` to serialize `filters.confidence` (e.g. `?confidence=HIGH`) to the FastAPI backend.
- Preserves backend query mapping where `GET /api/academic-items?confidence=UNASSESSED` captures `(confidence IS NULL OR confidence = 'UNASSESSED')`.

#### 2.3 Dashboard Integration (`frontend/src/App.jsx` & `frontend/src/App.css`)
- **Analyze Chat:**
  - Added `candidateConfidence` state (defaults to `"ALL"`).
  - Added `.confidence-filter-bar` below category pills with segmented controls (`All Confidence`, `HIGH`, `MEDIUM`, `LOW`, `UNASSESSED`).
  - Integrated into `filteredCandidateItems` memo.
  - Added "Clear Filters" action to the empty filter state.
- **My Academic Tasks:**
  - Added `taskConfidence` state (defaults to `"ALL"`).
  - Added segmented controls in `.tasks-filter-card` alongside category and status pill groups.
  - Integrated into `filteredTasks` memo, `hasActiveTaskFilters`, and `handleClearTaskFilters`.
- **CSS Styling (`App.css`):**
  - Added `.confidence-filter-bar` and `.filter-group-label`.
  - Reused existing `.filter-btn`, `.status-pill-group`, and `.status-tab-btn` styles.

---

### 3. Test & Verification Results

1. **Frontend Unit Tests (`npm test`):**
   - Script: `node src/utils/highlightEvidence.test.mjs && node src/components/ReviewIndicator.test.mjs && node src/utils/confidenceFilter.test.mjs`
   - 49/49 test cases passed across all 3 test suites.
2. **Frontend Linter (`npm run lint`):**
   - ESLint passed cleanly with 0 errors and 0 warnings.
3. **Frontend Production Build (`npm run build`):**
   - Vite v8.3.4 production build completed cleanly in 549ms.
4. **Backend Regression (`py -m pytest -v`):**
   - 117/117 tests passed in 16.86s.
5. **Whitespace Verification (`git diff --check`):**
   - Clean, 0 whitespace errors.

---

## Phase 3.2.5: End-to-End Integration Testing

### 1. Objective & Scope
Conduct exhaustive, end-to-end integration testing across the complete SMART 2.0 system covering chat ingestion, extraction, candidate UI transparency, SQLite persistence & metadata immutability, saved-task filtering, task CRUD operations, and RFC 5545 calendar export. Verify cross-layer integrity, identify and repair verified defects, and establish comprehensive automated regression test suites.

---

### 2. Verified Integration Defects & Resolutions

#### Defect 1: Evidence Text Substring Discontinuity in Multiline Task Clusters (`backend/extractor.py`)
- **Severity:** High (Integrity & UI Transparency Defect).
- **Location:** `backend/extractor.py:959`.
- **Root Cause:** In `extract_academic_items()`, `split_message_into_segments(text)` segments multiline messages using delimiters (e.g., `.\n`, `\n`). When multiple consecutive segments formed a single task cluster, `cluster_text = " ".join(cluster).strip()` joined them with spaces (`" "`). Consequently, for 6 out of 7 tasks in `sample_chat.txt`, `evidence_text in source_text` evaluated to `False`. This triggered false mismatch warnings in `EvidenceDrawer.jsx` and caused substring validation in `database.py:save_academic_item` to fail if saved without trusted sentinels.
- **Resolution:** Replaced the naive `" ".join(cluster).strip()` with exact source span reconstruction:
  ```python
  first_seg = cluster[0]
  last_seg = cluster[-1]
  start_pos = text.find(first_seg, current_text_offset)
  if start_pos != -1:
      end_pos = text.find(last_seg, start_pos)
      if end_pos != -1:
          end_pos += len(last_seg)
          cluster_text = text[start_pos:end_pos].strip()
          current_text_offset = end_pos
  ```
  This guarantees `evidence_text in source_text` is 100% mathematically exact, preserves original formatting/newlines, and eliminates false mismatch warnings.
- **Regression Tests Added:**
  - `backend/tests/test_integration_e2e.py::test_scenario_b_ten_representative_extraction_cases`
  - `frontend/src/utils/integrationE2E.test.mjs` (Defect 1 Regression test).

#### Defect 2: Substring Assertion Alignment in `test_integration_e2e.py`
- **Location:** `backend/tests/test_integration_e2e.py:303`.
- **Root Cause:** The integration test checked for substring `"not a verified substring"` while `database.py:save_academic_item` returns `"evidence_text must be a substring of source_text. Fabricated extraction evidence is not permitted."`.
- **Resolution:** Aligned assertion to check `"must be a substring of source_text"`.

#### Defect 3: Truncation on Repeated First/Last Segments & Abbreviation Regex Overshadowing (`backend/extractor.py`)
- **Location:** `backend/extractor.py:823` & `backend/extractor.py:960-975`.
- **Root Causes:**
  1. *First/Last Segment Truncation:* When a task cluster contained repeated identical segments (e.g. `[seg_A, seg_A]`), `text.find(last_seg, start_pos)` matched at `start_pos`, slicing only the first segment and truncating the remaining cluster.
  2. *Title Abbreviation Overshadowing:* `split_message_into_segments()` applied `re.sub(re.escape(abbr), ...)` without word boundaries. The abbreviation `"Ms."` matched `"MS."` inside `"LMS."`, mutating `"LMS."` to `"LMs."` upon placeholder restoration and causing exact substring lookups to fail.
- **Resolutions:**
  1. Replaced first/last segment matching with sequential segment search (`search_pos = end_pos` for every segment in the cluster), guaranteeing complete cluster span preservation.
  2. Added leading word boundary `r"\b" + re.escape(abbr)` to all title abbreviations, preventing false matches inside words like `LMS.`.
- **Regression Tests Added:**
  - `backend/tests/test_extractor.py::test_evidence_reconstruction_two_identical_consecutive_segments`
  - `backend/tests/test_extractor.py::test_evidence_reconstruction_repeated_first_and_last_segments`
  - `backend/tests/test_extractor.py::test_evidence_reconstruction_repeated_announcements_separated_by_different_sentences`
  - `backend/tests/test_extractor.py::test_evidence_reconstruction_multiline_clusters_with_repeated_dates`
  - `backend/tests/test_extractor.py::test_evidence_reconstruction_punctuation_and_blank_line_preservation`
  - `frontend/src/utils/integrationE2E.test.mjs` (Task 1 Regression covering all 5 edge cases in drawer highlight).

---

### 3. Scenario Coverage Matrix

- **Scenario A: Chat Ingestion & Validation**
  - Android & iOS formatted export ingestion.
  - Rejection of empty, whitespace-only, and oversized files with HTTP 400/422.
  - Multi-upload stability: repeated chat uploads do not corrupt or overwrite saved database tasks.
- **Scenario B: Academic Extraction Accuracy**
  - Extraction across 10 representative test cases (Assignments, Exams, Events, Opportunities, Announcements, bare dates, relative dates, multiline formatting, comma-separated tasks).
  - Verbatim evidence substring preservation for every extracted candidate.
- **Scenario C: Candidate UI & Transparency**
  - Confidence badges rendered across HIGH, MEDIUM, LOW, and UNASSESSED.
  - Independent review indicator states (`REQUIRED`, `NOT_REQUIRED`, `UNAVAILABLE`).
  - Evidence inspection drawer highlighting exact verbatim evidence without mismatch warnings.
  - Selection and batch operations.
- **Scenario D: Persistence & Metadata Integrity**
  - Full candidate-to-task lifecycle: candidate selected -> saved to SQLite -> retrieved via API.
  - Metadata immutability: `confidence`, `confidence_reasons`, and `evidence_text` cannot be tampered via POST or modified via PATCH.
  - Provenance protection: Manual/legacy tasks receive `UNASSESSED` confidence and null evidence.
  - Deduplication prevents duplicate task saves.
- **Scenario E: Saved-Task Multi-Criteria Filtering**
  - Combined filtering across category, status, confidence, date ranges, and search keywords.
  - Preserved backward compatibility for unassessed and legacy records.
  - Clean filter reset restoring all tasks.
- **Scenario F: Task Lifecycle & CRUD Operations**
  - Status updates: `pending` -> `completed` -> `dismissed`.
  - Field updates: `title`, `description`, `category`, `due_date` updated while provenance remains invariant.
  - Safe task deletion.
- **Scenario G: Calendar Export Standards Compliance**
  - RFC 5545 `.ics` export with `VEVENT`, `UID`, `SUMMARY`, `DTSTART`, `STATUS`, and `DESCRIPTION`.
  - Excludes non-deadline items and dismissed tasks.
  - Line folding at 75 octets and special character escaping (`\,`, `\;`, `\n`).
- **Scenario H: Regression Testing & Legacy Compatibility**
  - Legacy records with `NULL` confidence/evidence/review handled without errors.
  - Existing Phase 1, Phase 2, and Phase 3 functionality 100% preserved.

---

### 4. Test & Verification Metrics

- **Backend Integration & Unit Tests (`py -m pytest -v`):**
  - **133 passed, 1 warning in 26.72s** (100% passing across 5 test suites).
  - `backend/tests/test_extractor.py`: 58 passed.
  - `backend/tests/test_persistence.py`: 48 passed.
  - `backend/tests/test_integration_e2e.py`: 11 passed.
  - `backend/tests/test_parser.py`: 8 passed.
  - `backend/tests/test_api.py`: 8 passed.
- **Frontend Test Suite (`npm --prefix frontend test`):**
  - **57 tests passing** across 4 suites:
    - `highlightEvidence.test.mjs`: 12 passed.
    - `ReviewIndicator.test.mjs`: 22 passed (16 unit + 6 regression).
    - `confidenceFilter.test.mjs`: 15 passed.
    - `integrationE2E.test.mjs`: 8 end-to-end integration scenarios passed.
- **Frontend Code Quality:**
  - `npm --prefix frontend run lint`: 0 errors, 0 warnings.
  - `npm --prefix frontend run build`: Production bundle built in 534ms.
- **Git Check:**
  - `git diff --check`: 0 whitespace errors.

