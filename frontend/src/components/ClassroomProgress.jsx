import { useState } from "react";
import { turnInCoursework } from "../api";

export default function ClassroomProgress({
  courses = [],
  coursework = [],
  submissions = [],
  onSyncClassroom,
  onSubmissionsUpdated,
  loading = false,
}) {
  const [selectedCourseId, setSelectedCourseId] = useState("ALL");
  const [submittingCwId, setSubmittingCwId] = useState(null);
  const [feedbackMsg, setFeedbackMsg] = useState(null);

  const handleTurnIn = async (cw) => {
    setSubmittingCwId(cw.id);
    setFeedbackMsg(null);
    try {
      await turnInCoursework(cw.id, cw.alternate_link);
      setFeedbackMsg({
        type: "success",
        text: `Successfully turned in "${cw.title}". Your submission is pending grading.`,
      });
      if (onSubmissionsUpdated) {
        onSubmissionsUpdated();
      }
    } catch (err) {
      setFeedbackMsg({
        type: "error",
        text: err.message || "Failed to turn in assignment. Please try again.",
      });
    } finally {
      setSubmittingCwId(null);
    }
  };

  const filteredCoursework = coursework.filter((cw) => {
    if (selectedCourseId === "ALL") return true;
    return cw.course_id === selectedCourseId;
  });

  return (
    <div className="classroom-progress-view" aria-label="Google Classroom Courses and Progress">
      {/* Header */}
      <div className="saas-page-header">
        <div className="header-text-block">
          <h2 className="saas-page-title">Google Classroom &amp; Coursework</h2>
          <p className="saas-page-subtitle">
            Track enrolled courses, upcoming assignments, and graded submission states.
          </p>
        </div>
        <div className="header-action-block">
          {onSyncClassroom && (
            <button
              type="button"
              className="saas-primary-btn"
              onClick={onSyncClassroom}
              disabled={loading}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
                <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
              </svg>
              <span>Sync Classroom</span>
            </button>
          )}
        </div>
      </div>

      {/* Feedback banner */}
      {feedbackMsg && (
        <div
          className={`saas-alert-banner ${feedbackMsg.type === "success" ? "alert-success" : "alert-error"}`}
          style={{
            padding: "12px 16px",
            marginBottom: 20,
            borderRadius: 8,
            backgroundColor: feedbackMsg.type === "success" ? "rgba(16, 185, 129, 0.1)" : "rgba(239, 68, 68, 0.1)",
            color: feedbackMsg.type === "success" ? "#065f46" : "#991b1b",
            border: `1px solid ${feedbackMsg.type === "success" ? "#a7f3d0" : "#fecaca"}`,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>{feedbackMsg.text}</span>
          <button
            type="button"
            onClick={() => setFeedbackMsg(null)}
            style={{ background: "none", border: "none", cursor: "pointer", fontWeight: "bold" }}
          >
            ×
          </button>
        </div>
      )}

      {/* Courses Cards */}
      <div className="courses-section">
        <h3 className="card-section-title" style={{ marginBottom: 12 }}>Enrolled Courses ({courses.length})</h3>
        {courses.length === 0 ? (
          <div className="saas-card chart-empty-state">
            <div className="empty-state-icon" aria-hidden="true">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
                <path d="M6 12v5c3 3 9 3 12 0v-5" />
              </svg>
            </div>
            <h4>No Classroom Courses Connected</h4>
            <p>Connect your student Google account and click "Sync Classroom" to load your active courses.</p>
          </div>
        ) : (
          <div className="courses-grid">
            <button
              type="button"
              className={`course-card ${selectedCourseId === "ALL" ? "course-active" : ""}`}
              onClick={() => setSelectedCourseId("ALL")}
            >
              <span className="course-card-badge">All Courses</span>
              <h4 className="course-card-title">All Course Deliverables</h4>
              <span className="course-card-meta">{coursework.length} active assignments</span>
            </button>

            {courses.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`course-card ${selectedCourseId === c.id ? "course-active" : ""}`}
                onClick={() => setSelectedCourseId(c.id)}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="course-card-badge">{c.section || "Classroom"}</span>
                  {c.is_demo === 1 && <span className="demo-data-badge">Demo</span>}
                </div>
                <h4 className="course-card-title">{c.name}</h4>
                <p className="course-card-desc">{c.description_heading || c.room || "Google Classroom"}</p>
                {c.alternate_link && (
                  <a
                    href={c.alternate_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="course-ext-link"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open in Classroom ↗
                  </a>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Coursework & Submission Progress */}
      <div className="saas-card coursework-section" style={{ marginTop: 24 }}>
        <div className="card-header-row">
          <div>
            <h3 className="card-section-title">Assignments &amp; Submission Progress</h3>
            <p className="card-section-desc">Coursework deadlines, turned-in status, and received grades</p>
          </div>
        </div>

        {filteredCoursework.length === 0 ? (
          <div className="chart-empty-state">
            <span className="empty-state-icon">📝</span>
            <p>No active coursework items for the selected course.</p>
          </div>
        ) : (
          <div className="coursework-table-wrapper">
            <table className="saas-table">
              <thead>
                <tr>
                  <th>Assignment Title</th>
                  <th>Course</th>
                  <th>Due Date</th>
                  <th>Status</th>
                  <th>Grade</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredCoursework.map((cw) => {
                  const sub = submissions.find((s) => s.coursework_id === cw.id);
                  const state = sub?.state || "NEW";
                  const grade = sub?.assigned_grade !== null && sub?.assigned_grade !== undefined
                    ? `${sub.assigned_grade} / ${cw.max_points || 100}`
                    : (state === "TURNED_IN" ? "Pending grading" : "Not submitted");

                  return (
                    <tr key={cw.id}>
                      <td>
                        <strong className="table-title">{cw.title}</strong>
                        {cw.description && <p className="table-desc">{cw.description.slice(0, 100)}</p>}
                      </td>
                      <td>
                        <span className="course-tag">{cw.course_name || "Course"}</span>
                      </td>
                      <td>
                        <span className="date-val">{cw.due_date || "No due date"}</span>
                        {cw.due_time && <span className="time-val"> {cw.due_time}</span>}
                      </td>
                      <td>
                        <span className={`status-badge-sub sub-state-${state.toLowerCase()}`}>
                          {state === "TURNED_IN" ? "Turned In" : state === "RETURNED" ? "Graded" : "Pending"}
                        </span>
                      </td>
                      <td>
                        <span className="grade-val">{grade}</span>
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                          {state !== "TURNED_IN" && state !== "RETURNED" ? (
                            <button
                              type="button"
                              className="saas-primary-btn"
                              style={{ padding: "6px 12px", fontSize: "0.8125rem", whiteSpace: "nowrap" }}
                              onClick={() => handleTurnIn(cw)}
                              disabled={submittingCwId === cw.id}
                            >
                              {submittingCwId === cw.id ? "Turning In..." : "Turn In"}
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="saas-outline-btn-sm"
                              style={{ padding: "6px 12px", fontSize: "0.8125rem", whiteSpace: "nowrap" }}
                              onClick={() => handleTurnIn(cw)}
                              disabled={submittingCwId === cw.id}
                              title="Resubmit your coursework"
                            >
                              {submittingCwId === cw.id ? "Submitting..." : "Resubmit"}
                            </button>
                          )}
                          {cw.alternate_link && (
                            <a
                              href={cw.alternate_link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="saas-outline-btn-sm"
                              style={{ padding: "6px 10px", fontSize: "0.8125rem", textDecoration: "none" }}
                              title="Open assignment in Google Classroom"
                            >
                              Open ↗
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
