import { useEffect, useRef } from "react";
import ConfidenceBadge from "./ConfidenceBadge";
import ReviewIndicator from "./ReviewIndicator";
import { highlightEvidence } from "../utils/highlightEvidence";

const CATEGORY_COLORS = {
  Assignment: { bg: "#eff6ff", text: "#1d4ed8", border: "#bfdbfe" },
  Exam: { bg: "#fff1f2", text: "#be123c", border: "#fecdd3" },
  Announcement: { bg: "#f1f5f9", text: "#334155", border: "#cbd5e1" },
  Opportunity: { bg: "#fef3c7", text: "#92400e", border: "#fcd34d" },
  Event: { bg: "#ecfdf5", text: "#047857", border: "#a7f3d0" },
};

/**
 * EvidenceDrawer component for SMART 2.0.
 *
 * Provides a slide-over inspection drawer that visually connects an academic task
 * with its underlying WhatsApp source evidence and algorithmic confidence scoring.
 *
 * Supported features:
 * - Exact non-fuzzy evidence highlighting within original message text.
 * - Clear warning for evidence mismatches without guessing or fuzzy matching.
 * - Explicit unavailable states for missing source or missing evidence (no fabrication).
 * - Full confidence reasons display.
 * - Accessible modal dialog with keyboard (Escape) and backdrop click dismissal.
 * - Reusable across both Analyze Chat candidates and saved Tasks dashboard.
 */
