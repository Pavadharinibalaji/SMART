/**
 * Unit and integration tests for ReviewIndicator logic and contracts.
 * Covers all 16 test cases specified in SMART 2.0 Phase 3.2.3 Section 9.
 */

import assert from "node:assert/strict";
import { getReviewStatus } from "../utils/reviewDecisions.js";

console.log("Starting ReviewIndicator test suite...");

// Case 1: review_required = true
{
  const res = getReviewStatus({ reviewRequired: true });
  assert.equal(res.status, "REQUIRED");
  assert.equal(res.label, "Needs Human Review");
  assert.equal(res.isWarning, true);
  console.log("✔ Case 1: review_required = true produces REQUIRED status with warning");
}

// Case 2: review_required = false
{
  const res = getReviewStatus({ reviewRequired: false });
  assert.equal(res.status, "NOT_REQUIRED");
  assert.equal(res.isWarning, false);
  console.log("✔ Case 2: review_required = false produces NOT_REQUIRED status without warning");
}

// Case 3: review_required = null
{
  const res = getReviewStatus({ reviewRequired: null, confidence: "MEDIUM" });
  assert.equal(res.status, "UNAVAILABLE");
  assert.equal(res.isWarning, false);
  assert.equal(res.label, "Review status unavailable");
  console.log("✔ Case 3: review_required = null produces UNAVAILABLE status without inferring false");
}

// Case 4: review_required missing (undefined)
{
  const res = getReviewStatus({ reviewRequired: undefined, confidence: "HIGH" });
  assert.equal(res.status, "UNAVAILABLE");
  assert.equal(res.isWarning, false);
  assert.equal(res.label, "Review status unavailable");
  console.log("✔ Case 4: review_required missing produces UNAVAILABLE status neutrally");
}

// Case 5: LOW confidence + review required
{
  const res = getReviewStatus({
    reviewRequired: true,
    confidence: "LOW",
    reasons: ["Ambiguous date formats present"],
  });
  assert.equal(res.status, "REQUIRED");
  assert.equal(res.isWarning, true);
  assert.equal(res.reasons[0], "Ambiguous date formats present");
  console.log("✔ Case 5: LOW confidence + review required marks item for review");
}

// Case 6: LOW confidence + review not required
{
  const res = getReviewStatus({
    reviewRequired: false,
    confidence: "LOW",
    reasons: ["Low score but explicitly marked clear"],
  });
  assert.equal(res.status, "NOT_REQUIRED");
  assert.equal(res.isWarning, false);
  console.log("✔ Case 6: LOW confidence + review not required strictly obeys backend boolean");
}

// Case 7: MEDIUM confidence + review not required
{
  const res = getReviewStatus({
    reviewRequired: false,
    confidence: "MEDIUM",
  });
  assert.equal(res.status, "NOT_REQUIRED");
  assert.equal(res.isWarning, false);
  console.log("✔ Case 7: MEDIUM confidence + review not required does not falsely mark for review");
}

// Case 8: MEDIUM confidence + review required
{
  const res = getReviewStatus({
    reviewRequired: true,
    confidence: "MEDIUM",
    reasons: ["Mentioned date without explicit deadline keywords"],
  });
  assert.equal(res.status, "REQUIRED");
  assert.equal(res.isWarning, true);
  console.log("✔ Case 8: MEDIUM confidence + review required displays review warning");
}

// Case 9: HIGH confidence + review not required
{
  const res = getReviewStatus({
    reviewRequired: false,
    confidence: "HIGH",
  });
  assert.equal(res.status, "NOT_REQUIRED");
  assert.equal(res.isWarning, false);
  console.log("✔ Case 9: HIGH confidence + review not required shows clear state");
}

// Case 10: HIGH confidence + review required
{
  const res = getReviewStatus({
    reviewRequired: true,
    confidence: "HIGH",
    reasons: ["Secondary category conflict detected"],
  });
  assert.equal(res.status, "REQUIRED");
  assert.equal(res.isWarning, true);
  console.log("✔ Case 10: HIGH confidence + review required respects authoritative review_required flag");
}

