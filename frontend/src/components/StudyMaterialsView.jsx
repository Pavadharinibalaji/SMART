import { useState } from "react";

export default function StudyMaterialsView({ materials = [], loading = false }) {
  const [sourceFilter, setSourceFilter] = useState("ALL");

  const filtered = materials.filter((m) => {
    if (sourceFilter === "ALL") return true;
    return (m.source_type || "").toLowerCase() === sourceFilter.toLowerCase();
  });

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return "0 KB";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  return (
    <div className="study-materials-view" aria-label="Study Materials & Course Attachments">
      <div className="saas-page-header">
        <div className="header-text-block">
          <h2 className="saas-page-title">Study Materials &amp; Attachments</h2>
          <p className="saas-page-subtitle">
            Consolidated lecture slides, reference manuals, syllabus copies, and email attachments.
          </p>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="section-pill-group" role="tablist" aria-label="Materials source filters">
        {[
          { id: "ALL", label: "All Materials" },
          { id: "classroom_material", label: "Classroom Materials" },
          { id: "gmail_attachment", label: "Gmail Attachments" },
        ].map((btn) => (
          <button
            key={btn.id}
            type="button"
            className={`section-tab-btn ${sourceFilter === btn.id ? "active" : ""}`}
            onClick={() => setSourceFilter(btn.id)}
          >
            {btn.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="saas-card chart-empty-state">
          <span className="spinner" aria-hidden="true" style={{ fontSize: 28 }} />
          <p>Loading study materials...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="saas-card chart-empty-state">
          <div className="empty-state-icon" aria-hidden="true">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </svg>
          </div>
          <h4>No Study Materials Yet</h4>
          <p>Sync your Gmail or Classroom to automatically index syllabus documents and course materials.</p>
        </div>
      ) : (
        <div className="materials-grid">
          {filtered.map((mat) => (
            <div key={mat.id} className="saas-card material-card">
              <div className="material-icon-box" aria-hidden="true">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              </div>
              <div className="material-content">
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
                  <span className={`source-pill source-pill-${mat.source_type === "classroom_material" ? "google_classroom" : "gmail"}`}>
                    {mat.source_type === "classroom_material" ? "Classroom Material" : "Email Attachment"}
                  </span>
                  {mat.is_demo === 1 && <span className="demo-data-badge">Demo</span>}
                </div>
                <h4 className="material-title">{mat.title}</h4>
                <p className="material-meta">
                  {mat.course_name ? `${mat.course_name} • ` : ""}
                  {formatBytes(mat.file_size)}
                </p>
              </div>

              {mat.file_url && (
                <a
                  href={mat.file_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="saas-secondary-btn"
                  style={{ alignSelf: "center", whiteSpace: "nowrap" }}
                >
                  Open File ↗
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
