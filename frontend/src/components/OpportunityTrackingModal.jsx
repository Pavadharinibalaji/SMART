import { useState, useEffect } from "react";
import { getSmartCourses, trackOpportunity, updateTrackedOpportunity } from "../api";

const CATEGORIES = [
  "Competition",
  "Hackathon",
  "Internship",
  "Workshop",
  "Scholarship",
  "Conference",
  "Other",
];

const STATUSES = [
  "Interested",
  "Planning to Apply",
  "Registered",
  "Submitted",
  "Completed",
  "Not Pursuing",
];

export default function OpportunityTrackingModal({
  isOpen,
  onClose,
  initialData = null,
  onSaved,
}) {
  const isEditing = Boolean(initialData?.id && !initialData?.isNewTracking);

  const [title, setTitle] = useState("");
  const [organizer, setOrganizer] = useState("");
  const [category, setCategory] = useState("Competition");
  const [description, setDescription] = useState("");
  const [registrationUrl, setRegistrationUrl] = useState("");
  const [registrationDeadline, setRegistrationDeadline] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [trackingStatus, setTrackingStatus] = useState("Interested");
  const [courseId, setCourseId] = useState("");
  const [enrolledCourses, setEnrolledCourses] = useState([]);
  const [loadingCourses, setLoadingCourses] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isOpen) {
      setError("");
      setTitle(initialData?.title || initialData?.name || "");
      setOrganizer(initialData?.organizer || "");
      setCategory(initialData?.category || "Competition");
      setDescription(initialData?.description || "");
      setRegistrationUrl(initialData?.registration_url || initialData?.url || "");
      setRegistrationDeadline(
        initialData?.registration_deadline
          ? initialData.registration_deadline.slice(0, 16)
          : initialData?.due_date
          ? initialData.due_date.slice(0, 10)
          : ""
      );
      setEventDate(initialData?.event_date ? initialData.event_date.slice(0, 10) : "");
      setTrackingStatus(initialData?.tracking_status || "Interested");
      setCourseId(initialData?.course_id ? String(initialData.course_id) : "");

      // Load enrolled courses for course association
      setLoadingCourses(true);
      getSmartCourses()
        .then((res) => {
          setEnrolledCourses(res.courses || []);
        })
        .catch((err) => console.error("Could not load courses:", err))
        .finally(() => setLoadingCourses(false));
    }
  }, [isOpen, initialData]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Opportunity title is required.");
      return;
    }

    try {
      setSaving(true);
      setError("");

      const payload = {
        title: title.trim(),
        organizer: organizer.trim() || null,
        category,
        description: description.trim() || null,
        registration_url: registrationUrl.trim() || null,
        registration_deadline: registrationDeadline || null,
        event_date: eventDate || null,
        tracking_status: trackingStatus,
        course_id: courseId ? Number(courseId) : null,
      };

      if (isEditing) {
        await updateTrackedOpportunity(initialData.id, payload);
      } else {
        payload.opportunity_id = initialData?.opportunity_id || (initialData?.isNewTracking ? null : initialData?.id) || null;
        payload.source_platform = initialData?.source_type || initialData?.source_platform || "manual";
        payload.source_reference = initialData?.evidence_text || initialData?.source_reference || null;
        await trackOpportunity(payload);
      }

      if (onSaved) onSaved();
      onClose();
    } catch (err) {
      setError(err.message || "Failed to save opportunity tracking.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15, 23, 42, 0.6)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1050,
        padding: "1rem",
      }}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: "14px",
          maxWidth: "560px",
          width: "100%",
          padding: "1.75rem",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1)",
          maxHeight: "90vh",
          overflowY: "auto",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <div>
            <h2 style={{ fontSize: "1.3rem", fontWeight: 700, margin: 0, color: "#1e1b4b" }}>
              {isEditing ? "Edit Tracked Opportunity" : "Track Competition or Opportunity"}
            </h2>
            <p style={{ color: "#64748b", margin: "0.2rem 0 0 0", fontSize: "0.88rem" }}>
              Track deadlines, organize requirements, and share participation with faculty.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{ background: "transparent", border: "none", fontSize: "1.5rem", cursor: "pointer", color: "#64748b" }}
          >
            ×
          </button>
        </div>

        {/* Clear External Registration Notice */}
        <div
          style={{
            background: "#eff6ff",
            border: "1px solid #bfdbfe",
            borderRadius: "8px",
            padding: "0.75rem 1rem",
            marginBottom: "1.25rem",
            fontSize: "0.84rem",
            color: "#1e40af",
            lineHeight: 1.45,
          }}
        >
          ℹ️ <strong>Note:</strong> Tracking an opportunity in SMART helps you plan deadlines and notify course faculty. It does <em>not</em> automatically register you for the external competition or program.
        </div>

        {error && (
          <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", padding: "0.65rem 0.85rem", borderRadius: "8px", marginBottom: "1rem", fontSize: "0.88rem" }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
          {/* Title */}
          <div>
            <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
              Opportunity Title *
            </label>
            <input
              type="text"
              placeholder="e.g. ACM ICPC Regional Contest 2026"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem", boxSizing: "border-box" }}
            />
          </div>

          {/* Organizer & Category */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                Organizer / Host
              </label>
              <input
                type="text"
                placeholder="e.g. IEEE / Google / ACM"
                value={organizer}
                onChange={(e) => setOrganizer(e.target.value)}
                style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem", boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem" }}
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Registration Deadline & Event Date */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                Registration Deadline
              </label>
              <input
                type="datetime-local"
                value={registrationDeadline}
                onChange={(e) => setRegistrationDeadline(e.target.value)}
                style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.85rem", boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                Event Date (Optional)
              </label>
              <input
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
                style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.85rem", boxSizing: "border-box" }}
              />
            </div>
          </div>

          {/* Associated Course & Status */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                Associated Course
              </label>
              <select
                value={courseId}
                onChange={(e) => setCourseId(e.target.value)}
                style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem" }}
              >
                <option value="">(None / Personal)</option>
                {enrolledCourses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.code})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                Tracking Status
              </label>
              <select
                value={trackingStatus}
                onChange={(e) => setTrackingStatus(e.target.value)}
                style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem" }}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Registration URL */}
          <div>
            <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
              Application / Registration Link
            </label>
            <input
              type="url"
              placeholder="https://..."
              value={registrationUrl}
              onChange={(e) => setRegistrationUrl(e.target.value)}
              style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem", boxSizing: "border-box" }}
            />
          </div>

          {/* Description */}
          <div>
            <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
              Description &amp; Notes
            </label>
            <textarea
              rows={2}
              placeholder="Team members, submission requirements, or notes..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.88rem", boxSizing: "border-box" }}
            />
          </div>

          {/* Action buttons */}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "0.75rem" }}>
            <button
              type="button"
              onClick={onClose}
              style={{ padding: "0.55rem 1rem", borderRadius: "8px", border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer", fontWeight: 600 }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              style={{
                padding: "0.55rem 1.25rem",
                borderRadius: "8px",
                border: "none",
                background: "#6366f1",
                color: "#fff",
                fontWeight: 600,
                cursor: saving ? "not-allowed" : "pointer",
              }}
            >
              {saving ? "Saving..." : isEditing ? "Save Changes" : "Track Opportunity"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
