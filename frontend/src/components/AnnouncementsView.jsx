import { useState, useEffect } from "react";
import {
  getSmartCourses,
  getCourseAnnouncements,
  createCourseAnnouncement,
  acknowledgeAnnouncement,
} from "../api";

export default function AnnouncementsView({ user }) {
  const isTeacher = user?.role === "teacher";
  const [courses, setCourses] = useState([]);
  const [selectedCourseId, setSelectedCourseId] = useState(null);
  const [announcements, setAnnouncements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Create form modal state
  const [showModal, setShowModal] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [isPinned, setIsPinned] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function loadCourses() {
      try {
        setLoading(true);
        const data = await getSmartCourses();
        const list = data.courses || [];
        setCourses(list);
        if (list.length > 0) {
          setSelectedCourseId(list[0].id);
        }
      } catch (err) {
        setError(err.message || "Failed to load courses");
      } finally {
        setLoading(false);
      }
    }
    loadCourses();
  }, []);

  const loadAnnouncements = async (cId) => {
    if (!cId) return;
    try {
      setLoading(true);
      setError("");
      const data = await getCourseAnnouncements(cId);
      setAnnouncements(data.announcements || []);
    } catch (err) {
      setError(err.message || "Failed to load announcements");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedCourseId) {
      loadAnnouncements(selectedCourseId);
    }
  }, [selectedCourseId]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!title.trim() || !content.trim() || !selectedCourseId) return;

    try {
      setSubmitting(true);
      setError("");
      await createCourseAnnouncement(selectedCourseId, {
        title: title.trim(),
        content: content.trim(),
        is_pinned: isPinned,
      });
      setSuccess("Announcement broadcast successfully!");
      setShowModal(false);
      setTitle("");
      setContent("");
      setIsPinned(false);
      loadAnnouncements(selectedCourseId);
    } catch (err) {
      setError(err.message || "Failed to create announcement");
    } finally {
      setSubmitting(false);
    }
  };

  const handleAcknowledge = async (annId) => {
    try {
      await acknowledgeAnnouncement(selectedCourseId, annId);
      setAnnouncements((prev) =>
        prev.map((a) => (a.id === annId ? { ...a, acknowledged: true } : a))
      );
      setSuccess("Marked as read & acknowledged.");
    } catch (err) {
      setError(err.message || "Failed to acknowledge");
    }
  };

  return (
    <div style={{ padding: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0, color: "#1e1b4b" }}>
            Course Announcements &amp; Broadcasts
          </h1>
          <p style={{ color: "#64748b", margin: "0.25rem 0 0 0" }}>
            Official notices, exam updates, schedule changes, and priority alerts.
          </p>
        </div>

        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          {courses.length > 0 && (
            <select
              value={selectedCourseId || ""}
              onChange={(e) => setSelectedCourseId(Number(e.target.value) || e.target.value)}
              style={{ padding: "0.55rem 0.9rem", borderRadius: "8px", border: "1px solid #cbd5e1", background: "#fff", fontWeight: 600, color: "#334155" }}
            >
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} - {c.title || c.name}
                </option>
              ))}
            </select>
          )}

          {isTeacher && selectedCourseId && (
            <button
              type="button"
              onClick={() => setShowModal(true)}
              style={{ background: "#6366f1", color: "#fff", border: "none", padding: "0.55rem 1.1rem", borderRadius: "8px", cursor: "pointer", fontWeight: 600 }}
            >
              + Broadcast Announcement
            </button>
          )}
        </div>
      </div>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", padding: "0.75rem 1rem", borderRadius: "8px", marginBottom: "1.25rem" }}>
          {error}
        </div>
      )}
      {success && (
        <div style={{ background: "#f0fdf4", color: "#15803d", border: "1px solid #bbf7d0", padding: "0.75rem 1rem", borderRadius: "8px", marginBottom: "1.25rem" }}>
          {success}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: "center", padding: "3rem", color: "#64748b" }}>Loading announcements...</div>
      ) : announcements.length === 0 ? (
        <div style={{ textAlign: "center", padding: "4rem 2rem", background: "#f8fafc", borderRadius: "12px", border: "2px dashed #e2e8f0" }}>
          <h3 style={{ color: "#334155", margin: "0 0 0.5rem 0" }}>No Announcements Yet</h3>
          <p style={{ color: "#64748b", margin: 0 }}>
            {isTeacher ? "Broadcast an update to notify your enrolled students." : "Check back later for updates from your course instructors."}
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {announcements.map((ann) => (
            <div
              key={ann.id}
              style={{
                background: "#fff",
                borderRadius: "10px",
                border: ann.is_pinned ? "2px solid #6366f1" : "1px solid #e2e8f0",
                boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                padding: "1.25rem",
                position: "relative",
              }}
            >
              {ann.is_pinned && (
                <span
                  style={{
                    position: "absolute",
                    top: "12px",
                    right: "12px",
                    background: "#ede9fe",
                    color: "#6d28d9",
                    padding: "0.2rem 0.5rem",
                    borderRadius: "4px",
                    fontSize: "0.75rem",
                    fontWeight: 700,
                  }}
                >
                  📌 PINNED
                </span>
              )}

              <div style={{ fontSize: "0.8rem", color: "#64748b", marginBottom: "0.35rem" }}>
                <span>Posted by {ann.author_name}</span> &bull;{" "}
                <span>{ann.created_at ? new Date(ann.created_at).toLocaleDateString() : ""}</span>
              </div>

              <h3 style={{ margin: "0 0 0.5rem 0", fontSize: "1.2rem", color: "#0f172a" }}>{ann.title}</h3>
              <p style={{ margin: "0 0 1rem 0", color: "#334155", lineHeight: "1.5", whiteSpace: "pre-wrap" }}>
                {ann.content}
              </p>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid #f1f5f9", paddingTop: "0.75rem" }}>
                <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
                  {ann.acknowledgment_count !== undefined ? `${ann.acknowledgment_count} students read` : ""}
                </span>

                {!isTeacher && (
                  <div>
                    {ann.acknowledged ? (
                      <span style={{ color: "#16a34a", fontSize: "0.85rem", fontWeight: 600 }}>✓ Acknowledged</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleAcknowledge(ann.id)}
                        style={{ background: "#eef2ff", color: "#4f46e5", border: "1px solid #c7d2fe", padding: "0.35rem 0.75rem", borderRadius: "6px", cursor: "pointer", fontSize: "0.85rem", fontWeight: 600 }}
                      >
                        Acknowledge Notice
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div style={{ background: "#fff", width: "100%", maxWidth: "520px", borderRadius: "12px", padding: "1.5rem", boxShadow: "0 20px 25px -5px rgba(0,0,0,0.1)" }}>
            <h2 style={{ margin: "0 0 1rem 0", fontSize: "1.25rem", color: "#1e1b4b" }}>Broadcast Course Announcement</h2>
            <form onSubmit={handleCreate}>
              <div style={{ marginBottom: "1rem" }}>
                <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Midterm Examination Schedule & Format"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  style={{ width: "100%", padding: "0.6rem", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                />
              </div>

              <div style={{ marginBottom: "1rem" }}>
                <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>Content *</label>
                <textarea
                  required
                  rows={4}
                  placeholder="Details, instructions, deadlines, or room assignments..."
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  style={{ width: "100%", padding: "0.6rem", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                />
              </div>

              <div style={{ marginBottom: "1.5rem" }}>
                <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.9rem", color: "#334155", cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={isPinned}
                    onChange={(e) => setIsPinned(e.target.checked)}
                  />
                  Pin this announcement to top of course view
                </label>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  style={{ padding: "0.6rem 1rem", borderRadius: "6px", border: "1px solid #cbd5e1", background: "#f8fafc", cursor: "pointer" }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  style={{ padding: "0.6rem 1.25rem", borderRadius: "6px", border: "none", background: "#6366f1", color: "#fff", fontWeight: 600, cursor: "pointer" }}
                >
                  {submitting ? "Broadcasting..." : "Broadcast"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
