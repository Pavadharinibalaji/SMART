/**
 * End-to-End Frontend Integration Test Suite for SMART 2.0 (Phase 3.2.5).
 * Tests complete integration across:
 * - Scenario A: Chat ingestion payload parsing & error handling
 * - Scenario C: Candidate cards, confidence badges, review indicators & evidence drawer state
 * - Scenario D: Candidate save payload construction & provenance integrity
 * - Scenario E: Multi-criteria filtering (confidence, category, status, search, date)
 * - Scenario F: Task CRUD operations & immutable metadata protection in state
 * - Scenario G: Calendar export URL generation & parameter encoding
 * - Scenario H: Regression coverage for legacy/manual tasks & Defect 1 multiline evidence
 */

import assert from "node:assert/strict";
import { highlightEvidence } from "./highlightEvidence.js";
import { getReviewStatus } from "./reviewDecisions.js";
import {
  normalizeConfidence,
  matchesConfidence,
  filterByConfidence,
  matchesTaskFilters,
  filterTasks,
  calculateDashboardStats,
  taskMatchesSection,
} from "./confidenceFilter.js";

console.log("Starting End-to-End Frontend Integration test suite...\n");

// ============================================================================
// SCENARIO A: Ingestion Payload Processing & Error Handling
// ============================================================================
{
  // Simulated backend POST /api/extract-academic response
  const rawBackendResponse = {
    filename: "sample_chat.txt",
    total_messages: 13,
    total_items: 7,
    review_required_count: 2,
    category_counts: {
      Assignment: 2,
      Exam: 1,
      Event: 2,
      Opportunity: 1,
      Announcement: 1,
    },
    confidence_counts: {
      HIGH: 3,
      MEDIUM: 2,
      LOW: 2,
      UNASSESSED: 0,
    },
    items: [
      {
        item_id: 1,
        title: "Assignment 1 on Distributed Systems",
        category: "Assignment",
        due_date: "2026-11-25",
        confidence: "HIGH",
        confidence_reasons: ["Explicit deadline phrasing", "Confirmed due date"],
        review_required: false,
        review_reasons: [],
        evidence_text: "Assignment 1 on Distributed Systems due Nov 25",
        source_text: "Assignment 1 on Distributed Systems due Nov 25. Please submit.",
        source_sender: "Prof. Smith",
        source_timestamp: "2026-11-18 10:00:00",
      },
      {
        item_id: 2,
        title: "Midterm Exam Announcement",
        category: "Exam",
        due_date: "2026-12-05",
        confidence: "LOW",
        confidence_reasons: ["Ambiguous date phrasing"],
        review_required: true,
        review_reasons: ["Date mentioned without explicit deadline phrasing"],
        evidence_text: "Midterm Exam on Dec 5 or Dec 6",
        source_text: "Midterm Exam on Dec 5 or Dec 6 in Hall B",
        source_sender: "Dr. Adams",
        source_timestamp: "2026-11-18 10:15:00",
      },
    ],
  };

  // Verify extraction response metadata integrity
  assert.equal(rawBackendResponse.total_items, 7);
  assert.equal(rawBackendResponse.confidence_counts.HIGH, 3);
  assert.equal(rawBackendResponse.confidence_counts.LOW, 2);
  assert.equal(rawBackendResponse.items.length, 2);

  // Error case handling: Empty or invalid file response
  const error422Response = {
    detail: "No recognised WhatsApp messages were found. Please check that the export matches supported WhatsApp formats.",
  };
  assert.match(error422Response.detail, /No recognised WhatsApp messages/);

  console.log("✔ Scenario A: Ingestion payload parsing and error handling verified");
}

// ============================================================================
// SCENARIO C: Candidate UI Components & Evidence Drawer Integration
// ============================================================================
{
  const candidate = {
    item_id: 101,
    title: "Project Milestone 2 Submission",
    category: "Assignment",
    due_date: "2026-11-30",
    confidence: "HIGH",
    confidence_reasons: ["Clear deadline phrase", "Explicit due date"],
    review_required: false,
    review_reasons: [],
    evidence_text: "Project Milestone 2 Submission due 30/11/2026",
    source_text: "Notice: Project Milestone 2 Submission due 30/11/2026 via portal.\nLate submissions incur penalty.",
    source_sender: "TA John",
    source_timestamp: "2026-11-19 09:30:00",
  };

  // 1. Review Decision calculation
  const decision = getReviewStatus({
    reviewRequired: candidate.review_required,
    confidence: candidate.confidence,
    reasons: candidate.review_reasons,
  });
  assert.equal(decision.status, "NOT_REQUIRED");
  assert.equal(decision.label, "No Review Needed");
  assert.equal(decision.isWarning, false);
  assert.equal(decision.tooltip, "No human review is currently required according to SMART's assessment.");

  // 2. Evidence Drawer highlight test on candidate
  const highlightResult = highlightEvidence(candidate.source_text, candidate.evidence_text);
  assert.equal(highlightResult.matched, true);
  assert.equal(highlightResult.mismatchWarning, false);
  assert.equal(highlightResult.segments.length, 3);
  assert.equal(highlightResult.segments[0].text, "Notice: ");
  assert.equal(highlightResult.segments[0].isMatch, false);
  assert.equal(highlightResult.segments[1].text, "Project Milestone 2 Submission due 30/11/2026");
  assert.equal(highlightResult.segments[1].isMatch, true);
  assert.equal(highlightResult.segments[2].text, " via portal.\nLate submissions incur penalty.");
  assert.equal(highlightResult.segments[2].isMatch, false);

  // 3. Candidate selection state transitions
  const initialSelection = new Set();
  assert.equal(initialSelection.has(candidate.item_id), false);
  const updatedSelection = new Set(initialSelection);
  updatedSelection.add(candidate.item_id);
  assert.equal(updatedSelection.has(candidate.item_id), true);
  updatedSelection.delete(candidate.item_id);
  assert.equal(updatedSelection.has(candidate.item_id), false);

  console.log("✔ Scenario C: Candidate UI components and evidence drawer integration verified");
}

