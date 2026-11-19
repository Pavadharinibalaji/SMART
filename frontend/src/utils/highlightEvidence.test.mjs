import assert from "node:assert";
import { highlightEvidence } from "./highlightEvidence.js";

console.log("Running highlightEvidence unit tests across all 12 scenarios...\n");

// 1. Exact evidence at the beginning of a message
{
  const source = "Submit assignment 1 on 10/11/2026. Please ensure all tests pass.";
  const evidence = "Submit assignment 1 on 10/11/2026";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, evidence);
  assert.strictEqual(res.segments[0].isMatch, true);
  assert.strictEqual(res.segments[1].text, ". Please ensure all tests pass.");
  assert.strictEqual(res.segments[1].isMatch, false);
  console.log("[PASS] 1. Exact evidence at beginning of message");
}

// 2. Exact evidence in the middle of a message
{
  const source = "Dear students, submit your lab exercise report for the robotics workshop on 28/10/2026. Attendance is mandatory.";
  const evidence = "submit your lab exercise report for the robotics workshop on 28/10/2026";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.segments.length, 3);
  assert.strictEqual(res.segments[0].text, "Dear students, ");
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  assert.strictEqual(res.segments[2].text, ". Attendance is mandatory.");
  assert.strictEqual(res.segments[2].isMatch, false);
  console.log("[PASS] 2. Exact evidence in middle of message");
}

// 3. Exact evidence at the end of a message
{
  const source = "Notice: CN exam on 12/11/2026";
  const evidence = "CN exam on 12/11/2026";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments.length, 2);
  assert.strictEqual(res.segments[0].text, "Notice: ");
  assert.strictEqual(res.segments[0].isMatch, false);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 3. Exact evidence at end of message");
}

// 4. Evidence with punctuation
{
  const source = "Reminder: Project (Phase 2) is due; submit before 11:59 PM!";
  const evidence = "Project (Phase 2) is due;";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments[1].text, evidence);
  assert.strictEqual(res.segments[1].isMatch, true);
  console.log("[PASS] 4. Evidence with punctuation preserved exactly");
}

// 5. Evidence containing dates
{
  const source = "Assignment due on Friday, 20 November 2026 by 5 PM.";
  const evidence = "Assignment due on Friday, 20 November 2026";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments[0].text, evidence);
  assert.strictEqual(res.segments[0].isMatch, true);
  assert.strictEqual(res.segments[1].text, " by 5 PM.");
  console.log("[PASS] 5. Evidence containing dates");
}

// 6. Evidence containing multiple words and spaces
{
  const source = "Please   submit   lab   report   before   Friday.";
  const evidence = "submit   lab   report";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments[1].text, "submit   lab   report");
  console.log("[PASS] 6. Evidence containing multiple words and preserved spacing");
}

// 7. Evidence repeated in the source (deterministic policy: first occurrence matched)
{
  const source = "Quiz on Monday. Reminder: Quiz on Monday for all sections.";
  const evidence = "Quiz on Monday";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, true);
  assert.strictEqual(res.segments[0].text, "Quiz on Monday");
  assert.strictEqual(res.segments[0].isMatch, true);
  assert.strictEqual(res.segments[1].text, ". Reminder: Quiz on Monday for all sections.");
  assert.strictEqual(res.segments[1].isMatch, false);
  console.log("[PASS] 7. Evidence repeated in source (first exact occurrence deterministically matched)");
}

// 8. Evidence not found (mismatch warning, no highlight)
{
  const source = "Assignment 1 was discussed yesterday.";
  const evidence = "Assignment 1 is due tomorrow";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.mismatchWarning, true);
  assert.strictEqual(res.segments.length, 1);
  assert.strictEqual(res.segments[0].text, source);
  assert.strictEqual(res.segments[0].isMatch, false);
  console.log("[PASS] 8. Evidence not found (mismatchWarning flagged, original source preserved without highlight)");
}

// 9. Empty evidence
{
  const source = "Some valid announcement text.";
  const evidence = "";
  const res = highlightEvidence(source, evidence);
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.hasEvidence, false);
  assert.strictEqual(res.segments.length, 1);
  assert.strictEqual(res.segments[0].text, source);
  assert.strictEqual(res.segments[0].isMatch, false);
  console.log("[PASS] 9. Empty evidence handled gracefully");
}

// 10. NULL evidence
{
  const source = "Manual task without evidence.";
  const res = highlightEvidence(source, null);
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.mismatchWarning, false);
  assert.strictEqual(res.hasEvidence, false);
  assert.strictEqual(res.segments.length, 1);
  assert.strictEqual(res.segments[0].text, source);
  assert.strictEqual(res.segments[0].isMatch, false);
  console.log("[PASS] 10. NULL evidence handled gracefully");
}

// 11. Empty source
{
  const res = highlightEvidence("", "some evidence");
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.hasSource, false);
  assert.strictEqual(res.segments.length, 0);
  console.log("[PASS] 11. Empty source handled gracefully");
}

// 12. NULL source
{
  const res = highlightEvidence(null, "some evidence");
  assert.strictEqual(res.matched, false);
  assert.strictEqual(res.hasSource, false);
  assert.strictEqual(res.segments.length, 0);
  console.log("[PASS] 12. NULL source handled gracefully");
}

console.log("\nAll 12 highlightEvidence test scenarios PASSED successfully!");
