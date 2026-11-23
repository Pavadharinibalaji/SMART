export default function TeacherDashboard({
  coursesOverview = [],
  opportunitiesOverview = { status_counts: {}, participations: [] },
  user = null,
  loading = false,
  onRefresh,
}) {
  const participations = opportunitiesOverview.participations || [];
  const statusCounts = opportunitiesOverview.status_counts || {};

  const totalAssignments = coursesOverview.reduce((acc, c) => acc + (c.total_assignments || 0), 0);
  const totalSubmissions = coursesOverview.reduce((acc, c) => acc + (c.total_submissions || 0), 0);
  const pendingTurnedIn = coursesOverview.reduce((acc, c) => acc + (c.turned_in_count || 0), 0);
  const totalGraded = coursesOverview.reduce((acc, c) => acc + (c.graded_count || 0), 0);

  return (
    <div className="teacher-dashboard-view" aria-label="Authorized Teacher Dashboard">
      {/* Page Header */}
      <div className="saas-page-header">
        <div className="header-text-block">
          <h2 className="saas-page-title">
            {user?.name ? `Faculty Portal · ${user.name}` : "Teacher Overview"}
          </h2>
          <p className="saas-page-subtitle">
            {user?.department ? `${user.department} · ` : ""}
            Supervise assigned courses, track student assignment submissions, and review competition engagement.
          </p>
        </div>
        <div className="header-action-block">
          {onRefresh && (
            <button
              type="button"
              className="saas-secondary-btn"
              onClick={onRefresh}
              disabled={loading}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              <span>Refresh Analytics</span>
            </button>
          )}
        </div>
      </div>

      {/* Security & Access Restriction Callout Banner */}
      <div className="teacher-security-callout" role="note">
        <span className="security-icon" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
        </span>
        <div>
          <strong>Role-Based Access Control Enforced</strong>
          <p>
            You only have access to courses you explicitly teach and authorized academic progress records.
            Student personal Gmail inboxes, unrelated private communications, and courses of other faculty remain strictly private.
          </p>
        </div>
      </div>

      {/* 4 Professional Teacher KPI Cards */}
      <div className="kpi-bento-grid" role="region" aria-label="Faculty Key Performance Indicators">
        <div className="kpi-card kpi-purple">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Assigned Courses</span>
            <div className="kpi-icon-wrapper" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
            </div>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-number">{coursesOverview.length}</span>
            <span className="kpi-meta">Active Course Sections</span>
          </div>
        </div>

        <div className="kpi-card kpi-blue">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Active Coursework</span>
            <div className="kpi-icon-wrapper" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
            </div>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-number">{totalAssignments}</span>
            <span className="kpi-meta">Assignments &amp; Labs</span>
          </div>
        </div>

        <div className="kpi-card kpi-orange">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Pending Grading</span>
            <div className="kpi-icon-wrapper" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
            </div>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-number">{pendingTurnedIn}</span>
            <span className="kpi-meta">Turned In by Students</span>
          </div>
        </div>

        <div className="kpi-card kpi-green">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Graded Submissions</span>
            <div className="kpi-icon-wrapper" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
            </div>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-number">{totalGraded}</span>
            <span className="kpi-meta">Out of {totalSubmissions} total</span>
          </div>
        </div>
      </div>

      {/* Section 1: Courses I Teach & Submission Progress */}
      <div className="saas-card" style={{ marginBottom: 24, marginTop: 24 }}>
        <div className="card-header-row">
          <div>
            <h3 className="card-section-title">Courses I Teach &amp; Submission Progress</h3>
            <p className="card-section-desc">Course-level assignment completion and grading queue</p>
          </div>
        </div>

        {coursesOverview.length === 0 ? (
          <div className="chart-empty-state">
            <div className="empty-state-icon" aria-hidden="true">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
            </div>
            <p>No courses found where you are registered as the course instructor.</p>
          </div>
        ) : (
          <div className="teacher-courses-grid">
            {coursesOverview.map((c) => (
              <div key={c.course_id} className="teacher-course-card">
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span className="course-card-badge">{c.section || "Active Class"}</span>
                  {c.is_demo === 1 && <span className="demo-data-badge">Demo</span>}
                </div>
                <h4 className="teacher-course-title">{c.course_name}</h4>

                <div className="teacher-course-stats">
                  <div className="tstat-box">
                    <span className="tstat-lbl">Assignments</span>
                    <strong className="tstat-val">{c.total_assignments}</strong>
                  </div>
                  <div className="tstat-box">
                    <span className="tstat-lbl">Submissions</span>
                    <strong className="tstat-val">{c.total_submissions}</strong>
                  </div>
                  <div className="tstat-box">
                    <span className="tstat-lbl">Turned In</span>
                    <strong className="tstat-val text-warning">{c.turned_in_count}</strong>
                  </div>
                  <div className="tstat-box">
                    <span className="tstat-lbl">Graded</span>
                    <strong className="tstat-val text-success">{c.graded_count}</strong>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Section 2: Student Competition Engagement Overview */}
      <div className="saas-card">
        <div className="card-header-row">
          <div>
            <h3 className="card-section-title">Student Competition &amp; Opportunity Participation</h3>
            <p className="card-section-desc">Track which students are registered or interested in academic hackathons and contests</p>
          </div>
        </div>

        {/* Aggregate KPI counters */}
        <div className="teacher-engagement-kpis">
          <div className="tek-item">
            <span className="tek-label">Total Student Engagements</span>
            <span className="tek-val">{opportunitiesOverview.total_engagements || 0}</span>
          </div>
          <div className="tek-item">
            <span className="tek-label">Confirmed Registered</span>
            <span className="tek-val text-success">{statusCounts["registered"] || 0}</span>
          </div>
          <div className="tek-item">
            <span className="tek-label">Interested / Preparing</span>
            <span className="tek-val text-warning">{statusCounts["interested"] || 0}</span>
          </div>
          <div className="tek-item">
            <span className="tek-label">Attended / Competed</span>
            <span className="tek-val text-purple">{statusCounts["attended"] || 0}</span>
          </div>
        </div>

        {participations.length === 0 ? (
          <div className="chart-empty-state">
            <p>No student opportunity engagement recorded yet.</p>
          </div>
        ) : (
          <div className="coursework-table-wrapper" style={{ marginTop: 16 }}>
            <table className="saas-table">
              <thead>
                <tr>
                  <th>Student Identity</th>
                  <th>Competition / Opportunity</th>
                  <th>Deadline</th>
                  <th>Participation Status</th>
                  <th>Notes / Evidence</th>
                </tr>
              </thead>
              <tbody>
                {participations.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong className="table-title">{p.student_id}</strong>
                    </td>
                    <td>
                      <span className="table-title">{p.opportunity_name}</span>
                      {p.organizer && <p className="table-desc">{p.organizer}</p>}
                    </td>
                    <td>
                      <span className="date-val">{p.registration_deadline || "No deadline"}</span>
                    </td>
                    <td>
                      <span className={`status-badge-opp status-opp-${p.status}`}>
                        {p.status.replace(/_/g, " ").toUpperCase()}
                      </span>
                    </td>
                    <td>
                      <span className="table-desc">{p.evidence_notes || "Self-reported"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