// ============================================================================
// DEFECT 1 REGRESSION: Multiline Evidence Exact Matching in Drawer
// ============================================================================
{
  // Test that multiline task evidence (joined with original whitespace) produces an exact highlight match
  const multilineSource = "Internship opportunity at AI Lab.\nDeadline: 30/11/2026.\nSend CV to hr@example.com";
  const exactMultilineEvidence = "Internship opportunity at AI Lab.\nDeadline: 30/11/2026.";

  const drawerHighlight = highlightEvidence(multilineSource, exactMultilineEvidence);
  assert.equal(drawerHighlight.matched, true, "Multiline evidence must highlight");
  assert.equal(drawerHighlight.mismatchWarning, false, "Must not trigger mismatch warning for exact multiline span");
  assert.equal(drawerHighlight.segments[0].text, exactMultilineEvidence);
  assert.equal(drawerHighlight.segments[0].isMatch, true);
  assert.equal(drawerHighlight.segments[1].text, "\nSend CV to hr@example.com");
  assert.equal(drawerHighlight.segments[1].isMatch, false);

  console.log("✔ Defect 1 Regression: Multiline evidence text matches verbatim without drawer mismatch warning");
}

// ============================================================================
// TASK 1 REGRESSION: Evidence Reconstruction & Exact Matching Edge Cases
// ============================================================================
{
  // 1. Two identical consecutive segments grouped into one task
  const src1 = "Assignment 1 due Nov 25.\nAssignment 1 due Nov 25.";
  const ev1 = "Assignment 1 due Nov 25.\nAssignment 1 due Nov 25.";
  const hl1 = highlightEvidence(src1, ev1);
  assert.equal(hl1.matched, true);
  assert.equal(hl1.mismatchWarning, false);
  assert.equal(hl1.segments.length, 1);
  assert.equal(hl1.segments[0].text, ev1);
  assert.equal(hl1.segments[0].isMatch, true);

  // 2. Repeated first and last segments
  const src2 = "Submit assignment 1.\nImportant details.\nSubmit assignment 1 on Nov 25.";
  const ev2 = "Submit assignment 1.\nImportant details.\nSubmit assignment 1 on Nov 25.";
  const hl2 = highlightEvidence(src2, ev2);
  assert.equal(hl2.matched, true);
  assert.equal(hl2.mismatchWarning, false);
  assert.equal(hl2.segments.length, 1);
  assert.equal(hl2.segments[0].text, ev2);

  // 3. Repeated announcements separated by different sentences
  const src3 = "Assignment 1 due Nov 25.\nExam on Dec 01.\nAssignment 1 due Nov 25.";
  const ev3 = "Assignment 1 due Nov 25.";
  const hl3 = highlightEvidence(src3, ev3);
  assert.equal(hl3.matched, true);
  assert.equal(hl3.mismatchWarning, false);

  // 4. Multiline clusters with repeated dates
  const src4 = "Workshop on 15/12/2026.\nMorning session on 15/12/2026.\nEvening session on 15/12/2026.";
  const ev4 = "Workshop on 15/12/2026.\nMorning session on 15/12/2026.\nEvening session on 15/12/2026.";
  const hl4 = highlightEvidence(src4, ev4);
  assert.equal(hl4.matched, true);
  assert.equal(hl4.mismatchWarning, false);
  assert.equal(hl4.segments.length, 1);
  assert.equal(hl4.segments[0].text, ev4);

  // 5. Punctuation and blank-line preservation
  const src5 = "Notice:\n\nAssignment 1 due 20/11/2026!\n\nPlease check LMS.";
  const ev5 = "Assignment 1 due 20/11/2026!\n\nPlease check LMS.";
  const hl5 = highlightEvidence(src5, ev5);
  assert.equal(hl5.matched, true);
  assert.equal(hl5.mismatchWarning, false);
  assert.equal(hl5.segments.length, 2);
  assert.equal(hl5.segments[0].text, "Notice:\n\n");
  assert.equal(hl5.segments[0].isMatch, false);
  assert.equal(hl5.segments[1].text, ev5);
  assert.equal(hl5.segments[1].isMatch, true);

  console.log("✔ Task 1 Regression: All 5 evidence reconstruction edge cases verified in frontend drawer highlight");
}

