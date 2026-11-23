import { useState, useEffect } from "react";
import { getTaskRelationships } from "../api";

export default function TaskRelationshipsModal({ task, onClose, onSelectTask }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [relationships, setRelationships] = useState(null);

  useEffect(() => {
    let active = true;
    async function fetchRels() {
      setLoading(true);
      setError("");
      try {
        const data = await getTaskRelationships(task.id);
        if (active) {
          setRelationships(data);
        }
      } catch (err) {
        if (active) {
          setError(err.message || "Failed to load task relationships.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    fetchRels();
    return () => {
      active = false;
    };
  }, [task.id]);

  const parent = relationships?.parent;
  const children = relationships?.children || [];
  const related = relationships?.related || [];
  const history = relationships?.history || [];

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rel-modal-title"
      onClick={onClose}
    >
      <div className="modal-dialog rel-modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span aria-hidden="true" style={{ fontSize: 20 }}>🔗</span>
            <div>
              <h3 id="rel-modal-title" style={{ margin: 0, fontSize: "1.15rem" }}>
                Task Lineage &amp; Relationships: #{task.id}
              </h3>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {task.title}
              </span>
            </div>
          </div>
          <button
            type="button"
            className="toast-close-btn"
            onClick={onClose}
            aria-label="Close relationship dialog"
          >
            ✕
          </button>
        </div>

        <div className="modal-body" style={{ maxHeight: "70vh", overflowY: "auto", padding: "18px 20px" }}>
          {loading && (
            <div style={{ textAlign: "center", padding: "30px 0" }}>
              <span className="spinner" aria-hidden="true" style={{ fontSize: 22 }}></span>
              <p style={{ marginTop: 8, color: "var(--text-muted)", fontSize: 13 }}>
                Retrieving lineage hierarchy from SQLite database...
              </p>
            </div>
          )}

          {error && (
            <div className="alert alert-error" role="alert">
              <span className="alert-icon" aria-hidden="true">⚠️</span>
              <div className="alert-body">
                <strong>Lineage Error</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          {!loading && !error && relationships && (
            <div className="relationships-content">
              {/* Parent / Predecessor Section */}
              <section className="rel-section">
                <h4 className="rel-heading">
                  <span>Predecessor Task (Replaces)</span>
                </h4>
                {parent ? (
                  <div className="rel-card">
                    <div className="rel-card-top">
                      <span className="category-pill-mini">{parent.category}</span>
                      <span className={`badge-status-mini badge-status-${(parent.status || "pending").toLowerCase()}`}>
                        {parent.status?.toUpperCase()}
                      </span>
                      <span className="rel-id">Task #{parent.id}</span>
                    </div>
                    <div className="rel-title">{parent.title}</div>
                    <div className="rel-meta">
                      <span>Due: {parent.due_date || "No date"}</span>
                      {parent.update_type && <span>Type: {parent.update_type}</span>}
                    </div>
                    {onSelectTask && (
                      <button
                        type="button"
                        className="btn-link"
                        onClick={() => {
                          onClose();
                          onSelectTask(parent.id);
                        }}
                      >
                        View Predecessor Task →
                      </button>
                    )}
                  </div>
                ) : (
                  <p className="rel-none">This task does not supersede an earlier deadline.</p>
                )}
              </section>

              {/* Children / Successors Section */}
              <section className="rel-section" style={{ marginTop: 18 }}>
                <h4 className="rel-heading">
                  <span>Successor Revisions (Replaced by)</span>
                  <span className="rel-count-badge">{children.length}</span>
                </h4>
                {children.length > 0 ? (
                  <div className="rel-list">
                    {children.map((child) => (
                      <div key={child.id} className="rel-card">
                        <div className="rel-card-top">
                          <span className="category-pill-mini">{child.category}</span>
                          <span className={`badge-status-mini badge-status-${(child.status || "pending").toLowerCase()}`}>
                            {child.status?.toUpperCase()}
                          </span>
                          <span className="rel-id">Task #{child.id}</span>
                        </div>
                        <div className="rel-title">{child.title}</div>
                        <div className="rel-meta">
                          <span>Due: {child.due_date || "No date"}</span>
                          {child.update_type && <span>Update: {child.update_type}</span>}
                        </div>
                        {onSelectTask && (
                          <button
                            type="button"
                            className="btn-link"
                            onClick={() => {
                              onClose();
                              onSelectTask(child.id);
                            }}
                          >
                            View Successor Task →
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="rel-none">No subsequent announcements have modified or superseded this task.</p>
                )}
              </section>

              {/* Related Tasks (same academic identifier) */}
              <section className="rel-section" style={{ marginTop: 18 }}>
                <h4 className="rel-heading">
                  <span>Related Course Tasks (Matching Identifier)</span>
                  <span className="rel-count-badge">{related.length}</span>
                </h4>
                {related.length > 0 ? (
                  <div className="rel-list">
                    {related.map((relItem) => (
                      <div key={relItem.id} className="rel-card">
                        <div className="rel-card-top">
                          <span className="category-pill-mini">{relItem.category}</span>
                          <span className={`badge-status-mini badge-status-${(relItem.status || "pending").toLowerCase()}`}>
                            {relItem.status?.toUpperCase()}
                          </span>
                          <span className="rel-id">Task #{relItem.id}</span>
                        </div>
                        <div className="rel-title">{relItem.title}</div>
                        <div className="rel-meta">
                          <span>Due: {relItem.due_date || "No date"}</span>
                          <span>Priority: {relItem.priority || "MEDIUM"}</span>
                        </div>
                        {onSelectTask && (
                          <button
                            type="button"
                            className="btn-link"
                            onClick={() => {
                              onClose();
                              onSelectTask(relItem.id);
                            }}
                          >
                            View Task →
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="rel-none">No other active tasks share this academic identifier.</p>
                )}
              </section>

              {/* Revision History Timeline */}
              {history.length > 0 && (
                <section className="rel-section" style={{ marginTop: 18 }}>
                  <h4 className="rel-heading">
                    <span>Revision Timeline</span>
                  </h4>
                  <div className="timeline-container">
                    {history.map((step, idx) => (
                      <div key={step.id || idx} className="timeline-step">
                        <div className="timeline-dot"></div>
                        <div className="timeline-content">
                          <div className="timeline-header">
                            <strong>Task #{step.id}</strong>
                            <span className="timeline-date">{step.source_timestamp || step.created_at || "Timeline item"}</span>
                          </div>
                          <div className="timeline-body">
                            <span>{step.title}</span>
                            <span className="timeline-status-tag">Status: {step.status}</span>
                            {step.due_date && <span>Due: {step.due_date}</span>}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}
        </div>

        <div className="modal-footer" style={{ borderTop: "1px solid var(--border-light)", padding: "12px 20px" }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
