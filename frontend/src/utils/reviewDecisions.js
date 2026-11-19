/**
 * Human Review Decision Engine for SMART 2.0.
 *
 * Resolves review decision status, labels, and explanations strictly adhering
 * to authoritative backend metadata without inventing review decisions.
 *
 * Decision rules:
 * 1. review_required === true:
 *    - status: "REQUIRED"
 *    - label: "Needs Human Review"
 *    - isWarning: true
 *    - explanation: provided reasons OR fallback:
 *      "SMART recommends reviewing this task, but no detailed review explanation is available."
 *
 * 2. review_required === false:
 *    - status: "NOT_REQUIRED"
 *    - label: "No Review Needed"
 *    - isWarning: false
 *    - explanation: null
 *
 * 3. review_required === null || review_required === undefined:
 *    - If confidence is "UNASSESSED":
 *      - status: "UNASSESSED"
 *      - label: "Not assessed"
 *      - isWarning: false
 *      - explanation: "Algorithmic review assessment is unavailable for this task."
 *    - Else:
 *      - status: "UNAVAILABLE"
 *      - label: "Review status unavailable"
 *      - isWarning: false
 *      - explanation: "Review status metadata is missing or unavailable for this item."
 *
 * 4. Never derive review_required solely from confidence (LOW, MEDIUM, HIGH, UNASSESSED).
 */

export function getReviewStatus({ reviewRequired, confidence, reasons }) {
  const normConfidence = typeof confidence === "string" ? confidence.trim().toUpperCase() : "";
  const isUnassessed = normConfidence === "UNASSESSED";

  // Rule 1: Authoritative review_required === true
  if (reviewRequired === true) {
    const rawReasons = Array.isArray(reasons)
      ? reasons.filter((r) => typeof r === "string" && r.trim().length > 0)
      : [];
    const hasReasons = rawReasons.length > 0;
    const fallbackText = "SMART recommends reviewing this task, but no detailed review explanation is available.";
    const explanationText = hasReasons ? rawReasons.join(" • ") : fallbackText;

    return {
      status: "REQUIRED",
      label: "Needs Human Review",
      isWarning: true,
      isUnassessed,
      confidence: normConfidence || (isUnassessed ? "UNASSESSED" : "UNAVAILABLE"),
      hasExplanation: hasReasons,
      reasons: rawReasons,
      fallbackText,
      tooltip: `Needs Human Review: ${explanationText}`,
    };
  }

  // Rule 2: Authoritative review_required === false
  if (reviewRequired === false) {
    return {
      status: "NOT_REQUIRED",
      label: "No Review Needed",
      isWarning: false,
      isUnassessed,
      confidence: normConfidence || (isUnassessed ? "UNASSESSED" : "UNAVAILABLE"),
      hasExplanation: false,
      reasons: [],
      fallbackText: null,
      tooltip: "No human review is currently required according to SMART's assessment.",
    };
  }

  // Rule 3 & 7: review_required is missing, null, or undefined
  if (isUnassessed) {
    return {
      status: "UNASSESSED",
      label: "Not assessed",
      isWarning: false,
      hasExplanation: false,
      reasons: [],
      fallbackText: null,
      tooltip: "Algorithmic confidence and review assessment are unavailable for this task.",
    };
  }

  return {
    status: "UNAVAILABLE",
    label: "Review status unavailable",
    isWarning: false,
    hasExplanation: false,
    reasons: [],
    fallbackText: null,
    tooltip: "Review status metadata is unavailable for this item.",
  };
}
