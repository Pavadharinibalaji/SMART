import { useState, useEffect } from "react";
import {
  getStudentTrackedOpportunities,
  updateTrackedOpportunity,
  deleteTrackedOpportunity,
} from "../api";
import OpportunityTrackingModal from "./OpportunityTrackingModal";

const CATEGORIES = [
  "All",
  "Competition",
  "Hackathon",
  "Internship",
  "Workshop",
  "Scholarship",
  "Conference",
  "Other",
];

const TRACKING_STATUSES = [
  "All",
  "Interested",
  "Planning to Apply",
  "Registered",
  "Submitted",
  "Completed",
  "Not Pursuing",
];

export default function OpportunityExplorer({
  opportunities = [],
  onUpdateStatus,
  loading = false,
  onSyncGmail,
  userRole = "student",
}) {
  const isStudent = userRole === "student";

  // Sub-tab: "tracked" (My Tracked) or "discovered" (Discovered / External)
  const [activeTab, setActiveTab] = useState("tracked");

  // Tracked opportunities state
  const [trackedOpps, setTrackedOpps] = useState([]);
  const [trackedLoading, setTrackedLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [selectedStatus, setSelectedStatus] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");

  // Tracking modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [modalInitialData, setModalInitialData] = useState(null);

  // Status updating inline tracker
  const [updatingId, setUpdatingId] = useState(null);

  // Discovered filter
  const [discoveredFilterStatus, setDiscoveredFilterStatus] = useState("ALL");

  const loadTracked = async () => {
    if (!isStudent) return;
    try {
      setTrackedLoading(true);
      const data = await getStudentTrackedOpportunities();
      setTrackedOpps(data || []);
    } catch (err) {
      console.error("Failed to load tracked opportunities:", err);
    } finally {
      setTrackedLoading(false);
    }
  };

  useEffect(() => {
    loadTracked();
  }, [isStudent]);

  // Handle inline status change for tracked opportunity
  const handleTrackedStatusChange = async (trackedId, newStatus) => {
    try {
      setUpdatingId(trackedId);
      await updateTrackedOpportunity(trackedId, { tracking_status: newStatus });
      setTrackedOpps((prev) =>
        prev.map((o) => (o.id === trackedId ? { ...o, tracking_status: newStatus } : o))
      );
    } catch (err) {
      alert(err.message || "Failed to update opportunity status.");
    } finally {
      setUpdatingId(null);
    }
  };

  // Handle delete tracked
  const handleDeleteTracked = async (opp) => {
    const ok = window.confirm(`Stop tracking '${opp.title}'?`);
    if (!ok) return;
    try {
      await deleteTrackedOpportunity(opp.id);
      setTrackedOpps((prev) => prev.filter((o) => o.id !== opp.id));
    } catch (err) {
      alert(err.message || "Failed to delete tracked opportunity.");
    }
  };

  // Open modal to track a discovered opportunity
  const handleTrackDiscovered = (opp) => {
    setModalInitialData({
      opportunity_id: opp.id,
      title: opp.name,
      organizer: opp.organizer,
      category: opp.category || "Competition",
      description: opp.description,
      registration_url: opp.registration_url,
      registration_deadline: opp.registration_deadline,
      event_date: opp.event_date,
      source_type: opp.source_type || "gmail",
      evidence_text: opp.evidence_text,
      isNewTracking: true,
    });
    setModalOpen(true);
  };

  // Open modal for manual entry
  const handleAddNewManual = () => {
    setModalInitialData({ isNewTracking: true });
    setModalOpen(true);
  };

  // Open modal to edit existing tracked
  const handleEditTracked = (opp) => {
    setModalInitialData(opp);
    setModalOpen(true);
  };

  // Filter tracked opportunities
  const filteredTracked = trackedOpps.filter((opp) => {
    const matchesCategory = selectedCategory === "All" || opp.category === selectedCategory;
    const matchesStatus = selectedStatus === "All" || opp.tracking_status === selectedStatus;
    const q = searchQuery.toLowerCase().trim();
    const matchesQuery =
      !q ||
      (opp.title && opp.title.toLowerCase().includes(q)) ||
      (opp.organizer && opp.organizer.toLowerCase().includes(q)) ||
      (opp.description && opp.description.toLowerCase().includes(q));
    return matchesCategory && matchesStatus && matchesQuery;
  });

  // Calculate summary metrics
  const totalTracked = trackedOpps.length;
  const upcomingDeadlinesCount = trackedOpps.filter(
    (o) =>
      o.days_remaining !== null &&
      o.days_remaining >= 0 &&
      o.days_remaining <= 7 &&
      !["Completed", "Not Pursuing"].includes(o.tracking_status)
  ).length;
  const applicationsSubmittedCount = trackedOpps.filter((o) =>
    ["Submitted", "Completed"].includes(o.tracking_status)
  ).length;
  const registrationsCompletedCount = trackedOpps.filter((o) =>
    ["Registered", "Submitted", "Completed"].includes(o.tracking_status)
  ).length;

  // Filter discovered opportunities
  const filteredDiscovered = opportunities.filter((opp) => {
    if (discoveredFilterStatus === "ALL") return true;
    return (opp.student_status || "discovered").toLowerCase() === discoveredFilterStatus.toLowerCase();
  });

  const getStatusBadgeStyle = (st) => {
    switch (st) {
      case "Registered":
      case "Completed":
        return { bg: "#dcfce7", color: "#166534", border: "#bbf7d0" };
      case "Submitted":
        return { bg: "#e0e7ff", color: "#3730a3", border: "#c7d2fe" };
      case "Planning to Apply":
        return { bg: "#fef3c7", color: "#92400e", border: "#fde68a" };
      case "Not Pursuing":
        return { bg: "#f1f5f9", color: "#64748b", border: "#e2e8f0" };
      default:
        return { bg: "#ede9fe", color: "#5b21b6", border: "#ddd6fe" };
    }
  };

  return (
    <div className="opportunity-explorer" aria-label="Academic Competitions & Opportunities" style={{ maxWidth: 1140, margin: "0 auto", padding: "1.5rem" }}>
      {/* Page Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0, color: "#1e1b4b" }}>
            Competitions &amp; Opportunities
          </h1>
          <p style={{ color: "#64748b", margin: "0.25rem 0 0 0", fontSize: "0.95rem" }}>
            Discover contests, hackathons, internships, track registration deadlines, and share participation with faculty.
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
          {isStudent && (
            <button
              type="button"
              onClick={handleAddNewManual}
              style={{
                background: "#6366f1",
                color: "#fff",
                border: "none",
                padding: "0.55rem 1.1rem",
                borderRadius: "8px",
                cursor: "pointer",
                fontWeight: 600,
                fontSize: "0.88rem",
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
              }}
            >
              <span>➕</span> Add Opportunity
            </button>
          )}

          {onSyncGmail && (
            <button
              type="button"
              className="saas-primary-btn"
              onClick={onSyncGmail}
              disabled={loading}
              style={{ padding: "0.55rem 1rem", fontSize: "0.88rem" }}
            >
              <span>Sync Gmail</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Mode Tabs */}
      <div style={{ display: "flex", background: "#f1f5f9", padding: "4px", borderRadius: "10px", width: "fit-content", marginBottom: "1.5rem" }}>
        <button
          type="button"
          onClick={() => setActiveTab("tracked")}
          style={{
            padding: "0.5rem 1.25rem",
            borderRadius: "8px",
            border: "none",
            cursor: "pointer",
            fontWeight: 700,
            fontSize: "0.88rem",
            background: activeTab === "tracked" ? "#6366f1" : "transparent",
            color: activeTab === "tracked" ? "#fff" : "#475569",
            transition: "all 0.15s ease",
          }}
        >
          🎯 My Tracked Opportunities ({trackedOpps.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("discovered")}
          style={{
            padding: "0.5rem 1.25rem",
            borderRadius: "8px",
            border: "none",
            cursor: "pointer",
            fontWeight: 700,
            fontSize: "0.88rem",
            background: activeTab === "discovered" ? "#6366f1" : "transparent",
            color: activeTab === "discovered" ? "#fff" : "#475569",
            transition: "all 0.15s ease",
          }}
        >
          🔍 Discovered &amp; Ingested ({opportunities.length})
        </button>
      </div>

      {/* ========================================================================= */}
      {/* VIEW 1: MY TRACKED OPPORTUNITIES                                          */}
      {/* ========================================================================= */}
      {activeTab === "tracked" && (
        <div>
          {/* Summary KPI Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", marginBottom: "1.5rem" }}>
            <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.2rem", boxShadow: "0 1px 3px rgba(0,0,0,0.03)" }}>
              <span style={{ fontSize: "0.82rem", color: "#64748b", fontWeight: 600 }}>Total Tracked</span>
              <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#1e1b4b", marginTop: "0.25rem" }}>
                {totalTracked}
              </div>
            </div>

            <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.2rem", boxShadow: "0 1px 3px rgba(0,0,0,0.03)" }}>
              <span style={{ fontSize: "0.82rem", color: "#64748b", fontWeight: 600 }}>Upcoming Deadlines (&le;7d)</span>
              <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#e11d48", marginTop: "0.25rem" }}>
                {upcomingDeadlinesCount}
              </div>
            </div>

            <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.2rem", boxShadow: "0 1px 3px rgba(0,0,0,0.03)" }}>
              <span style={{ fontSize: "0.82rem", color: "#64748b", fontWeight: 600 }}>Registrations Completed</span>
              <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#16a34a", marginTop: "0.25rem" }}>
                {registrationsCompletedCount}
              </div>
            </div>

            <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.2rem", boxShadow: "0 1px 3px rgba(0,0,0,0.03)" }}>
              <span style={{ fontSize: "0.82rem", color: "#64748b", fontWeight: 600 }}>Applications Submitted</span>
              <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#7c3aed", marginTop: "0.25rem" }}>
                {applicationsSubmittedCount}
              </div>
            </div>
          </div>

          {/* Search & Filters */}
          <div style={{ marginBottom: "1.25rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
              {/* Search input */}
              <div style={{ position: "relative", minWidth: "260px", flex: 1 }}>
                <input
                  type="text"
                  placeholder="Search tracked opportunities by title or organizer..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.55rem 0.85rem 0.55rem 2.2rem",
                    borderRadius: "8px",
                    border: "1px solid #cbd5e1",
                    fontSize: "0.9rem",
                    boxSizing: "border-box",
                  }}
                />
                <span style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }}>
                  🔍
                </span>
              </div>

              {/* Status Select */}
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#475569" }}>Status:</span>
                <select
                  value={selectedStatus}
                  onChange={(e) => setSelectedStatus(e.target.value)}
                  style={{ padding: "0.5rem 0.75rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.88rem", background: "#fff" }}
                >
                  {TRACKING_STATUSES.map((st) => (
                    <option key={st} value={st}>
                      {st}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Category Pills */}
            <div style={{ display: "flex", gap: "0.45rem", overflowX: "auto", paddingBottom: "4px" }}>
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setSelectedCategory(cat)}
                  style={{
                    padding: "0.35rem 0.8rem",
                    borderRadius: "20px",
                    border: "1px solid",
                    borderColor: selectedCategory === cat ? "#6366f1" : "#e2e8f0",
                    background: selectedCategory === cat ? "#ede9fe" : "#fff",
                    color: selectedCategory === cat ? "#4f46e5" : "#64748b",
                    fontSize: "0.82rem",
                    fontWeight: selectedCategory === cat ? 700 : 500,
                    cursor: "pointer",
                    whiteSpace: "nowrap",
                  }}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Cards Grid */}
          {trackedLoading ? (
            <div style={{ textAlign: "center", padding: "3rem", color: "#64748b" }}>Loading tracked opportunities...</div>
          ) : filteredTracked.length === 0 ? (
            <div style={{ textAlign: "center", padding: "4rem 2rem", background: "#f8fafc", borderRadius: "12px", border: "2px dashed #cbd5e1" }}>
              <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>🎯</div>
              <h3 style={{ margin: "0 0 0.5rem 0", color: "#334155" }}>No Tracked Opportunities</h3>
              <p style={{ color: "#64748b", maxWidth: "460px", margin: "0 auto 1.25rem auto", fontSize: "0.9rem" }}>
                {searchQuery || selectedCategory !== "All" || selectedStatus !== "All"
                  ? "No tracked opportunities match your active filters. Try clearing filters."
                  : "Track external hackathons, competitions, or scholarships to manage your deadlines and faculty credits."}
              </p>
              {!searchQuery && selectedCategory === "All" && selectedStatus === "All" && (
                <button
                  type="button"
                  onClick={handleAddNewManual}
                  style={{
                    background: "#6366f1",
                    color: "#fff",
                    border: "none",
                    padding: "0.6rem 1.25rem",
                    borderRadius: "8px",
                    cursor: "pointer",
                    fontWeight: 600,
                  }}
                >
                  ➕ Track Your First Opportunity
                </button>
              )}
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1.25rem" }}>
              {filteredTracked.map((opp) => {
                const badge = getStatusBadgeStyle(opp.tracking_status);
                const isOverdue = opp.is_overdue;

                return (
                  <div
                    key={opp.id}
                    style={{
                      background: "#fff",
                      border: "1px solid #e2e8f0",
                      borderRadius: "12px",
                      padding: "1.25rem",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                    }}
                  >
                    <div>
                      {/* Top Badges */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}>
                        <span
                          style={{
                            background: "#ede9fe",
                            color: "#5b21b6",
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            padding: "0.2rem 0.55rem",
                            borderRadius: "6px",
                          }}
                        >
                          {opp.category}
                        </span>

                        <span
                          style={{
                            background: badge.bg,
                            color: badge.color,
                            border: `1px solid ${badge.border}`,
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            padding: "0.2rem 0.55rem",
                            borderRadius: "6px",
                          }}
                        >
                          {opp.tracking_status}
                        </span>
                      </div>

                      {/* Title & Organizer */}
                      <h3 style={{ fontSize: "1.05rem", fontWeight: 700, margin: "0 0 0.35rem 0", color: "#1e1b4b" }}>
                        {opp.title}
                      </h3>
                      {opp.organizer && (
                        <p style={{ color: "#64748b", fontSize: "0.85rem", margin: "0 0 0.65rem 0" }}>
                          Organized by <strong>{opp.organizer}</strong>
                        </p>
                      )}

                      {/* Description */}
                      {opp.description && (
                        <p style={{ color: "#475569", fontSize: "0.85rem", margin: "0 0 0.75rem 0", lineHeight: 1.4 }}>
                          {opp.description}
                        </p>
                      )}

                      {/* Associated Course */}
                      {opp.course_name && (
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.75rem", fontSize: "0.8rem", color: "#4338ca", background: "#eef2ff", padding: "0.3rem 0.6rem", borderRadius: "6px" }}>
                          <span>🎓 Course:</span>
                          <strong>{opp.course_name}</strong> ({opp.course_code})
                        </div>
                      )}

                      {/* Deadline Countdown Box */}
                      {opp.registration_deadline && (
                        <div
                          style={{
                            background: isOverdue ? "#fef2f2" : "#f0fdf4",
                            border: `1px solid ${isOverdue ? "#fecaca" : "#bbf7d0"}`,
                            borderRadius: "8px",
                            padding: "0.5rem 0.75rem",
                            marginBottom: "0.85rem",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                          }}
                        >
                          <div>
                            <span style={{ fontSize: "0.72rem", color: isOverdue ? "#991b1b" : "#166534", fontWeight: 600, display: "block" }}>
                              Registration Deadline
                            </span>
                            <span style={{ fontSize: "0.82rem", fontWeight: 700, color: isOverdue ? "#b91c1c" : "#15803d" }}>
                              {opp.registration_deadline.slice(0, 16).replace("T", " ")}
                            </span>
                          </div>
                          <span
                            style={{
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              background: isOverdue ? "#fee2e2" : "#dcfce7",
                              color: isOverdue ? "#991b1b" : "#15803d",
                              padding: "0.2rem 0.5rem",
                              borderRadius: "4px",
                            }}
                          >
                            {isOverdue ? "Overdue" : `${opp.days_remaining}d remaining`}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Footer Controls: Status Select & Actions */}
                    <div style={{ borderTop: "1px solid #f1f5f9", paddingTop: "0.85rem", marginTop: "0.5rem" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                        <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "#64748b" }}>My Status:</span>
                        <select
                          value={opp.tracking_status}
                          disabled={updatingId === opp.id}
                          onChange={(e) => handleTrackedStatusChange(opp.id, e.target.value)}
                          style={{
                            padding: "0.35rem 0.6rem",
                            borderRadius: "6px",
                            border: "1px solid #cbd5e1",
                            fontSize: "0.8rem",
                            background: "#fff",
                            fontWeight: 600,
                          }}
                        >
                          {TRACKING_STATUSES.filter((s) => s !== "All").map((s) => (
                            <option key={s} value={s}>
                              {s}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                        {opp.registration_url && (
                          <a
                            href={opp.registration_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              flex: 1,
                              textAlign: "center",
                              background: "#6366f1",
                              color: "#fff",
                              padding: "0.45rem 0.75rem",
                              borderRadius: "6px",
                              textDecoration: "none",
                              fontWeight: 600,
                              fontSize: "0.82rem",
                              display: "inline-flex",
                              alignItems: "center",
                              justifyContent: "center",
                              gap: "0.3rem",
                            }}
                          >
                            <span>Register ↗</span>
                          </a>
                        )}

                        <button
                          type="button"
                          onClick={() => handleEditTracked(opp)}
                          title="Edit details"
                          style={{ background: "#f8fafc", border: "1px solid #cbd5e1", padding: "0.45rem 0.65rem", borderRadius: "6px", cursor: "pointer", fontSize: "0.82rem" }}
                        >
                          ✏️
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteTracked(opp)}
                          title="Untrack opportunity"
                          style={{ background: "#fef2f2", border: "1px solid #fee2e2", color: "#b91c1c", padding: "0.45rem 0.65rem", borderRadius: "6px", cursor: "pointer", fontSize: "0.82rem" }}
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* VIEW 2: DISCOVERED & INGESTED OPPORTUNITIES                               */}
      {/* ========================================================================= */}
      {activeTab === "discovered" && (
        <div>
          {/* Status Pills */}
          <div className="section-pill-group" role="tablist" style={{ marginBottom: "1.25rem" }}>
            {[
              { id: "ALL", label: "All Discovered" },
              { id: "interested", label: "Interested" },
              { id: "registration_pending", label: "Pending Registration" },
              { id: "registered", label: "Registered" },
              { id: "attended", label: "Attended" },
            ].map((btn) => (
              <button
                key={btn.id}
                type="button"
                className={`section-tab-btn ${discoveredFilterStatus === btn.id ? "active" : ""}`}
                onClick={() => setDiscoveredFilterStatus(btn.id)}
              >
                {btn.label}
              </button>
            ))}
          </div>

          {filteredDiscovered.length === 0 ? (
            <div style={{ textAlign: "center", padding: "4rem 2rem", background: "#f8fafc", borderRadius: "12px", border: "2px dashed #cbd5e1" }}>
              <h4>No Discovered Competitions Found</h4>
              <p style={{ color: "#64748b" }}>
                Click "Sync Gmail" to scan your inbox for active hackathons, conferences, and student opportunities.
              </p>
            </div>
          ) : (
            <div className="opportunity-cards-grid">
              {filteredDiscovered.map((opp) => (
                <article key={opp.id} className="saas-card opp-card">
                  <div className="opp-card-top">
                    <div className="badge-group">
                      <span className="category-pill" style={{ backgroundColor: "#FEF3C7", color: "#92400E", borderColor: "#FCD34D" }}>
                        {opp.category || "Competition"}
                      </span>
                      {opp.confidence && (
                        <span className={`confidence-pill confidence-${opp.confidence.toLowerCase()}`}>
                          {opp.confidence}
                        </span>
                      )}
                      {opp.is_demo === 1 && <span className="demo-data-badge">Demo</span>}
                    </div>

                    {/* Track Opportunity Action Button */}
                    {isStudent && (
                      <button
                        type="button"
                        onClick={() => handleTrackDiscovered(opp)}
                        style={{
                          background: "#ede9fe",
                          color: "#5b21b6",
                          border: "1px solid #c4b5fd",
                          padding: "0.35rem 0.75rem",
                          borderRadius: "6px",
                          fontWeight: 700,
                          fontSize: "0.78rem",
                          cursor: "pointer",
                        }}
                      >
                        🎯 Track Opportunity
                      </button>
                    )}
                  </div>

                  <h3 className="opp-card-title">{opp.name}</h3>
                  {opp.organizer && (
                    <p className="opp-card-organizer">
                      Hosted by <strong>{opp.organizer}</strong>
                    </p>
                  )}

                  <p className="opp-card-desc">{opp.description}</p>

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

                  {opp.evidence_text && (
                    <div className="opp-evidence-snippet">
                      <span className="evidence-lbl">Source:</span>
                      <em>"{opp.evidence_text}"</em>
                    </div>
                  )}

                  <div className="opp-card-footer" style={{ marginTop: "1rem" }}>
                    {opp.registration_url && (
                      <a
                        href={opp.registration_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="saas-primary-btn opp-register-link"
                      >
                        <span>Official Registration ↗</span>
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Opportunity Tracking Modal */}
      <OpportunityTrackingModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        initialData={modalInitialData}
        onSaved={loadTracked}
      />
    </div>
  );
}
