import { useState } from "react";

const CATEGORIES = ["Assignment", "Exam", "Announcement", "Opportunity", "Event"];
const IMPORTANCE_LEVELS = ["HIGH", "MEDIUM", "LOW", "UNASSESSED"];
const STATUS_OPTIONS = ["pending", "completed", "cancelled", "superseded", "dismissed"];

export default function EditTaskModal({ task, onClose, onSave }) {
  const [title, setTitle] = useState(task.title || "");
  const [category, setCategory] = useState(task.category || "Assignment");
  const [dueDate, setDueDate] = useState(task.due_date || "");
  const [importance, setImportance] = useState(task.importance || "UNASSESSED");
  const [status, setStatus] = useState((task.status || "pending").toLowerCase());
  const [description, setDescription] = useState(task.description || "");
  const [reviewRequired, setReviewRequired] = useState(Boolean(task.review_required));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Task title cannot be empty.");
      return;
    }

    setSaving(true);
    setError("");

    try {
      const updates = {
        title: title.trim(),
        category,
        due_date: dueDate.trim() ? dueDate.trim() : null,
        importance,
        status,
        description: description.trim(),
        review_required: reviewRequired,
      };

      await onSave(updates);
      onClose();
    } catch (err) {
      setError(err.message || "Failed to save task edits.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-modal-title"
      onClick={onClose}
    >
      <div className="modal-dialog edit-modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span aria-hidden="true" style={{ fontSize: 20 }}>✏️</span>
            <div>
              <h3 id="edit-modal-title" style={{ margin: 0, fontSize: "1.15rem" }}>
                Edit Academic Task #{task.id}
              </h3>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Update title, due date, category, importance, or lifecycle status.
              </span>
            </div>
          </div>
          <button
            type="button"
            className="toast-close-btn"
            onClick={onClose}
            aria-label="Close edit dialog"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body" style={{ maxHeight: "68vh", overflowY: "auto" }}>
            {error && (
              <div className="alert alert-error" role="alert" style={{ marginBottom: 14 }}>
                <span className="alert-icon" aria-hidden="true">⚠️</span>
                <div className="alert-body">
                  <strong>Edit Error</strong>
                  <p>{error}</p>
                </div>
              </div>
            )}

            <div className="form-group">
              <label htmlFor="edit-task-title" className="form-label">
                Task Title <span style={{ color: "var(--rose-text)" }}>*</span>
              </label>
              <input
                id="edit-task-title"
                type="text"
                className="filter-input"
                style={{ width: "100%", padding: "8px 12px" }}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                disabled={saving}
              />
            </div>

            <div className="form-row-2col" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
              <div className="form-group">
                <label htmlFor="edit-task-category" className="form-label">
                  Category
                </label>
                <select
                  id="edit-task-category"
                  className="filter-input"
                  style={{ width: "100%", padding: "8px 12px" }}
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  disabled={saving}
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="edit-task-importance" className="form-label">
                  Importance Level
                </label>
                <select
                  id="edit-task-importance"
                  className="filter-input"
                  style={{ width: "100%", padding: "8px 12px" }}
                  value={importance}
                  onChange={(e) => setImportance(e.target.value)}
                  disabled={saving}
                >
                  {IMPORTANCE_LEVELS.map((lvl) => (
                    <option key={lvl} value={lvl}>
                      {lvl === "HIGH"
                        ? "HIGH (High Stakes / Mandatory)"
                        : lvl === "MEDIUM"
                        ? "MEDIUM (Core Progression)"
                        : lvl === "LOW"
                        ? "LOW (Optional / General)"
                        : "UNASSESSED"}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-row-2col" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
              <div className="form-group">
                <label htmlFor="edit-task-duedate" className="form-label">
                  Due Date (YYYY-MM-DD)
                </label>
                <input
                  id="edit-task-duedate"
                  type="date"
                  className="filter-input"
                  style={{ width: "100%", padding: "8px 12px" }}
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  disabled={saving}
                />
              </div>

              <div className="form-group">
                <label htmlFor="edit-task-status" className="form-label">
                  Lifecycle Status
                </label>
                <select
                  id="edit-task-status"
                  className="filter-input"
                  style={{ width: "100%", padding: "8px 12px" }}
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  disabled={saving}
                >
                  {STATUS_OPTIONS.map((st) => (
                    <option key={st} value={st}>
                      {st.charAt(0).toUpperCase() + st.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-group" style={{ marginTop: 12 }}>
              <label htmlFor="edit-task-desc" className="form-label">
                Task Description / Notes
              </label>
              <textarea
                id="edit-task-desc"
                rows={3}
                className="filter-input"
                style={{ width: "100%", padding: "8px 12px", resize: "vertical" }}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={saving}
                placeholder="Additional notes or academic details..."
              />
            </div>

            {task.review_required && (
              <div
                className="review-edit-notice"
                style={{
                  marginTop: 14,
                  padding: "10px 14px",
                  background: "#fffbeb",
                  border: "1px solid #fde68a",
                  borderRadius: 6,
                }}
              >
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    cursor: "pointer",
                    fontSize: 13,
                    fontWeight: 600,
                    color: "#92400e",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={!reviewRequired}
                    onChange={(e) => setReviewRequired(!e.target.checked)}
                  />
                  <span>
                    ✓ Mark as human-reviewed &amp; verified (clears review warning)
                  </span>
                </label>
              </div>
            )}

            <div className="immutable-notice" style={{ marginTop: 14, padding: "10px 12px", background: "var(--bg-muted)", borderRadius: 6, fontSize: 12, color: "var(--text-dim)" }}>
              🔒 <strong>Cryptographic &amp; Provenance Protection:</strong> Original message text, sender (<code>{task.source_sender || "Unknown"}</code>), timestamp, and confidence (<code>{task.confidence || "UNASSESSED"}</code>) are immutable and cannot be altered.
            </div>
          </div>

          <div className="modal-footer" style={{ borderTop: "1px solid var(--border-light)", padding: "14px 20px" }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={saving}
            >
              {saving ? (
                <>
                  <span className="spinner" aria-hidden="true"></span>
                  Saving...
                </>
              ) : (
                "Save Changes"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