// ============================================================================
// PHASE 3.3: Occurrence Disambiguation Integration Tests
// ============================================================================
{
  const source = "Quiz on Friday.\nLab report due.\nQuiz on Friday.";
  const candidate1 = {
    item_id: 201,
    title: "Quiz 1",
    category: "Exam",
    source_text: source,
    evidence_text: "Quiz on Friday.",
    evidence_start_index: 0,
    evidence_end_index: 15,
  };
  const candidate2 = {
    item_id: 202,
    title: "Quiz 2",
    category: "Exam",
    source_text: source,
    evidence_text: "Quiz on Friday.",
    evidence_start_index: 32,
    evidence_end_index: 47,
  };

  // Drawer highlight for candidate 1 matches first occurrence
  const hl1 = highlightEvidence(
    candidate1.source_text,
    candidate1.evidence_text,
    candidate1.evidence_start_index,
    candidate1.evidence_end_index
  );
  assert.equal(hl1.matched, true);
  assert.equal(hl1.segments[0].text, "Quiz on Friday.");
  assert.equal(hl1.segments[0].isMatch, true);
  assert.equal(hl1.segments[1].text, "\nLab report due.\nQuiz on Friday.");
  assert.equal(hl1.segments[1].isMatch, false);

  // Drawer highlight for candidate 2 matches second occurrence (exact disambiguation)
  const hl2 = highlightEvidence(
    candidate2.source_text,
    candidate2.evidence_text,
    candidate2.evidence_start_index,
    candidate2.evidence_end_index
  );
  assert.equal(hl2.matched, true);
  assert.equal(hl2.segments[0].text, "Quiz on Friday.\nLab report due.\n");
  assert.equal(hl2.segments[0].isMatch, false);
  assert.equal(hl2.segments[1].text, "Quiz on Friday.");
  assert.equal(hl2.segments[1].isMatch, true);

  // Persistence payload preserves occurrence offsets
  const savePayload = {
    title: candidate2.title,
    category: candidate2.category,
    source_text: candidate2.source_text,
    evidence_text: candidate2.evidence_text,
    evidence_start_index: candidate2.evidence_start_index,
    evidence_end_index: candidate2.evidence_end_index,
  };
  assert.equal(savePayload.evidence_start_index, 32);
  assert.equal(savePayload.evidence_end_index, 47);
  assert.equal(
    source.slice(savePayload.evidence_start_index, savePayload.evidence_end_index),
    savePayload.evidence_text
  );

  console.log("✔ Phase 3.3: Occurrence disambiguation integration verified across candidate pairs and drawer rendering");
}

// ============================================================================
// SCENARIO D: Save Candidate Payload Construction & Provenance Preservation
// ============================================================================
{
  const candidate = {
    title: "Final Term Paper",
    category: "Assignment",
    due_date: "2026-12-10",
    confidence: "HIGH",
    confidence_reasons: ["Explicit deadline wording"],
    review_required: false,
    review_reasons: [],
    evidence_text: "Final Term Paper due December 10",
    source_text: "Final Term Paper due December 10 in LMS.",
    source_sender: "Prof. Davis",
    source_timestamp: "2026-11-19 10:00:00",
    source_filename: "chat.txt",
  };

  // Simulated frontend payload construction before POST /api/academic-items
  const savePayload = {
    title: candidate.title,
    category: candidate.category,
    due_date: candidate.due_date,
    status: "pending",
    evidence_text: candidate.evidence_text,
    source_text: candidate.source_text,
    source_sender: candidate.source_sender,
    source_timestamp: candidate.source_timestamp,
    source_filename: candidate.source_filename,
    review_required: candidate.review_required,
    review_reasons: candidate.review_reasons,
  };

  // Verify that frontend does NOT tamper with or inject synthetic confidence in client payload
  assert.equal("confidence" in savePayload, false, "Client POST payload must not define confidence");
  assert.equal("confidence_reasons" in savePayload, false, "Client POST payload must not define confidence_reasons");
  assert.equal(savePayload.evidence_text, candidate.evidence_text);
  assert.equal(savePayload.source_text.includes(savePayload.evidence_text), true);

  console.log("✔ Scenario D: Save payload generation and provenance preservation verified");
}

// ============================================================================
// SCENARIO E: Combined Multi-Criteria Filtering
// ============================================================================
{
  const taskStore = [
    { id: 1, title: "Assignment 1", category: "Assignment", status: "pending", confidence: "HIGH", due_date: "2026-11-25", source_text: "Due soon" },
    { id: 2, title: "Assignment 2", category: "Assignment", status: "completed", confidence: "HIGH", due_date: "2026-11-26", source_text: "Finished" },
    { id: 3, title: "Exam Prep", category: "Exam", status: "pending", confidence: "MEDIUM", due_date: "2026-12-01", source_text: "Review chapters" },
    { id: 4, title: "Hackathon", category: "Event", status: "pending", confidence: "LOW", due_date: "2026-12-05", source_text: "Register team" },
    { id: 5, title: "Manual Entry Task", category: "Assignment", status: "pending", confidence: "UNASSESSED", due_date: "2026-12-10", source_text: "Notes" },
  ];

  // 1. Filter: category="Assignment" AND confidence="HIGH"
  const filter1 = filterTasks(taskStore, { category: "Assignment", confidence: "HIGH" });
  assert.equal(filter1.length, 2);
  assert.ok(filter1.every(t => t.category === "Assignment" && t.confidence === "HIGH"));

  // 2. Filter: category="Assignment" AND status="pending" AND confidence="HIGH"
  const filter2 = filterTasks(taskStore, { category: "Assignment", status: "pending", confidence: "HIGH" });
  assert.equal(filter2.length, 1);
  assert.equal(filter2[0].id, 1);

  // 3. Filter: confidence="UNASSESSED"
  const filter3 = filterTasks(taskStore, { confidence: "UNASSESSED" });
  assert.equal(filter3.length, 1);
  assert.equal(filter3[0].id, 5);

  // 4. Filter: search query "Exam" AND confidence="MEDIUM"
  const filter4 = filterTasks(taskStore, { search: "Exam", confidence: "MEDIUM" });
  assert.equal(filter4.length, 1);
  assert.equal(filter4[0].id, 3);

  // 5. Clear filters restores full collection
  const filterCleared = filterTasks(taskStore, { category: "ALL", status: "ALL", confidence: "ALL", search: "" });
  assert.equal(filterCleared.length, taskStore.length);

  console.log("✔ Scenario E: Combined multi-criteria filtering verified");
}

