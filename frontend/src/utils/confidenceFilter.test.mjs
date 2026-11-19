/**
 * Unit and integration tests for confidence filtering utility.
 * Covers all 15 scenarios specified in SMART 2.0 Phase 3.2.4 Section 4.
 */

import assert from "node:assert/strict";
import {
  normalizeConfidence,
  matchesConfidence,
  filterByConfidence,
  matchesTaskFilters,
  filterTasks,
} from "./confidenceFilter.js";

console.log("Starting confidenceFilter test suite...");

const sampleItems = [
  { id: 1, title: "Assignment 1", category: "Assignment", status: "pending", confidence: "HIGH", due_date: "2026-11-25", source_text: "Submit report" },
  { id: 2, title: "Exam 1", category: "Exam", status: "pending", confidence: "MEDIUM", due_date: "2026-11-28", source_text: "Semester exam" },
  { id: 3, title: "Workshop Notice", category: "Announcement", status: "completed", confidence: "LOW", due_date: "2026-11-30", source_text: "Robotics workshop notice" },
  { id: 4, title: "Manual Task Null Conf", category: "Assignment", status: "pending", confidence: null, due_date: "2026-12-01", source_text: "Manually entered task" },
  { id: 5, title: "Legacy Task Undef Conf", category: "Event", status: "dismissed", confidence: undefined, due_date: "2026-12-05", source_text: "Legacy event" },
  { id: 6, title: "Empty Conf Item", category: "Opportunity", status: "completed", confidence: "", due_date: "2026-12-10", source_text: "Internship" },
  { id: 7, title: "Invalid Conf Value", category: "Exam", status: "pending", confidence: "UNKNOWN_TIER", due_date: "2026-12-15", source_text: "Internal quiz" },
  { id: 8, title: "Explicit Unassessed", category: "Assignment", status: "pending", confidence: "UNASSESSED", due_date: "2026-12-20", source_text: "Manual entry" },
];

// Test 1: All displays every candidate/task
{
  const result = filterByConfidence(sampleItems, "ALL");
  assert.equal(result.length, sampleItems.length);
  console.log("✔ Test 1: 'ALL' confidence filter displays every item");
}

// Test 2: HIGH displays only HIGH confidence items
{
  const result = filterByConfidence(sampleItems, "HIGH");
  assert.equal(result.length, 1);
  assert.equal(result[0].id, 1);
  assert.equal(result[0].confidence, "HIGH");
  console.log("✔ Test 2: 'HIGH' confidence filter displays only HIGH confidence items");
}

// Test 3: MEDIUM displays only MEDIUM confidence items
{
  const result = filterByConfidence(sampleItems, "MEDIUM");
  assert.equal(result.length, 1);
  assert.equal(result[0].id, 2);
  assert.equal(result[0].confidence, "MEDIUM");
  console.log("✔ Test 3: 'MEDIUM' confidence filter displays only MEDIUM confidence items");
}

// Test 4: LOW displays only LOW confidence items
{
  const result = filterByConfidence(sampleItems, "LOW");
  assert.equal(result.length, 1);
  assert.equal(result[0].id, 3);
  assert.equal(result[0].confidence, "LOW");
  console.log("✔ Test 4: 'LOW' confidence filter displays only LOW confidence items");
}

// Test 5: UNASSESSED includes null confidence
{
  assert.equal(normalizeConfidence(null), "UNASSESSED");
  assert.equal(matchesConfidence({ confidence: null }, "UNASSESSED"), true);
  console.log("✔ Test 5: 'UNASSESSED' filter includes null confidence records");
}

// Test 6: UNASSESSED includes undefined confidence
{
  assert.equal(normalizeConfidence(undefined), "UNASSESSED");
  assert.equal(matchesConfidence({ confidence: undefined }, "UNASSESSED"), true);
  console.log("✔ Test 6: 'UNASSESSED' filter includes undefined confidence records");
}

// Test 7: UNASSESSED includes empty confidence
{
  assert.equal(normalizeConfidence(""), "UNASSESSED");
  assert.equal(normalizeConfidence("   "), "UNASSESSED");
  assert.equal(matchesConfidence({ confidence: "" }, "UNASSESSED"), true);
  console.log("✔ Test 7: 'UNASSESSED' filter includes empty string confidence records");
}