// Case 11: UNASSESSED confidence
{
  const resNull = getReviewStatus({
    reviewRequired: null,
    confidence: "UNASSESSED",
  });
  assert.equal(resNull.status, "UNASSESSED");
  assert.equal(resNull.label, "Not assessed");
  assert.equal(resNull.isWarning, false);

  const resUndef = getReviewStatus({
    confidence: "UNASSESSED",
  });
  assert.equal(resUndef.status, "UNASSESSED");
  assert.equal(resUndef.isWarning, false);
  console.log("✔ Case 11: UNASSESSED confidence displays Not assessed without claiming review or certainty");
}

// Case 12: Missing review explanation
{
  const res = getReviewStatus({
    reviewRequired: true,
    confidence: "MEDIUM",
    reasons: [],
  });
  assert.equal(res.status, "REQUIRED");
  assert.equal(res.hasExplanation, false);
  assert.equal(
    res.fallbackText,
    "SMART recommends reviewing this task, but no detailed review explanation is available."
  );
  assert.ok(res.tooltip.includes("SMART recommends reviewing this task"));
  console.log("✔ Case 12: Missing review explanation displays standard SMART fallback message");
}

// Case 13: Review explanation present
{
  const res = getReviewStatus({
    reviewRequired: true,
    confidence: "LOW",
    reasons: [
      "Date mentioned without explicit deadline phrasing (e.g. 'due', 'submit by').",
      "Multiple categories matched (Assignment, Exam); classified as 'Assignment'.",
    ],
  });
  assert.equal(res.status, "REQUIRED");
  assert.equal(res.hasExplanation, true);
  assert.equal(res.reasons.length, 2);
  assert.ok(res.tooltip.includes("Multiple categories matched"));
  console.log("✔ Case 13: Review explanation present correctly formats reasons list and tooltip");
}

// Case 14: Candidate card rendering contract
{
  const candidateItem = {
    title: "OS Lab Submission",
    category: "Assignment",
    review_required: true,
    review_reasons: ["Submission date ambiguous"],
    confidence: "LOW",
  };
  const badgeRes = getReviewStatus({
    reviewRequired: candidateItem.review_required,
    confidence: candidateItem.confidence,
    reasons: candidateItem.review_reasons,
  });
  assert.equal(badgeRes.status, "REQUIRED");
  assert.equal(badgeRes.isWarning, true);
  console.log("✔ Case 14: Candidate card review metadata contract correctly parsed");
}

// Case 15: Saved task card rendering contract
{
  const savedTaskItem = {
    id: 42,
    title: "Robotics Workshop",
    category: "Event",
    review_required: false,
    review_reasons: [],
    confidence: "HIGH",
  };
  const taskRes = getReviewStatus({
    reviewRequired: savedTaskItem.review_required,
    confidence: savedTaskItem.confidence,
    reasons: savedTaskItem.review_reasons,
  });
  assert.equal(taskRes.status, "NOT_REQUIRED");
  assert.equal(taskRes.isWarning, false);
  console.log("✔ Case 15: Saved task card review metadata contract correctly parsed");
}

// Case 16: Evidence drawer integration contract
{
  const drawerItemWithReview = {
    title: "Internal Assessment 1",
    category: "Exam",
    review_required: true,
    review_reasons: ["Relative weekday resolved from timestamp"],
    confidence: "MEDIUM",
  };
  const drawerRes = getReviewStatus({
    reviewRequired: drawerItemWithReview.review_required,
    confidence: drawerItemWithReview.confidence,
    reasons: drawerItemWithReview.review_reasons,
  });
  assert.equal(drawerRes.status, "REQUIRED");
  assert.equal(drawerRes.hasExplanation, true);
  assert.equal(drawerRes.reasons[0], "Relative weekday resolved from timestamp");
  console.log("✔ Case 16: Evidence drawer review integration contract correctly parsed");
}