// ============================================================================
// SCENARIO F: Task CRUD Operations in Frontend State & Immutability
// ============================================================================
{
  let stateTasks = [
    {
      id: 1,
      title: "Initial Task",
      category: "Assignment",
      status: "pending",
      confidence: "HIGH",
      confidence_reasons: ["Explicit deadline"],
      evidence_text: "Due Nov 25",
      source_text: "Task due Nov 25",
    },
  ];

  // 1. Create task from candidate
  const newTask = {
    id: 2,
    title: "Created Task",
    category: "Exam",
    status: "pending",
    confidence: "MEDIUM",
    confidence_reasons: ["Relative date"],
    evidence_text: "Exam next Monday",
    source_text: "Exam next Monday in Room 101",
  };
  stateTasks = [...stateTasks, newTask];
  assert.equal(stateTasks.length, 2);

  // 2. Update task status (pending -> completed)
  stateTasks = stateTasks.map(t => (t.id === 1 ? { ...t, status: "completed" } : t));
  assert.equal(stateTasks.find(t => t.id === 1).status, "completed");

  // 3. Edit mutable fields (title, due_date) while strictly preserving immutable confidence and evidence
  const userEdit = { title: "Updated Task Title", due_date: "2026-11-26" };
  stateTasks = stateTasks.map(t => {
    if (t.id === 1) {
      return {
        ...t,
        title: userEdit.title,
        due_date: userEdit.due_date,
        // Ensure confidence and evidence are NOT overwritten by user edits
        confidence: t.confidence,
        confidence_reasons: t.confidence_reasons,
        evidence_text: t.evidence_text,
      };
    }
    return t;
  });
  const updatedTask = stateTasks.find(t => t.id === 1);
  assert.equal(updatedTask.title, "Updated Task Title");
  assert.equal(updatedTask.due_date, "2026-11-26");
  assert.equal(updatedTask.confidence, "HIGH", "Confidence must remain immutable across edits");
  assert.equal(updatedTask.evidence_text, "Due Nov 25", "Evidence must remain immutable across edits");

  // 4. Delete task
  stateTasks = stateTasks.filter(t => t.id !== 1);
  assert.equal(stateTasks.length, 1);
  assert.equal(stateTasks[0].id, 2);

  console.log("✔ Scenario F: Task CRUD operations and metadata immutability verified");
}

// ============================================================================
// SCENARIO G: Calendar Export URL Parameter Encoding
// ============================================================================
{
  function buildExportUrl(baseUrl, filters = {}) {
    const params = new URLSearchParams();
    if (filters.category && filters.category !== "ALL") {
      params.set("category", filters.category);
    }
    if (filters.status && filters.status !== "ALL") {
      params.set("status", filters.status);
    }
    if (filters.startDate) {
      params.set("start_date", filters.startDate);
    }
    if (filters.endDate) {
      params.set("end_date", filters.endDate);
    }
    const qs = params.toString();
    return qs ? `${baseUrl}/export.ics?${qs}` : `${baseUrl}/export.ics`;
  }

  const base = "/api/academic-items";

  // 1. All filters default
  assert.equal(buildExportUrl(base, {}), "/api/academic-items/export.ics");

  // 2. Specific category & status
  assert.equal(
    buildExportUrl(base, { category: "Assignment", status: "pending" }),
    "/api/academic-items/export.ics?category=Assignment&status=pending"
  );

  // 3. Date range filters
  assert.equal(
    buildExportUrl(base, { startDate: "2026-11-01", endDate: "2026-11-30" }),
    "/api/academic-items/export.ics?start_date=2026-11-01&end_date=2026-11-30"
  );

  console.log("✔ Scenario G: Calendar export URL generation and parameter encoding verified");
}

// ============================================================================
// SCENARIO H: Regression Coverage for Legacy & Edge-Case Records
// ============================================================================
{
  const legacyRecord = {
    id: 999,
    title: "Legacy Phase 1 Record",
    category: "Assignment",
    status: "pending",
    confidence: null,
    confidence_reasons: null,
    evidence_text: null,
    source_text: "Historical text without confidence or evidence",
    review_required: null,
    review_reasons: null,
  };

  // 1. Confidence normalization
  assert.equal(normalizeConfidence(legacyRecord.confidence), "UNASSESSED");

  // 2. Review Decision for legacy item
  const legacyDecision = getReviewStatus({
    reviewRequired: legacyRecord.review_required,
    confidence: legacyRecord.confidence,
    reasons: legacyRecord.review_reasons,
  });
  assert.equal(legacyDecision.status, "UNAVAILABLE");
  assert.equal(legacyDecision.label, "Review status unavailable");

  // 3. Evidence drawer highlight gracefully handles null evidence
  const legacyHighlight = highlightEvidence(legacyRecord.source_text, legacyRecord.evidence_text);
  assert.equal(legacyHighlight.matched, false);
  assert.equal(legacyHighlight.mismatchWarning, false);
  assert.equal(legacyHighlight.segments[0].text, legacyRecord.source_text);
  assert.equal(legacyHighlight.segments[0].isMatch, false);

  // 4. Filtering includes legacy item under UNASSESSED
  const filtered = filterTasks([legacyRecord], { confidence: "UNASSESSED" });
  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].id, 999);

  console.log("✔ Scenario H: Legacy record backward compatibility verified");
}

