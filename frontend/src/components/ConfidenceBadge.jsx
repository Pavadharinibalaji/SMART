/**
 * ConfidenceBadge component for SMART 2.0.
 *
 * Displays an accessible, color-coded badge indicating the algorithmic
 * extraction confidence level of an academic task:
 * - HIGH: Green indicator
 * - MEDIUM: Amber indicator
 * - LOW: Red indicator
 * - UNASSESSED: Neutral grey indicator (for manual tasks and legacy pre-Phase 3 records)
 *
 * Missing, null, undefined, or unexpected values always resolve safely to UNASSESSED,
 * ensuring the system never overstates confidence.
 */

const CONFIDENCE_CONFIG = {
  HIGH: {
    label: "High Confidence",
    variant: "high",
    ariaDescription: "High extraction confidence: unambiguous academic category with validated explicit calendar date.",
  },
  MEDIUM: {
    label: "Medium Confidence",
    variant: "medium",
    ariaDescription: "Medium extraction confidence: relative date or clear task without explicit date.",
  },
  LOW: {
    label: "Low Confidence",
    variant: "low",
    ariaDescription: "Low extraction confidence: ambiguous dates or category conflicts requiring human review.",
  },
  UNASSESSED: {
    label: "Unassessed",
    variant: "unassessed",
    ariaDescription: "Unassessed confidence: manually created task or legacy record without an automated score.",
  },
};

export default function ConfidenceBadge({ confidence, reasons, className = "" }) {
  // Graceful normalization: safely handle null, undefined, empty, or unexpected values.
  // Never interpret missing confidence as MEDIUM or HIGH.
  const rawKey = typeof confidence === "string" ? confidence.trim().toUpperCase() : "";
  const config = CONFIDENCE_CONFIG[rawKey] || CONFIDENCE_CONFIG.UNASSESSED;

  // Build helpful tooltip from extraction reasons if available
  const reasonsText = Array.isArray(reasons) && reasons.length > 0 ? reasons.join(" • ") : null;
  const tooltip = reasonsText ? `${config.label}: ${reasonsText}` : config.ariaDescription;

  return (
    <span
      className={`confidence-badge confidence-badge-${config.variant} ${className}`.trim()}
      role="status"
      aria-label={`Extraction confidence: ${config.label}`}
      title={tooltip}
    >
      <span
        className={`confidence-dot confidence-dot-${config.variant}`}
        aria-hidden="true"
      />
      <span className="confidence-text">{config.label}</span>
    </span>
  );
}