export default function EvidenceDrawer({ item, onClose, onMarkReviewed, onTrackOpportunity }) {
  const closeBtnRef = useRef(null);

  // Keyboard accessibility: Dismiss drawer on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Lock body scroll while drawer is open
  useEffect(() => {
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    if (closeBtnRef.current) {
      closeBtnRef.current.focus();
    }
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, []);

  if (!item) {
    return null;
  }

  const meta = typeof item.source_metadata === "string"
    ? (() => { try { return JSON.parse(item.source_metadata); } catch { return {}; } })()
    : (item.source_metadata || {});
  const isGmail = item.source_type === "gmail" || Boolean(meta.gmail_deep_link) || Boolean(meta.threadId);
  const gmailDeepLink = meta.gmail_deep_link || (meta.threadId ? `https://mail.google.com/mail/u/0/#all/${meta.threadId}` : null);
  const extractedUrls = Array.isArray(meta.extracted_urls)
    ? meta.extracted_urls
    : (Array.isArray(item.urls) ? item.urls.map((u) => ({ url: u, label: u, kind: "generic" })) : []);

  const categoryStyle = CATEGORY_COLORS[item.category] || {
    bg: "#f1f5f9",
    text: "#334155",
    border: "#cbd5e1",
  };

  const highlightResult = highlightEvidence(
    item.source_text,
    item.evidence_text,
    item.evidence_start_index,
    item.evidence_end_index
  );
  const reasons = Array.isArray(item.confidence_reasons) ? item.confidence_reasons : [];
  const isUnassessed = (item.confidence || "").toUpperCase() === "UNASSESSED";

  return (
    <div
      className="drawer-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="evidence-drawer-title"
      aria-describedby="evidence-drawer-desc"
      onClick={onClose}
    >
      <div
        className="drawer-panel"
        onClick={(e) => e.stopPropagation()}
        tabIndex={-1}
      >
        {/* Drawer Header */}
        <header className="drawer-header">
          <div className="drawer-header-content">
            <span className="drawer-eyebrow">Evidence Details</span>
            <h2 id="evidence-drawer-title" className="drawer-title">
              {item.title || "Untitled Academic Task"}
            </h2>
            <div className="drawer-meta-badges">
              {item.category && (
                <span
                  className="category-pill"
                  style={{
                    backgroundColor: categoryStyle.bg,
                    color: categoryStyle.text,
                    borderColor: categoryStyle.border,
                  }}
                >
                  {item.category}
                </span>
              )}
              <ReviewIndicator
                reviewRequired={item.review_required}
                confidence={item.confidence}
                reasons={item.review_reasons && item.review_reasons.length > 0 ? item.review_reasons : item.confidence_reasons}
              />
              {item.id && (
                <span className="method-pill">Task #{item.id}</span>
              )}
            </div>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            className="drawer-close-btn"
            onClick={onClose}
            aria-label="Close evidence drawer"
            title="Close (Esc)"
          >
            ✕
          </button>
        </header>

        {/* Drawer Scrollable Body */}
        <div className="drawer-body" id="evidence-drawer-desc">
          {/* Section 1: Extraction Confidence */}
          <section className="drawer-section" aria-labelledby="section-confidence">
            <div className="drawer-section-header">
              <h3 id="section-confidence" className="drawer-section-title">
                Extraction Confidence
              </h3>
            </div>
            <div className="drawer-confidence-row">
              <ConfidenceBadge
                confidence={item.confidence}
                reasons={item.confidence_reasons}
              />
              <span className="drawer-confidence-hint">
                {isUnassessed
                  ? "Manual task or legacy record without automated confidence assessment."
                  : "Deterministic algorithmic score computed by SMART's rule-based parser."}
              </span>
            </div>
          </section>

          {/* Section 2: Confidence Reasons */}
          <section className="drawer-section" aria-labelledby="section-reasons">
            <div className="drawer-section-header">
              <h3 id="section-reasons" className="drawer-section-title">
                Why SMART Identified This Task
              </h3>
            </div>
            {reasons.length > 0 ? (
              <ul className="evidence-reasons-list">
                {reasons.map((reason, idx) => (
                  <li key={idx} className="evidence-reason-item">
                    {reason}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="drawer-empty-text">
                {isUnassessed
                  ? "Algorithmic confidence assessment is unavailable for this task."
                  : "No confidence explanation is available for this task."}
              </p>
            )}
          </section>

          {/* Section 3: Human Review Status */}
          <section className="drawer-section" aria-labelledby="section-review">
            <div className="drawer-section-header">
              <h3 id="section-review" className="drawer-section-title">
                Human Review Status
              </h3>
            </div>
            <ReviewIndicator
              reviewRequired={item.review_required}
              confidence={item.confidence}
              reasons={item.review_reasons && item.review_reasons.length > 0 ? item.review_reasons : item.confidence_reasons}
              variant="box"
              showClearStatus
            />
          </section>

          {/* Section 4: Supporting Evidence */}
          <section className="drawer-section" aria-labelledby="section-evidence">
            <div className="drawer-section-header">
              <h3 id="section-evidence" className="drawer-section-title">
                Supporting Evidence
              </h3>
            </div>
            {highlightResult.hasEvidence ? (
              <div className="evidence-snippet-box">
                <span className="evidence-snippet-label">
                  Exact text segment identified as task evidence:
                </span>
                <blockquote className="evidence-snippet-text">
                  {item.evidence_text}
                </blockquote>
              </div>
            ) : (
              <div className="drawer-empty-callout">
                <span className="drawer-empty-icon" aria-hidden="true">ℹ️</span>
                <div>
                  <strong>Evidence is not available for this task.</strong>
                  <p className="drawer-empty-subtext">
                    {isUnassessed
                      ? "Manually created or legacy tasks do not contain machine-extracted evidence."
                      : "No specific supporting text segment was recorded for this task."}
                  </p>
                </div>
              </div>
            )}
          </section>

          {/* Section 5: Original Source Message */}
          <section className="drawer-section" aria-labelledby="section-source">
            <div className="drawer-section-header">
              <h3 id="section-source" className="drawer-section-title">
                Original Source Message
              </h3>
            </div>

            {/* Source message metadata bar */}
            {(item.source_sender || item.source_timestamp || item.source_message_id || item.source_filename) && (
              <div className="drawer-source-meta">
                {item.source_sender && (
                  <span><strong>Sender:</strong> {item.source_sender}</span>
                )}
                {item.source_timestamp && (
                  <span><strong>Timestamp:</strong> {item.source_timestamp}</span>
                )}
                {item.source_message_id && (
                  <span><strong>Message #{item.source_message_id}</strong></span>
                )}
                {item.source_filename && (
                  <span><strong>File:</strong> {item.source_filename}</span>
                )}
              </div>
            )}

            {/* Mismatch Warning Alert */}
            {highlightResult.mismatchWarning && (
              <div className="drawer-mismatch-alert" role="alert">
                <span aria-hidden="true">⚠️</span>
                <div>
                  <strong>Evidence could not be matched to the original message.</strong>
                  <p className="drawer-empty-subtext">
                    The evidence segment above does not appear as an exact substring in the message below.
                  </p>
                </div>
              </div>
            )}

            {/* Source text content */}
            {highlightResult.hasSource ? (
              <div className="drawer-source-container">
                <pre className="drawer-source-pre">
                  {highlightResult.segments.map((seg, idx) =>
                    seg.isMatch ? (
                      <mark
                        key={idx}
                        className="evidence-highlight"
                        title="Matching verified evidence segment"
                      >
                        {seg.text}
                      </mark>
                    ) : (
                      <span key={idx}>{seg.text}</span>
                    )
                  )}
                </pre>
              </div>
            ) : (
              <div className="drawer-empty-callout">
                <span className="drawer-empty-icon" aria-hidden="true">ℹ️</span>
                <div>
                  <strong>Original source message is unavailable.</strong>
                  <p className="drawer-empty-subtext">
                    No original communication message was attached to this task.
                  </p>
                </div>
              </div>
            )}
          </section>

          {/* Section 6: Gmail Source Integration */}
          {(isGmail || Boolean(gmailDeepLink)) && (
            <section className="drawer-section" aria-labelledby="section-gmail-source">
              <div className="drawer-section-header">
                <h3 id="section-gmail-source" className="drawer-section-title">
                  Gmail Source Integration
                </h3>
              </div>
              <div className="gmail-evidence-box">
                <div className="gmail-evidence-info">
                  <span className="gmail-evidence-tag">✉️ Live Google Email</span>
                  {meta.threadId && (
                    <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                      <strong>Thread ID:</strong> <code>{meta.threadId}</code>
                    </span>
                  )}
                  {item.source_id && (
                    <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                      <strong>Message ID:</strong> <code>{item.source_id}</code>
                    </span>
                  )}
                </div>
                {gmailDeepLink && (
                  <a
                    href={gmailDeepLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-gmail-pill"
                    style={{ fontSize: "13px", padding: "8px 14px" }}
                  >
                    <span>✉️</span> View Original Email ↗
                  </a>
                )}
              </div>
            </section>
          )}

          {/* Section 7: Shared Links & Resources */}
          {extractedUrls.length > 0 && (
            <section className="drawer-section" aria-labelledby="section-extracted-urls">
              <div className="drawer-section-header">
                <h3 id="section-extracted-urls" className="drawer-section-title">
                  Shared Links &amp; Resources ({extractedUrls.length})
                </h3>
              </div>
              <div className="extracted-urls-grid">
                {extractedUrls.map((u, idx) => (
                  <a
                    key={idx}
                    href={u.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="extracted-url-chip"
                    title={u.url}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
                      <span className={`url-kind-badge kind-${u.kind || "generic"}`}>
                        {u.kind === "google_form"
                          ? "📝 Google Form"
                          : u.kind === "classroom"
                          ? "🏫 Google Classroom"
                          : u.kind === "drive"
                          ? "📁 Google Drive"
                          : u.kind === "registration"
                          ? "📋 Registration"
                          : u.kind === "competition"
                          ? "🏆 Competition"
                          : u.kind === "meeting"
                          ? "📹 Video Meet"
                          : "🔗 Resource"}
                      </span>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {u.label || u.url}
                      </span>
                    </div>
                    <span style={{ marginLeft: "12px", color: "var(--primary)", fontWeight: 700 }}>↗</span>
                  </a>
                ))}
              </div>
            </section>
          )}
        </div>

        {/* Drawer Footer */}
        <footer className="drawer-footer">
          {onTrackOpportunity && (
            <button
              type="button"
              className="btn btn-secondary"
              style={{ color: "#4f46e5", borderColor: "#c7d2fe", background: "#ede9fe", fontWeight: 600 }}
              onClick={() => {
                onTrackOpportunity({
                  title: item.title,
                  description: item.description,
                  registration_deadline: item.due_date,
                  category: item.category === "Opportunity" ? "Competition" : "Other",
                  source_platform: item.source_type || "whatsapp",
                  source_reference: item.evidence_text || item.title,
                  registration_url: item.parsed_shared_urls?.[0]?.url || null,
                  isNewTracking: true,
                });
                onClose();
              }}
            >
              🎯 Track Opportunity
            </button>
          )}
          {item.review_required && onMarkReviewed && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={async () => {
                await onMarkReviewed(item.id, "pending");
                onClose();
              }}
            >
              ✓ Approve &amp; Mark Pending
            </button>
          )}
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
          >
            Close
          </button>
        </footer>
      </div>
    </div>
  );
}