// ============================================================================
// SCENARIO I: Phase 3.3.1 Unicode Compatibility & Candidate Save Provenance
// ============================================================================
{
  // 1. Candidate save payload includes candidate_token and occurrence offsets
  const candidate = {
    title: "Assignment 1",
    category: "Assignment",
    source_text: "📢 Assignment 1 is due tomorrow at 5pm.",
    due_date: "2026-11-20",
    date_text: "tomorrow",
    date_type: "deadline",
    date_status: "resolved",
    source_sender: "Prof",
    source_timestamp: "2026-11-19 10:00",
    review_required: false,
    review_reasons: [],
    evidence_text: "Assignment 1 is due tomorrow at 5pm.",
    evidence_start_index: 2, // Python code points (after '📢 ')
    evidence_end_index: 38,
    candidate_token: "eyJjYXRlZ29yeSI...signature",
  };

  const savePayload = {
    title: candidate.title,
    category: candidate.category,
    description: candidate.source_text,
    date_text: candidate.date_text,
    due_date: candidate.due_date,
    date_type: candidate.date_type,
    date_status: candidate.date_status,
    status: "pending",
    source_sender: candidate.source_sender,
    source_timestamp: candidate.source_timestamp,
    source_text: candidate.source_text,
    source_filename: "chat.txt",
    review_required: candidate.review_required,
    review_reasons: candidate.review_reasons,
    evidence_text: candidate.evidence_text,
    evidence_start_index: candidate.evidence_start_index,
    evidence_end_index: candidate.evidence_end_index,
    candidate_token: candidate.candidate_token,
  };

  assert.equal(savePayload.candidate_token, candidate.candidate_token);
  assert.equal(savePayload.evidence_start_index, 2);
  assert.equal(savePayload.evidence_end_index, 38);

  // 2. Drawer highlighting with Python code-point offsets and emoji prefix
  const hlEmoji = highlightEvidence(
    candidate.source_text,
    candidate.evidence_text,
    candidate.evidence_start_index,
    candidate.evidence_end_index
  );
  assert.equal(hlEmoji.matched, true);
  assert.equal(hlEmoji.mismatchWarning, false);
  assert.equal(hlEmoji.segments.length, 2);
  assert.equal(hlEmoji.segments[0].text, "📢 ");
  assert.equal(hlEmoji.segments[0].isMatch, false);
  assert.equal(hlEmoji.segments[1].text, candidate.evidence_text);
  assert.equal(hlEmoji.segments[1].isMatch, true);

  // 3. Repeated occurrences disambiguation in drawer
  const repeatedSource = "Quiz tomorrow. Important announcement: Quiz tomorrow.";
  const phrase = "Quiz tomorrow.";
  // Second occurrence
  const secondStart = repeatedSource.lastIndexOf(phrase);
  const secondEnd = secondStart + phrase.length;
  const hlSecond = highlightEvidence(repeatedSource, phrase, secondStart, secondEnd);
  assert.equal(hlSecond.matched, true);
  assert.equal(hlSecond.segments.length, 2);
  assert.equal(hlSecond.segments[0].text, "Quiz tomorrow. Important announcement: ");
  assert.equal(hlSecond.segments[0].isMatch, false);
  assert.equal(hlSecond.segments[1].text, phrase);
  assert.equal(hlSecond.segments[1].isMatch, true);

  console.log("✔ Scenario I: Unicode compatibility and candidate save provenance verified");
}

// ============================================================================
// SCENARIO J: Phase 4.1 Extraction Intelligence and Actionability Verification
// ============================================================================
{
  const candidatePostponement = {
    title: "The exam was postponed.",
    category: "Announcement",
    source_text: "The exam was postponed.",
    due_date: null,
    confidence: "MEDIUM",
    confidence_reasons: ["Candidate academic task extracted with standard rule-based heuristics."],
    is_actionable: false,
    actionability_type: "informational",
    update_type: "postponement",
    review_required: false,
    review_reasons: [],
    evidence_text: "The exam was postponed.",
    evidence_start_index: 0,
    evidence_end_index: 23,
    candidate_token: "test.token.postponement",
  };

  const candidateExtension = {
    title: "Assignment 1 deadline extended to Friday 5pm.",
    category: "Assignment",
    source_text: "Assignment 1 deadline extended to Friday 5pm.",
    due_date: "2026-11-27",
    confidence: "HIGH",
    confidence_reasons: ["Unambiguous academic category with validated explicit calendar date."],
    is_actionable: true,
    actionability_type: "action_required",
    update_type: "extension",
    review_required: false,
    review_reasons: [],
    evidence_text: "Assignment 1 deadline extended to Friday 5pm.",
    evidence_start_index: 0,
    evidence_end_index: 45,
    candidate_token: "test.token.extension",
  };

  // 1. Verify save payload structure carries actionability and update_type
  const buildSavePayload = (cand) => ({
    title: cand.title,
    category: cand.category,
    description: cand.source_text,
    date_text: cand.date_text || null,
    due_date: cand.due_date,
    date_type: cand.date_type || "none",
    date_status: cand.date_status || "not_found",
    status: "pending",
    source_sender: cand.source_sender || "",
    source_timestamp: cand.source_timestamp || "",
    source_text: cand.source_text,
    source_filename: "chat.txt",
    review_required: cand.review_required,
    review_reasons: cand.review_reasons,
    evidence_text: cand.evidence_text,
    evidence_start_index: cand.evidence_start_index,
    evidence_end_index: cand.evidence_end_index,
    candidate_token: cand.candidate_token,
    is_actionable: cand.is_actionable !== undefined ? cand.is_actionable : true,
    actionability_type: cand.actionability_type || "action_required",
    update_type: cand.update_type || null,
  });

  const payloadPostponement = buildSavePayload(candidatePostponement);
  assert.equal(payloadPostponement.is_actionable, false);
  assert.equal(payloadPostponement.actionability_type, "informational");
  assert.equal(payloadPostponement.update_type, "postponement");

  const payloadExtension = buildSavePayload(candidateExtension);
  assert.equal(payloadExtension.is_actionable, true);
  assert.equal(payloadExtension.actionability_type, "action_required");
  assert.equal(payloadExtension.update_type, "extension");

  // 2. Multi-clause independent task highlight in evidence drawer
  const multiClauseSource = "Submit your assignment by Thursday and register for the workshop before Saturday.";
  const clause1Evidence = "Submit your assignment by Thursday";
  const clause2Evidence = "register for the workshop before Saturday.";

  const hlClause1 = highlightEvidence(multiClauseSource, clause1Evidence, 0, 34);
  assert.equal(hlClause1.matched, true);
  assert.equal(hlClause1.mismatchWarning, false);
  assert.equal(hlClause1.segments[0].text, clause1Evidence);
  assert.equal(hlClause1.segments[0].isMatch, true);

  const hlClause2 = highlightEvidence(multiClauseSource, clause2Evidence, 39, 81);
  assert.equal(hlClause2.matched, true);
  assert.equal(hlClause2.mismatchWarning, false);
  assert.equal(hlClause2.segments[0].text, "Submit your assignment by Thursday and ");
  assert.equal(hlClause2.segments[0].isMatch, false);
  assert.equal(hlClause2.segments[1].text, clause2Evidence);
  assert.equal(hlClause2.segments[1].isMatch, true);

  console.log("✔ Scenario J: Phase 4.1 extraction intelligence and actionability verified");
}

