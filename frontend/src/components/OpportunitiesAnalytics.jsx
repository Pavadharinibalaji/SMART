import { useState, useEffect } from "react";
import { getSmartCourses, getCourseOpportunitiesAnalytics, getCourseOpportunitiesParticipation } from "../api";

export default function OpportunitiesAnalytics({ initialCourseId = null }) {
  const [courses, setCourses] = useState([]);
  const [selectedCourseId, setSelectedCourseId] = useState(initialCourseId);
  const [analytics, setAnalytics] = useState(null);
  const [participations, setParticipations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Load teacher courses
  useEffect(() => {
    getSmartCourses()
      .then((res) => {
        const list = res.courses || [];
        setCourses(list);
        if (list.length > 0 && !selectedCourseId) {
          setSelectedCourseId(list[0].id);
        }
      })
      .catch((err) => {
        console.error("Failed to load courses:", err);
      });
  }, []);

  // Load analytics when selectedCourseId changes
  useEffect(() => {
    if (!selectedCourseId) {
      setAnalytics(null);
      setParticipations([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");

    Promise.all([
      getCourseOpportunitiesAnalytics(selectedCourseId),
      getCourseOpportunitiesParticipation(selectedCourseId),
    ])
      .then(([aData, pData]) => {
        setAnalytics(aData);
        setParticipations(pData || []);
      })
      .catch((err) => {
        setError(err.message || "Failed to load opportunity analytics for this course.");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [selectedCourseId]);

  const getStatusBadgeStyle = (status) => {
    switch (status) {
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
    <div className="opportunities-analytics-section" style={{ marginTop: "1.5rem" }}>
      {/* Course selection banner */}
      <div
        style={{
          background: "#fff",
          border: "1px solid #e2e8f0",
          borderRadius: "12px",
          padding: "1rem 1.25rem",
          marginBottom: "1.5rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.95rem", fontWeight: 700, color: "#1e1b4b" }}>
            Course Opportunities Analytics:
          </span>
          {courses.length === 0 ? (
            <span style={{ color: "#94a3b8", fontSize: "0.9rem" }}>No active courses found.</span>
          ) : (
            <select
              value={selectedCourseId || ""}
              onChange={(e) => setSelectedCourseId(Number(e.target.value))}
              style={{
                padding: "0.5rem 0.85rem",
                borderRadius: "8px",
                border: "1px solid #cbd5e1",
                background: "#f8fafc",
                fontSize: "0.9rem",
                fontWeight: 600,
                color: "#1e293b",
                minWidth: "220px",
              }}
            >
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.code})
                </option>
              ))}
            </select>
          )}
        </div>
        <span style={{ fontSize: "0.82rem", color: "#64748b" }}>
          🔒 Privacy Protected: Displaying opportunities linked to this course only.
        </span>
      </div>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", padding: "0.75rem 1rem", borderRadius: "8px", marginBottom: "1.25rem" }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: "center", padding: "3rem", color: "#64748b" }}>
          <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>⏳</div>
          <p>Calculating course opportunity participation analytics...</p>
        </div>
      ) : !analytics || analytics.total_tracked === 0 ? (
        <div style={{ textAlign: "center", padding: "3.5rem 2rem", background: "#f8fafc", borderRadius: "12px", border: "2px dashed #cbd5e1" }}>
          <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>🏆</div>
          <h3 style={{ margin: "0 0 0.5rem 0", color: "#334155" }}>No Tracked Student Opportunities Yet</h3>
          <p style={{ color: "#64748b", maxWidth: "480px", margin: "0 auto", fontSize: "0.9rem" }}>
            When enrolled students associate their competitions, hackathons, and internships with this course, participation trends and deadlines will appear here.
          </p>
        </div>
      ) : (
        <div>
          {/* Summary Metric Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", marginBottom: "1.5rem" }}>
            <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.25rem" }}>
              <span style={{ fontSize: "0.82rem", color: "#64748b", fontWeight: 600 }}>Total Opportunities Tracked</span>
              <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#4f46e5", marginTop: "0.3rem" }}>
                {analytics.total_tracked}
              </div>
            </div>

            <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.25rem" }}>
              <span style={{ fontSize: "0.82rem", color: "#64748b", fontWeight: 600 }}>Participating Students</span>
              <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#0284c7", marginTop: "0.3rem" }}>
                {analytics.participating_students_count}
              </div>
            </div>

            <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.25rem" }}>
              <span style={{ fontSize: "0.82rem", color: "#64748b", fontWeight: 600 }}>Registrations Completed</span>
              <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#16a34a", marginTop: "0.3rem" }}>
                {analytics.registrations_completed}
              </div>
            </div>

            <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.25rem" }}>
              <span style={{ fontSize: "0.82rem", color: "#64748b", fontWeight: 600 }}>Applications Submitted</span>
              <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "#7c3aed", marginTop: "0.3rem" }}>
                {analytics.applications_submitted}
              </div>
            </div>
          </div>

          {/* Breakdown Section: Categories & Statuses */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1.25rem", marginBottom: "1.5rem" }}>
            {/* Category Distribution */}
            <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.25rem" }}>
              <h4 style={{ margin: "0 0 1rem 0", fontSize: "0.95rem", fontWeight: 700, color: "#1e1b4b" }}>
                Opportunities by Category
              </h4>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                {Object.entries(analytics.category_distribution || {}).map(([cat, count]) => {
                  const percent = Math.round((count / analytics.total_tracked) * 100);
                  return (
                    <div key={cat}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem", marginBottom: "0.2rem", fontWeight: 600, color: "#334155" }}>
                        <span>{cat}</span>
                        <span>{count} ({percent}%)</span>
                      </div>
                      <div style={{ background: "#f1f5f9", height: "8px", borderRadius: "4px", overflow: "hidden" }}>
                        <div style={{ background: "#6366f1", height: "100%", width: `${percent}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Status Distribution */}
            <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.25rem" }}>
              <h4 style={{ margin: "0 0 1rem 0", fontSize: "0.95rem", fontWeight: 700, color: "#1e1b4b" }}>
                Participation Status Distribution
              </h4>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                {Object.entries(analytics.status_distribution || {}).map(([st, count]) => {
                  const percent = Math.round((count / analytics.total_tracked) * 100);
                  const badge = getStatusBadgeStyle(st);
                  return (
                    <div key={st}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem", marginBottom: "0.2rem", fontWeight: 600, color: "#334155" }}>
                        <span style={{ color: badge.color }}>{st}</span>
                        <span>{count} ({percent}%)</span>
                      </div>
                      <div style={{ background: "#f1f5f9", height: "8px", borderRadius: "4px", overflow: "hidden" }}>
                        <div style={{ background: badge.color, height: "100%", width: `${percent}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Student Participation Roster Table */}
          <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.25rem", overflowX: "auto" }}>
            <h4 style={{ margin: "0 0 1rem 0", fontSize: "1rem", fontWeight: 700, color: "#1e1b4b" }}>
              Enrolled Student Opportunities Roster
            </h4>
            {participations.length === 0 ? (
              <p style={{ color: "#64748b", fontSize: "0.88rem" }}>No participation records found for this course.</p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem", textAlign: "left" }}>
                <thead>
                  <tr style={{ background: "#f8fafc", borderBottom: "1px solid #cbd5e1", color: "#475569" }}>
                    <th style={{ padding: "0.6rem 0.75rem" }}>Student</th>
                    <th style={{ padding: "0.6rem 0.75rem" }}>Opportunity Title</th>
                    <th style={{ padding: "0.6rem 0.75rem" }}>Category</th>
                    <th style={{ padding: "0.6rem 0.75rem" }}>Status</th>
                    <th style={{ padding: "0.6rem 0.75rem" }}>Registration Deadline</th>
                    <th style={{ padding: "0.6rem 0.75rem" }}>Last Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {participations.map((p) => {
                    const badge = getStatusBadgeStyle(p.tracking_status);
                    return (
                      <tr key={p.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={{ padding: "0.65rem 0.75rem", fontWeight: 600, color: "#1e293b" }}>
                          <div>{p.student_name}</div>
                          <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{p.student_email}</div>
                        </td>
                        <td style={{ padding: "0.65rem 0.75rem", color: "#1e1b4b", fontWeight: 600 }}>
                          {p.title}
                          {p.registration_url && (
                            <a
                              href={p.registration_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ marginLeft: "0.35rem", textDecoration: "none" }}
                              title="External Link"
                            >
                              ↗
                            </a>
                          )}
                        </td>
                        <td style={{ padding: "0.65rem 0.75rem" }}>
                          <span style={{ background: "#f1f5f9", padding: "0.2rem 0.45rem", borderRadius: "4px", fontSize: "0.75rem", fontWeight: 600 }}>
                            {p.category}
                          </span>
                        </td>
                        <td style={{ padding: "0.65rem 0.75rem" }}>
                          <span
                            style={{
                              background: badge.bg,
                              color: badge.color,
                              border: `1px solid ${badge.border}`,
                              padding: "0.2rem 0.55rem",
                              borderRadius: "6px",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                            }}
                          >
                            {p.tracking_status}
                          </span>
                        </td>
                        <td style={{ padding: "0.65rem 0.75rem", color: p.is_overdue ? "#b91c1c" : "#334155" }}>
                          {p.registration_deadline ? (
                            <div>
                              <span>{p.registration_deadline.slice(0, 10)}</span>
                              {p.days_remaining !== null && (
                                <span style={{ marginLeft: "0.35rem", fontSize: "0.75rem", color: p.is_overdue ? "#b91c1c" : "#059669" }}>
                                  ({p.is_overdue ? "Overdue" : `${p.days_remaining}d left`})
                                </span>
                              )}
                            </div>
                          ) : (
                            <span style={{ color: "#94a3b8" }}>—</span>
                          )}
                        </td>
                        <td style={{ padding: "0.65rem 0.75rem", color: "#64748b", fontSize: "0.75rem" }}>
                          {p.updated_at ? new Date(p.updated_at).toLocaleDateString() : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
