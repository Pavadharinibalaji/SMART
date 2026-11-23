import { useState, useEffect } from "react";
import {
  getSmartCourses,
  getCourseAnalytics,
  getStudentAnalytics,
} from "../api";

export default function AnalyticsView({ user }) {
  const isTeacher = user?.role === "teacher";
  const [courses, setCourses] = useState([]);
  const [selectedCourseId, setSelectedCourseId] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadInitial() {
      try {
        setLoading(true);
        setError("");
        if (isTeacher) {
          const coursesRes = await getSmartCourses();
          const list = coursesRes.courses || [];
          setCourses(list);
          if (list.length > 0) {
            setSelectedCourseId(list[0].id);
          }
        } else {
          const studentRes = await getStudentAnalytics();
          setAnalyticsData(studentRes);
        }
      } catch (err) {
        setError(err.message || "Failed to load analytics");
      } finally {
        setLoading(false);
      }
    }
    loadInitial();
  }, [isTeacher]);

  useEffect(() => {
    if (isTeacher && selectedCourseId) {
      async function loadCourseAnalytics() {
        try {
          setLoading(true);
          setError("");
          const data = await getCourseAnalytics(selectedCourseId);
          setAnalyticsData(data);
        } catch (err) {
          setError(err.message || "Failed to load course metrics");
        } finally {
          setLoading(false);
        }
      }
      loadCourseAnalytics();
    }
  }, [isTeacher, selectedCourseId]);

  return (
    <div style={{ padding: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0, color: "#1e1b4b" }}>
            {isTeacher ? "Academic Engagement Analytics" : "My Academic Progress & Activity"}
          </h1>
          <p style={{ color: "#64748b", margin: "0.25rem 0 0 0" }}>
            {isTeacher
              ? "Comprehensive real-time student participation, announcement read rates, poll turnouts, and activity trends."
              : "Overview of your course enrollments, task completions, and active participation."}
          </p>
        </div>

        {isTeacher && courses.length > 0 && (
          <select
            value={selectedCourseId || ""}
            onChange={(e) => setSelectedCourseId(e.target.value)}
            style={{ padding: "0.55rem 0.9rem", borderRadius: "8px", border: "1px solid #cbd5e1", background: "#fff", fontWeight: 600, color: "#334155" }}
          >
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} - {c.title}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", padding: "0.75rem 1rem", borderRadius: "8px", marginBottom: "1.25rem" }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: "center", padding: "3rem", color: "#64748b" }}>Calculating engagement metrics...</div>
      ) : !analyticsData ? (
        <div style={{ textAlign: "center", padding: "4rem 2rem", background: "#f8fafc", borderRadius: "12px", border: "2px dashed #e2e8f0" }}>
          <h3 style={{ color: "#334155", margin: 0 }}>No Analytics Data Available</h3>
        </div>
      ) : isTeacher ? (
        // Teacher Dashboard Analytics
        <div>
          {/* Key Metric KPI Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1.25rem", marginBottom: "1.5rem" }}>
            <div style={{ background: "#fff", padding: "1.25rem", borderRadius: "10px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
              <div style={{ fontSize: "0.85rem", color: "#64748b", fontWeight: 600 }}>Enrolled Students</div>
              <div style={{ fontSize: "2rem", fontWeight: 800, color: "#1e1b4b", marginTop: "0.3rem" }}>
                {analyticsData.total_enrolled ?? analyticsData.total_students ?? 0}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#10b981", marginTop: "0.2rem" }}>
                {analyticsData.active_students ?? analyticsData.active_students_7d ?? 0} active students
              </div>
            </div>

            <div style={{ background: "#fff", padding: "1.25rem", borderRadius: "10px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
              <div style={{ fontSize: "0.85rem", color: "#64748b", fontWeight: 600 }}>Announcement Read Rate</div>
              <div style={{ fontSize: "2rem", fontWeight: 800, color: "#6366f1", marginTop: "0.3rem" }}>
                {analyticsData.announcement_read_rate ?? 0}%
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.2rem" }}>
                Across {analyticsData.total_announcements ?? analyticsData.announcements_count ?? 0} announcements
              </div>
            </div>

            <div style={{ background: "#fff", padding: "1.25rem", borderRadius: "10px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
              <div style={{ fontSize: "0.85rem", color: "#64748b", fontWeight: 600 }}>Poll Participation Rate</div>
              <div style={{ fontSize: "2rem", fontWeight: 800, color: "#ec4899", marginTop: "0.3rem" }}>
                {analyticsData.poll_participation_rate ?? 0}%
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.2rem" }}>
                Across {analyticsData.total_polls ?? analyticsData.polls_count ?? 0} class polls
              </div>
            </div>

            <div style={{ background: "#fff", padding: "1.25rem", borderRadius: "10px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
              <div style={{ fontSize: "0.85rem", color: "#64748b", fontWeight: 600 }}>Course Discussion Volume</div>
              <div style={{ fontSize: "2rem", fontWeight: 800, color: "#059669", marginTop: "0.3rem" }}>
                {analyticsData.total_messages ?? 0}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.2rem" }}>
                {analyticsData.active_chatters ?? 0} active participants
              </div>
            </div>
          </div>

          {/* 7-Day Activity Trend Bar */}
          <div style={{ background: "#fff", padding: "1.5rem", borderRadius: "10px", border: "1px solid #e2e8f0", marginBottom: "1.5rem" }}>
            <h3 style={{ margin: "0 0 1rem 0", fontSize: "1.1rem", color: "#0f172a" }}>Recent 7-Day Course Activity</h3>
            {(analyticsData.activity_timeline || analyticsData.activity_by_day) && (analyticsData.activity_timeline || analyticsData.activity_by_day).length > 0 ? (
              <div style={{ display: "flex", gap: "1rem", alignItems: "flex-end", height: "180px", paddingTop: "1rem" }}>
                {(analyticsData.activity_timeline || analyticsData.activity_by_day).map((day) => {
                  const timelineArr = analyticsData.activity_timeline || analyticsData.activity_by_day;
                  const maxMsg = Math.max(...timelineArr.map((d) => d.count ?? d.messages ?? 0), 5);
                  const countVal = day.count ?? day.messages ?? 0;
                  const heightPct = Math.round((countVal / maxMsg) * 100);
                  return (
                    <div key={day.date} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", height: "100%", justifyContent: "flex-end" }}>
                      <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "#4f46e5", marginBottom: "0.3rem" }}>
                        {countVal}
                      </span>
                      <div
                        style={{
                          width: "100%",
                          height: `${Math.max(heightPct, 6)}%`,
                          background: "#818cf8",
                          borderRadius: "4px 4px 0 0",
                          transition: "height 0.3s ease",
                        }}
                      />
                      <span style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.5rem" }}>
                        {day.date ? day.date.slice(5) : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div style={{ color: "#94a3b8", textAlign: "center", padding: "2rem" }}>No recent activity records.</div>
            )}
          </div>
        </div>
      ) : (
        // Student Analytics
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "1.25rem" }}>
          <div style={{ background: "#fff", padding: "1.5rem", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
            <div style={{ fontSize: "0.85rem", color: "#64748b", fontWeight: 600 }}>Enrolled Courses</div>
            <div style={{ fontSize: "2.25rem", fontWeight: 800, color: "#4338ca", marginTop: "0.3rem" }}>
              {analyticsData.enrolled_courses_count ?? 0}
            </div>
          </div>
          <div style={{ background: "#fff", padding: "1.5rem", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
            <div style={{ fontSize: "0.85rem", color: "#64748b", fontWeight: 600 }}>Active Tasks</div>
            <div style={{ fontSize: "2.25rem", fontWeight: 800, color: "#0891b2", marginTop: "0.3rem" }}>
              {(analyticsData.tasks_completed ?? analyticsData.completed_tasks ?? 0) + (analyticsData.tasks_pending ?? 0)}
            </div>
            <div style={{ fontSize: "0.8rem", color: "#16a34a", marginTop: "0.2rem" }}>
              {analyticsData.tasks_completed ?? analyticsData.completed_tasks ?? 0} completed
            </div>
          </div>
          <div style={{ background: "#fff", padding: "1.5rem", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
            <div style={{ fontSize: "0.85rem", color: "#64748b", fontWeight: 600 }}>Polls Participated</div>
            <div style={{ fontSize: "2.25rem", fontWeight: 800, color: "#d97706", marginTop: "0.3rem" }}>
              {analyticsData.poll_votes_count ?? analyticsData.participated_polls_count ?? 0}
            </div>
          </div>
          <div style={{ background: "#fff", padding: "1.5rem", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
            <div style={{ fontSize: "0.85rem", color: "#64748b", fontWeight: 600 }}>Messages Sent</div>
            <div style={{ fontSize: "2.25rem", fontWeight: 800, color: "#7c3aed", marginTop: "0.3rem" }}>
              {analyticsData.messages_sent ?? analyticsData.messages_sent_count ?? 0}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