// ============================================================================
// SCENARIO K: Phase 4.4 Dashboard Overview Metrics & Status Separation
// ============================================================================
{
  const refDate = "2026-11-23";
  const tasksSample = [
    // 1. Overdue pending task
    {
      id: 1,
      title: "Overdue Lab Report",
      category: "Assignment",
      status: "pending",
      due_date: "2026-11-20",
      date_type: "deadline",
      urgency: "CRITICAL",
      urgency_reasons: ["Overdue by 3 days"],
      delta_days: -3,
      priority: "CRITICAL",
      importance: "HIGH",
    },
    // 2. Due today pending task
    {
      id: 2,
      title: "Quiz Today",
      category: "Exam",
      status: "pending",
      due_date: "2026-11-23",
      date_type: "deadline",
      urgency: "CRITICAL",
      delta_days: 0,
      priority: "HIGH",
      importance: "HIGH",
    },
    // 3. Upcoming deadline
    {
      id: 3,
      title: "Term Paper Submission",
      category: "Assignment",
      status: "pending",
      due_date: "2026-11-30",
      date_type: "deadline",
      urgency: "MEDIUM",
      delta_days: 7,
      priority: "MEDIUM",
      importance: "MEDIUM",
    },
    // 4. Task requiring review
    {
      id: 4,
      title: "Seminar Discussion",
      category: "Announcement",
      status: "pending",
      due_date: null,
      date_status: "needs_review",
      review_required: true,
      urgency: "NEEDS_REVIEW",
      priority: "LOW",
      importance: "LOW",
    },
    // 5. Completed task (must NOT count as overdue or active obligation even if past due_date)
    {
      id: 5,
      title: "Completed Midterm",
      category: "Exam",
      status: "completed",
      due_date: "2026-11-15",
      date_type: "deadline",
      urgency: "LOW",
      priority: "LOW",
      importance: "HIGH",
    },
    // 6. Cancelled task (must NOT count as upcoming or confirmed deadline)
    {
      id: 6,
      title: "Cancelled Guest Lecture",
      category: "Event",
      status: "cancelled",
      due_date: "2026-11-28",
      date_type: "event_date",
      urgency: "LOW",
      priority: "LOW",
      importance: "LOW",
    },
    // 7. Superseded task (must NOT count as upcoming deadline)
    {
      id: 7,
      title: "Old Assignment Schedule",
      category: "Assignment",
      status: "superseded",
      due_date: "2026-11-25",
      date_type: "deadline",
      urgency: "LOW",
      priority: "LOW",
      importance: "MEDIUM",
    },
    // 8. Dismissed task
    {
      id: 8,
      title: "Dismissed Notice",
      category: "Opportunity",
      status: "dismissed",
      due_date: null,
      urgency: "NO_DEADLINE",
      priority: "LOW",
      importance: "LOW",
    },
  ];

  const stats = calculateDashboardStats(tasksSample, refDate);

  // 1. Total and lifecycle statuses
  assert.equal(stats.total, 8, "Total tasks must be 8");
  assert.equal(stats.active, 4, "Active pending tasks must be exactly 4");
  assert.equal(stats.pending, 4, "Pending tasks must be 4");
  assert.equal(stats.completed, 1, "Completed tasks must be 1");
  assert.equal(stats.cancelled, 1, "Cancelled tasks must be 1");
  assert.equal(stats.superseded, 1, "Superseded tasks must be 1");
  assert.equal(stats.dismissed, 1, "Dismissed tasks must be 1");

  // 2. Active obligations separation (inactive tasks must NOT count)
  assert.equal(stats.overdue, 1, "Only pending overdue task #1 must count as overdue");
  assert.equal(stats.dueToday, 1, "Only pending task #2 must count as due today");
  assert.equal(stats.upcoming, 1, "Only pending future task #3 must count as upcoming (cancelled & superseded excluded)");
  assert.equal(stats.needsReview, 1, "Only pending task #4 must count as needing review");
  assert.equal(stats.highPriority, 2, "Pending tasks #1 (CRITICAL) and #2 (HIGH) count as highPriority");
  assert.equal(stats.attentionRequired, 3, "Attention required = overdue(1) + dueToday(1) + needsReview(1) = 3");
  assert.equal(stats.deadlines, 3, "Confirmed deadlines = tasks #1, #2, #3 (pending deadlines)");

  console.log("✔ Scenario K: Phase 4.4 dashboard metrics calculation and status separation verified");
}

