import { useState } from "react";

export default function OpportunityExplorer({
  opportunities = [],
  onUpdateStatus,
  loading = false,
  onSyncGmail,
}) {
  const [filterStatus, setFilterStatus] = useState("ALL");
  const [updatingId, setUpdatingId] = useState(null);

  const STATUS_OPTIONS = [
    { id: "ALL", label: "All Competitions" },
    { id: "interested", label: "Interested" },
    { id: "registration_pending", label: "Registration Pending" },
    { id: "registered", label: "Registered" },
    { id: "attended", label: "Attended" },
    { id: "declined", label: "Declined" },
  ];

  const filteredOpps = opportunities.filter((opp) => {
    if (filterStatus === "ALL") return true;
    return (opp.student_status || "discovered").toLowerCase() === filterStatus.toLowerCase();
  });

  const handleStatusChange = async (oppId, newStatus) => {
    setUpdatingId(oppId);
    try {
      await onUpdateStatus(oppId, newStatus);
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="opportunity-explorer" aria-label="Academic Competitions & Opportunities">
      {/* Header */}
      <div className="saas-page-header">
        <div className="header-text-block">
          <h2 className="saas-page-title">Competitions &amp; Opportunities</h2>
          <p className="saas-page-subtitle">
            Discover hackathons, coding contests, paper calls, and track your participation status.
          </p>
        </div>
        <div className="header-action-block">
          {onSyncGmail && (
            <button
              type="button"
              className="saas-primary-btn"
              onClick={onSyncGmail}
              disabled={loading}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                <polyline points="22,6 12,13 2,6" />
              </svg>
              <span>Sync Gmail Opportunities</span>
            </button>
          )}
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="section-pill-group" role="tablist" aria-label="Opportunity Status Filters">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            className={`section-tab-btn ${filterStatus === opt.id ? "active" : ""}`}
            onClick={() => setFilterStatus(opt.id)}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Opportunities Grid / List */}
      {loading ? (
        <div className="saas-card chart-empty-state">
          <span className="spinner" aria-hidden="true" style={{ fontSize: 28 }} />
          <p>Scanning academic messages for competition opportunities...</p>
        </div>
      ) : filteredOpps.length === 0 ? (
        <div className="saas-card chart-empty-state">
          <div className="empty-state-icon" aria-hidden="true">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="8" r="7" />
              <polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88" />
            </svg>
          </div>
          <h4>No Competitions Found</h4>
          <p>No opportunities match the selected status filter. Click "Sync Gmail Opportunities" to discover active contests.</p>
        </div>
      ) : (
        <div className="opportunity-cards-grid">
          {filteredOpps.map((opp) => {
            const currentStatus = opp.student_status || "discovered";
            const isUpdating = updatingId === opp.id;

            return (
              <article key={opp.id} className="saas-card opp-card">
                <div className="opp-card-top">
                  <div className="badge-group">
                    <span className="category-pill" style={{ backgroundColor: "#FEF3C7", color: "#92400E", borderColor: "#FCD34D" }}>
                      Competition
                    </span>
                    {opp.confidence && (
                      <span className={`confidence-pill confidence-${opp.confidence.toLowerCase()}`}>
                        {opp.confidence} Confidence
                      </span>
                    )}
                    {opp.is_demo === 1 && (
                      <span className="demo-data-badge" title="Demo sample data for offline demonstration">
                        Demo Sample
                      </span>
                    )}
                  </div>
                  <span className={`status-badge-opp status-opp-${currentStatus}`}>
                    {currentStatus.replace(/_/g, " ").toUpperCase()}
                  </span>
                </div>

                <h3 className="opp-card-title">{opp.name}</h3>
                {opp.organizer && (
                  <p className="opp-card-organizer">
                    Hosted by <strong>{opp.organizer}</strong>
                  </p>
                )}

                <p className="opp-card-desc">{opp.description}</p>

                {opp.eligibility && (
                  <div className="opp-detail-row">
                    <span className="opp-detail-label">Eligibility:</span>
                    <span className="opp-detail-val">{opp.eligibility}</span>
                  </div>
                )}

                <div className="opp-dates-row">
                  {opp.registration_deadline && (
                    <div className="opp-date-box">
                      <span className="date-box-lbl">Registration Deadline</span>
                      <strong className="date-box-val text-danger">{opp.registration_deadline}</strong>
                    </div>
                  )}
                  {opp.event_date && (
                    <div className="opp-date-box">
                      <span className="date-box-lbl">Event Date</span>
                      <strong className="date-box-val">{opp.event_date}</strong>
                    </div>
                  )}
                </div>

                {/* Evidence snippet */}
                {opp.evidence_text && (
                  <div className="opp-evidence-snippet">
                    <span className="evidence-lbl">Source Snippet:</span>
                    <em>"{opp.evidence_text}"</em>
                  </div>
                )}

                {/* Actions & Status Control */}
                <div className="opp-card-footer">
                  <div className="opp-status-control">
                    <label htmlFor={`opp-status-${opp.id}`} className="visually-hidden">
                      Update status for {opp.name}
                    </label>
                    <select
                      id={`opp-status-${opp.id}`}
                      className="opp-status-select"
                      value={currentStatus}
                      onChange={(e) => handleStatusChange(opp.id, e.target.value)}
                      disabled={isUpdating}
                    >
                      <option value="discovered">Discovered</option>
                      <option value="interested">Interested</option>
                      <option value="registration_pending">Registration Pending</option>
                      <option value="registered">Registered</option>
                      <option value="declined">Declined</option>
                      <option value="attended">Attended</option>
                      <option value="not_attended">Not Attended</option>
                      <option value="expired">Expired</option>
                    </select>
                  </div>

                  {opp.registration_url && (
                    <a
                      href={opp.registration_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="saas-primary-btn opp-register-link"
                    >
                      <span>Register Now</span>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                        <polyline points="15 3 21 3 21 9" />
                        <line x1="10" y1="14" x2="21" y2="3" />
                      </svg>
                    </a>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