// Test 8: Unsupported confidence values follow fallback behavior (resolve to UNASSESSED)
{
  assert.equal(normalizeConfidence("UNKNOWN_LEVEL"), "UNASSESSED");
  assert.equal(normalizeConfidence("bogus"), "UNASSESSED");
  assert.equal(normalizeConfidence(123), "UNASSESSED");
  assert.equal(matchesConfidence({ confidence: "UNSUPPORTED" }, "UNASSESSED"), true);
  assert.equal(matchesConfidence({ confidence: "UNSUPPORTED" }, "HIGH"), false);

  const unassessedItems = filterByConfidence(sampleItems, "UNASSESSED");
  // Expect items 4 (null), 5 (undefined), 6 (""), 7 ("UNKNOWN_TIER"), 8 ("UNASSESSED")
  assert.equal(unassessedItems.length, 5);
  console.log("✔ Test 8: Unsupported confidence values safely fall back to UNASSESSED");
}

// Test 9: Filtering does not mutate the original array or objects
{
  const originalSnapshot = JSON.stringify(sampleItems);
  const filtered = filterByConfidence(sampleItems, "HIGH");
  assert.notEqual(filtered, sampleItems);
  assert.equal(JSON.stringify(sampleItems), originalSnapshot);
  console.log("✔ Test 9: Filtering is strictly pure and non-mutating");
}

// Test 10: Confidence filtering works with search
{
  const result = filterTasks(sampleItems, {
    confidence: "MEDIUM",
    search: "semester exam",
  });
  assert.equal(result.length, 1);
  assert.equal(result[0].id, 2);

  const noMatch = filterTasks(sampleItems, {
    confidence: "HIGH",
    search: "semester exam",
  });
  assert.equal(noMatch.length, 0);
  console.log("✔ Test 10: Confidence filtering combines properly with search queries");
}

// Test 11: Confidence filtering works with category filtering
{
  const result = filterTasks(sampleItems, {
    confidence: "UNASSESSED",
    category: "Assignment",
  });
  // Items 4 (null) and 8 ("UNASSESSED") are Assignments
  assert.equal(result.length, 2);
  assert.ok(result.every((it) => it.category === "Assignment"));
  console.log("✔ Test 11: Confidence filtering combines properly with category filters");
}

// Test 12: Confidence filtering works with status filtering
{
  const result = filterTasks(sampleItems, {
    confidence: "LOW",
    status: "completed",
  });
  assert.equal(result.length, 1);
  assert.equal(result[0].id, 3);
  assert.equal(result[0].status, "completed");

  const noMatch = filterTasks(sampleItems, {
    confidence: "LOW",
    status: "pending",
  });
  assert.equal(noMatch.length, 0);
  console.log("✔ Test 12: Confidence filtering combines properly with task status filters");
}

// Test 13: Confidence filtering works with date filtering
{
  const result = filterTasks(sampleItems, {
    confidence: "HIGH",
    due_before: "2026-11-26",
  });
  assert.equal(result.length, 1);
  assert.equal(result[0].id, 1);

  const resultAfter = filterTasks(sampleItems, {
    confidence: "HIGH",
    due_after: "2026-11-26",
  });
  assert.equal(resultAfter.length, 0);
  console.log("✔ Test 13: Confidence filtering combines properly with date range filters");
}

// Test 14: Clearing the confidence filter restores all matching items
{
  // Filtered by HIGH + category: Assignment
  const filteredHigh = filterTasks(sampleItems, {
    category: "Assignment",
    confidence: "HIGH",
  });
  assert.equal(filteredHigh.length, 1);

  // Clearing confidence filter to "ALL"
  const clearedConfidence = filterTasks(sampleItems, {
    category: "Assignment",
    confidence: "ALL",
  });
  // Should restore all Assignments (id 1, 4, 8)
  assert.equal(clearedConfidence.length, 3);
  console.log("✔ Test 14: Clearing confidence filter restores all items matching remaining filters");
}

// Test 15: Candidate and saved-task filtering behave consistently
{
  const candidateList = [
    { title: "Lab 1", category: "Assignment", confidence: "HIGH" },
    { title: "Lab 2", category: "Assignment", confidence: "UNASSESSED" },
    { title: "Lab 3", category: "Assignment", confidence: null },
  ];
  const savedList = [
    { title: "Lab 1", category: "Assignment", confidence: "HIGH" },
    { title: "Lab 2", category: "Assignment", confidence: "UNASSESSED" },
    { title: "Lab 3", category: "Assignment", confidence: null },
  ];

  const filteredCandidates = filterByConfidence(candidateList, "UNASSESSED");
  const filteredSaved = filterByConfidence(savedList, "UNASSESSED");

  assert.equal(filteredCandidates.length, 2);
  assert.equal(filteredSaved.length, 2);
  assert.deepEqual(
    filteredCandidates.map((c) => c.title),
    filteredSaved.map((s) => s.title)
  );
  console.log("✔ Test 15: Candidate and saved-task filtering behave consistently across all confidence values");
}

console.log("All 15 confidenceFilter tests passed successfully!");