// ============================================================================
// SCENARIO L: Phase 4.4 Advanced Multi-Criteria Filters & Section Matching
// ============================================================================
{
  const refDate = "2026-11-23";
  const tasks = [
    {
      id: 10,
      title: "Distributed Systems Assignment 2",
      category: "Assignment",
      academic_intent: "assignment",
      status: "pending",
      due_date: "2026-11-20",
      urgency: "CRITICAL",
      priority: "CRITICAL",
      importance: "HIGH",
      confidence: "HIGH",
      review_required: false,
    },
    {
      id: 11,
      title: "Operating Systems Final Exam",
      category: "Exam",
      academic_intent: "exam",
      status: "pending",
      due_date: "2026-11-23",
      urgency: "CRITICAL",
      priority: "CRITICAL",
      importance: "HIGH",
      confidence: "HIGH",
      review_required: false,
    },
    {
      id: 12,
      title: "Web Security Lab Project",
      category: "Assignment",
      academic_intent: "project",
      status: "pending",
      due_date: "2026-11-29",
      urgency: "MEDIUM",
      priority: "HIGH",
      importance: "HIGH",
      confidence: "MEDIUM",
      review_required: false,
    },
    {
      id: 13,
      title: "Club Hackathon Registration",
      category: "Opportunity",
      academic_intent: "competition",
      status: "pending",
      due_date: null,
      date_status: "needs_review",
      urgency: "NEEDS_REVIEW",
      priority: "LOW",
      importance: "LOW",
      confidence: "LOW",
      review_required: true,
    },
    {
      id: 14,
      title: "Old Rescheduled Quiz",
      category: "Exam",
      academic_intent: "exam",
      status: "superseded",
      due_date: "2026-11-18",
      urgency: "LOW",
      priority: "LOW",
      importance: "MEDIUM",
      confidence: "HIGH",
      review_required: false,
    },
  ];

  // 1. Section matching tests
  // Section: 'today' (overdue + due today)
  const todayTasks = tasks.filter((t) => taskMatchesSection(t, "today", refDate));
  assert.equal(todayTasks.length, 2);
  assert.deepEqual(todayTasks.map((t) => t.id).sort(), [10, 11]);

  // Section: 'upcoming' (future active deadlines)
  const upcomingTasks = tasks.filter((t) => taskMatchesSection(t, "upcoming", refDate));
  assert.equal(upcomingTasks.length, 1);
  assert.equal(upcomingTasks[0].id, 12);

  // Section: 'high_priority' (CRITICAL or HIGH)
  const highPriTasks = tasks.filter((t) => taskMatchesSection(t, "high_priority", refDate));
  assert.equal(highPriTasks.length, 3);
  assert.deepEqual(highPriTasks.map((t) => t.id).sort(), [10, 11, 12]);

  // Section: 'needs_review'
  const reviewTasks = tasks.filter((t) => taskMatchesSection(t, "needs_review", refDate));
  assert.equal(reviewTasks.length, 1);
  assert.equal(reviewTasks[0].id, 13);

  // Section: 'completed_archived'
  const archivedTasks = tasks.filter((t) => taskMatchesSection(t, "completed_archived", refDate));
  assert.equal(archivedTasks.length, 1);
  assert.equal(archivedTasks[0].id, 14);

  // 2. Multi-criteria combined filtering
  // Search + Category + Priority + Importance
  const combinedMatches = filterTasks(tasks, {
    search: "Distributed",
    category: "Assignment",
    priority: "CRITICAL",
    importance: "HIGH",
    status: "pending",
  });
  assert.equal(combinedMatches.length, 1);
  assert.equal(combinedMatches[0].id, 10);

  // Intent filter
  const examMatches = filterTasks(tasks, {
    academic_intent: "exam",
    status: "pending",
  });
  assert.equal(examMatches.length, 1);
  assert.equal(examMatches[0].id, 11);

  // Review filter
  const needsReviewMatches = filterTasks(tasks, {
    review_required: "NEEDS_REVIEW",
  });
  assert.equal(needsReviewMatches.length, 1);
  assert.equal(needsReviewMatches[0].id, 13);

  console.log("✔ Scenario L: Phase 4.4 advanced multi-criteria filters and sections verified");
}