// ============================================================================
// Phase 3.2.3 Final Correction: Independence & Neutral Wording Regression Tests
// ============================================================================

// Regression Test 1: UNASSESSED + review_required false
// Visibly communicates confidence is unassessed without falsely marking task for review.
{
  const res = getReviewStatus({
    confidence: "UNASSESSED",
    reviewRequired: false,
  });
  assert.equal(res.status, "NOT_REQUIRED");
  assert.equal(res.isWarning, false);
  assert.equal(res.isUnassessed, true);
  assert.equal(res.label, "No Review Needed");
  assert.equal(res.tooltip, "No human review is currently required according to SMART's assessment.");
  console.log("✔ Regression 1: UNASSESSED + review_required false communicates unassessed confidence without review warning");
}

// Regression Test 2: UNASSESSED + review_required true
// Unassessed confidence must not suppress authoritative backend review_required flag.
{
  const res = getReviewStatus({
    confidence: "UNASSESSED",
    reviewRequired: true,
    reasons: ["Legacy item flagged for manual review"],
  });
  assert.equal(res.status, "REQUIRED");
  assert.equal(res.isWarning, true);
  assert.equal(res.isUnassessed, true);
  assert.equal(res.label, "Needs Human Review");
  assert.equal(res.reasons[0], "Legacy item flagged for manual review");
  console.log("✔ Regression 2: UNASSESSED + review_required true preserves authoritative review warning");
}

// Regression Test 3: MEDIUM + review_required false
// MEDIUM confidence must not automatically trigger review unless backend metadata requires it.
{
  const res = getReviewStatus({
    confidence: "MEDIUM",
    reviewRequired: false,
  });
  assert.equal(res.status, "NOT_REQUIRED");
  assert.equal(res.isWarning, false);
  assert.equal(res.isUnassessed, false);
  assert.equal(res.tooltip, "No human review is currently required according to SMART's assessment.");
  console.log("✔ Regression 3: MEDIUM + review_required false does not trigger review warning");
}

// Regression Test 4: LOW + review_required false
// LOW confidence must not override an authoritative backend decision of review_required: false.
{
  const res = getReviewStatus({
    confidence: "LOW",
    reviewRequired: false,
  });
  assert.equal(res.status, "NOT_REQUIRED");
  assert.equal(res.isWarning, false);
  assert.equal(res.isUnassessed, false);
  assert.equal(res.tooltip, "No human review is currently required according to SMART's assessment.");
  console.log("✔ Regression 4: LOW + review_required false strictly respects false flag without review warning");
}

// Regression Test 5: HIGH + review_required true
// HIGH confidence must not suppress an authoritative backend decision of review_required: true.
{
  const res = getReviewStatus({
    confidence: "HIGH",
    reviewRequired: true,
    reasons: ["Multi-category ambiguity detected in assignment text"],
  });
  assert.equal(res.status, "REQUIRED");
  assert.equal(res.isWarning, true);
  assert.equal(res.isUnassessed, false);
  assert.equal(res.label, "Needs Human Review");
  assert.equal(res.reasons[0], "Multi-category ambiguity detected in assignment text");
  console.log("✔ Regression 5: HIGH + review_required true respects authoritative review warning despite high confidence");
}

// Regression Test 6: Neutral Wording Validation
// Ensures deprecated phrasing "Extraction criteria met with high certainty" is not used anywhere.
{
  const res = getReviewStatus({ reviewRequired: false });
  assert.equal(res.tooltip, "No human review is currently required according to SMART's assessment.");
  assert.ok(!res.tooltip.includes("Extraction criteria met with high certainty"));
  console.log("✔ Regression 6: Neutral wording correctly applied");
}

console.log("All 16 ReviewIndicator test cases + 6 Final Correction regression tests passed successfully!");
