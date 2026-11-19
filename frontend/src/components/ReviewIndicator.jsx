/**
 * ReviewIndicator component for SMART 2.0.
 *
 * Displays human review indicators based strictly on authoritative backend metadata
 * (`review_required`, `review_reasons`, and `confidence`).
 *
 * Distinguishes:
 * A. Review required:
 *    - Prominent amber warning indicator with label "Needs Human Review"
 *    - Accessible explanation and reasons list
 * B. Review not required:
 *    - Suppresses review warnings completely (no false warnings)
 *    - Optional subtle verified clear state
 * C. Review status unavailable:
 *    - Neutral "Review status unavailable" indicator without inferring certainty
 * D. UNASSESSED:
 *    - Neutral "Not assessed" indicator explaining that algorithmic assessment is unavailable
 *    - Does NOT automatically classify UNASSESSED items as requiring review
 *
 * Supports three variants:
 * - "badge": Compact pill for card header badge rows
 * - "box": Detailed explanation box with reasons or fallback notice
 * - "full": Combined badge and explanation container
 */

import { getReviewStatus } from "../utils/reviewDecisions";

export default function ReviewIndicator({
  reviewRequired,
  confidence,
  reasons,
  showReasons = false,
  showClearStatus = false,
  variant,
  className = "",
}) {
  const review = getReviewStatus({ reviewRequired, confidence, reasons });
  const effectiveVariant = variant || (showReasons ? "box" : "badge");

  // 1. Badge Variant (Pill for card headers and badge rows)
  if (effectiveVariant === "badge") {
    if (review.status === "REQUIRED") {
      return (
        <span
          className={`review-pill review-pill-warning ${className}`.trim()}
          role="status"
          aria-label={review.label}
          title={review.tooltip}
        >
          <span className="review-icon" aria-hidden="true">⚠️</span>
          <span className="review-text">{review.label}</span>
        </span>
      );
    }

    if (review.status === "NOT_REQUIRED") {
      if (!showClearStatus) {
        return null;
      }
      return (
        <span
          className={`review-pill review-pill-clear ${className}`.trim()}
          role="status"
          aria-label={review.label}
          title={review.tooltip}
        >
          <span className="review-icon" aria-hidden="true">✓</span>
          <span className="review-text">{review.label}</span>
        </span>
      );
    }

    if (review.status === "UNASSESSED") {
      return (
        <span
          className={`review-pill review-pill-unassessed ${className}`.trim()}
          role="status"
          aria-label={`Review status: ${review.label}`}
          title={review.tooltip}
        >
          <span className="review-text">{review.label}</span>
        </span>
      );
    }

    if (review.status === "UNAVAILABLE") {
      if (!showClearStatus) {
        return null;
      }
      return (
        <span
          className={`review-pill review-pill-unavailable ${className}`.trim()}
          role="status"
          aria-label={review.label}
          title={review.tooltip}
        >
          <span className="review-text">{review.label}</span>
        </span>
      );
    }

    return null;
  }

  // 2. Box Variant (Explanatory details for card body or drawer)
  if (effectiveVariant === "box") {
    if (review.status === "REQUIRED") {
      return (
        <div
          className={`review-reasons-box ${className}`.trim()}
          role="region"
          aria-label="Human review explanation"
        >
          <div className="review-box-header">
            <span className="review-box-icon" aria-hidden="true">⚠️</span>
            <span className="review-box-title">Why this item requires review:</span>
          </div>
          {review.hasExplanation ? (
            <ul className="review-reasons-list">
              {review.reasons.map((reason, idx) => (
                <li key={idx} className="review-reason-item">
                  {reason}
                </li>
              ))}
            </ul>
          ) : (
            <p className="review-fallback-text">{review.fallbackText}</p>
          )}
        </div>
      );
    }

    if (review.status === "NOT_REQUIRED" && showClearStatus) {
      return (
        <div className={`review-clear-box ${className}`.trim()} role="status">
          <span className="review-box-icon" aria-hidden="true">✓</span>
          <span>No human review is currently required according to SMART's assessment.</span>
        </div>
      );
    }

    if ((review.status === "UNASSESSED" || review.status === "UNAVAILABLE") && showClearStatus) {
      return (
        <div className={`review-unavailable-box ${className}`.trim()} role="status">
          <span className="review-box-icon" aria-hidden="true">ℹ️</span>
          <span>
            {review.status === "UNASSESSED"
              ? "Algorithmic review assessment is unavailable for this task."
              : "Review status metadata is unavailable for this item."}
          </span>
        </div>
      );
    }

    return null;
  }

  // 3. Full Variant (Badge + Box combined)
  if (effectiveVariant === "full") {
    const hasBoxContent =
      review.status === "REQUIRED" ||
      ((review.status === "NOT_REQUIRED" || review.status === "UNASSESSED" || review.status === "UNAVAILABLE") && showClearStatus);

    return (
      <div className={`review-indicator-full ${className}`.trim()}>
        <div className="review-full-badge-row">
          <ReviewIndicator
            reviewRequired={reviewRequired}
            confidence={confidence}
            reasons={reasons}
            showClearStatus={showClearStatus}
            variant="badge"
          />
        </div>
        {hasBoxContent && (
          <ReviewIndicator
            reviewRequired={reviewRequired}
            confidence={confidence}
            reasons={reasons}
            showClearStatus={showClearStatus}
            variant="box"
          />
        )}
      </div>
    );
  }

  return null;
}