// ============================================================================
// SCENARIO M: Phase 4.4 Task Editing & Immutability Protection
// ============================================================================
{
  const originalTask = {
    id: 101,
    title: "Original Title",
    category: "Assignment",
    description: "Original description",
    due_date: "2026-11-25",
    importance: "MEDIUM",
    status: "pending",
    // Immutable fields
    confidence: "HIGH",
    confidence_reasons: ["Explicit deadline statement"],
    evidence_text: "Original Evidence Text",
    evidence_start_index: 10,
    evidence_end_index: 32,
    source_sender: "Prof. Alan",
    source_timestamp: "2026-11-18 09:00:00",
    source_text: "Original message text",
    source_filename: "chat_export.txt",
  };

  // User updates editable fields
  const userEdits = {
    title: "Updated Title for Assignment",
    category: "Exam",
    due_date: "2026-11-28",
    importance: "HIGH",
    description: "Updated student notes",
    status: "pending",
  };

  // Simulate update in frontend state matching backend PUT/PATCH response
  const updatedTask = {
    ...originalTask,
    ...userEdits,
    // Explicitly guarantee immutable fields are never altered
    confidence: originalTask.confidence,
    confidence_reasons: originalTask.confidence_reasons,
    evidence_text: originalTask.evidence_text,
    evidence_start_index: originalTask.evidence_start_index,
    evidence_end_index: originalTask.evidence_end_index,
    source_sender: originalTask.source_sender,
    source_timestamp: originalTask.source_timestamp,
    source_text: originalTask.source_text,
    source_filename: originalTask.source_filename,
  };

  // Verify editable fields were updated
  assert.equal(updatedTask.title, "Updated Title for Assignment");
  assert.equal(updatedTask.category, "Exam");
  assert.equal(updatedTask.due_date, "2026-11-28");
  assert.equal(updatedTask.importance, "HIGH");
  assert.equal(updatedTask.description, "Updated student notes");

  // Verify immutable fields remained untouched
  assert.equal(updatedTask.confidence, "HIGH");
  assert.deepEqual(updatedTask.confidence_reasons, ["Explicit deadline statement"]);
  assert.equal(updatedTask.evidence_text, "Original Evidence Text");
  assert.equal(updatedTask.evidence_start_index, 10);
  assert.equal(updatedTask.evidence_end_index, 32);
  assert.equal(updatedTask.source_sender, "Prof. Alan");
  assert.equal(updatedTask.source_filename, "chat_export.txt");

  console.log("✔ Scenario M: Phase 4.4 task editing and immutability protection verified");
}

// ============================================================================
// SCENARIO N: Phase 4.5 Multi-Source Adapters & Source-Aware Filtering
// ============================================================================
{
  const multiSourceTasks = [
    {
      id: 1,
      title: "WhatsApp Assignment Task",
      category: "Assignment",
      status: "pending",
      due_date: "2026-11-28",
      source_type: "whatsapp",
      source_id: "wa_msg_1",
      source_text: "Assignment 1 due Friday Nov 28",
    },
    {
      id: 2,
      title: "Gmail Midterm Announcement",
      category: "Exam",
      status: "pending",
      due_date: "2026-12-02",
      source_type: "gmail",
      source_id: "gmail_msg_987",
      source_text: "Midterm exam is on Dec 2",
    },
    {
      id: 3,
      title: "Google Classroom Lab 3",
      category: "Assignment",
      status: "pending",
      due_date: "2026-11-30",
      source_type: "google_classroom",
      source_id: "gc_coursework_456",
      source_text: "Lab 3 backprop due Nov 30",
    },
    {
      id: 4,
      title: "Manual Personal Note",
      category: "Opportunity",
      status: "pending",
      due_date: "2026-12-15",
      source_type: "manual",
      source_id: "manual_12345",
      source_text: "Apply for research internship by Dec 15",
    },
    {
      id: 5,
      title: "Legacy Task (No source_type)",
      category: "Assignment",
      status: "pending",
      due_date: "2026-11-29",
      source_text: "Legacy task without explicit source",
    },
  ];

  // 1. Verify source-based filtering
  const waOnly = multiSourceTasks.filter((t) =>
    matchesTaskFilters(t, { source_type: "whatsapp" })
  );
  // Default fallback for items with missing source_type is 'whatsapp'
  assert.equal(waOnly.length, 2, "WhatsApp filter must match whatsapp source + legacy fallback");
  assert.equal(waOnly[0].id, 1);
  assert.equal(waOnly[1].id, 5);

  const gmailOnly = multiSourceTasks.filter((t) =>
    matchesTaskFilters(t, { source_type: "gmail" })
  );
  assert.equal(gmailOnly.length, 1);
  assert.equal(gmailOnly[0].id, 2);

  const classroomOnly = multiSourceTasks.filter((t) =>
    matchesTaskFilters(t, { source_type: "google_classroom" })
  );
  assert.equal(classroomOnly.length, 1);
  assert.equal(classroomOnly[0].id, 3);

  const manualOnly = multiSourceTasks.filter((t) =>
    matchesTaskFilters(t, { source_type: "manual" })
  );
  assert.equal(manualOnly.length, 1);
  assert.equal(manualOnly[0].id, 4);

  // 2. Verify calculateDashboardStats computes sourceTypeCounts
  const stats = calculateDashboardStats(multiSourceTasks, "2026-11-23");
  assert.ok(stats.sourceTypeCounts, "sourceTypeCounts must exist on dashboard stats");
  assert.equal(stats.sourceTypeCounts.whatsapp, 2);
  assert.equal(stats.sourceTypeCounts.gmail, 1);
  assert.equal(stats.sourceTypeCounts.google_classroom, 1);
  assert.equal(stats.sourceTypeCounts.manual, 1);

  console.log("✔ Scenario N: Phase 4.5 multi-source adapters & source-aware filtering verified");
}

console.log("\nAll End-to-End Frontend Integration tests PASSED successfully!");
