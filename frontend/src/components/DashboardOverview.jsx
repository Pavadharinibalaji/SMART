import { useMemo } from "react";
import ConfidenceBadge from "./ConfidenceBadge";
import ReviewIndicator from "./ReviewIndicator";

export default function DashboardOverview({
  stats,
  tasks,
  user = null,
  courses = [],
  opportunities = [],
  materials = [],
  onNavigateToSection,
  onExportDeadlines,
  onSwitchToAnalyze,
  onUpdateTaskStatus,
  onMarkReviewed,
  onOpenEvidence,
  onOpenEdit,
  onTrackOpportunity,
  todayStr,
}) {
  // Filter upcoming active tasks sorted chronologically by due date
  const upcomingDeadlines = useMemo(() => {
    return tasks
      .filter((t) => {
        const status = (t.status || "pending").toLowerCase();
        if (["completed", "cancelled", "superseded", "dismissed"].includes(status)) {
          return false;
        }
        return Boolean(t.due_date);
      })
      .sort((a, b) => {
        if (!a.due_date) return 1;
        if (!b.due_date) return -1;
        return a.due_date.localeCompare(b.due_date);
      })
      .slice(0, 5);
  }, [tasks]);

  // Tasks requiring human review or having low/unassessed confidence
  const tasksNeedingReview = useMemo(() => {
    return tasks
      .filter((t) => {
        const status = (t.status || "pending").toLowerCase();
        if (["completed", "cancelled", "superseded", "dismissed"].includes(status)) {
          return false;
        }
        return Boolean(t.review_required) || t.confidence === "LOW";
      })
      .slice(0, 5);
  }, [tasks]);

  // Category breakdown percentages based on actual task data
  const categoryPercentages = useMemo(() => {
    const total = stats.total || 1;
    const cats = ["Assignment", "Exam", "Announcement", "Opportunity", "Event"];
    return cats.map((cat) => {
      const count = stats.categoryCounts[cat] || 0;
      const pct = Math.round((count / total) * 100);
      return { cat, count, pct };
    }).filter((item) => item.count > 0);
  }, [stats]);

  // Priority breakdown percentages based on actual task data
  const priorityPercentages = useMemo(() => {
    const total = stats.total || 1;
    const priorities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
    return priorities.map((pri) => {
      const count = stats.priorityCounts[pri] || 0;
      const pct = Math.round((count / total) * 100);
      return { pri, count, pct };
    }).filter((item) => item.count > 0);
  }, [stats]);

  return (
    <div className="saas-dashboard-canvas" aria-label="Academic Workspace Dashboard">
      {/* =================================================================== */}
      {/* SECTION 1: PAGE HEADER                                             */}
      {/* =================================================================== */}
      <div className="saas-page-header">
        <div className="header-text-block">
          <h2 className="saas-page-title">
            {user?.name ? `Welcome back, ${user.name}` : "Student Academic Workspace"}
          </h2>
          <p className="saas-page-subtitle">
            {user?.program ? `${user.program} · ` : ""}
            Track your coursework obligations, upcoming submission dates, and opportunities.
          </p>
        </div>
        <div className="header-action-block">
          <button
            type="button"
            className="saas-primary-btn"
            onClick={onSwitchToAnalyze}
            aria-label="Analyze new communication messages"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>Analyze Messages</span>
          </button>
        </div>
      </div>

      {/* =================================================================== */}
      {/* SECTION 2: KPI BENTO GRID (4 STATISTIC CARDS)                      */}
      {/* =================================================================== */}
      <div className="kpi-bento-grid" role="region" aria-label="Key Performance Indicators">
        {/* Card 1: Total Academic Tasks */}
        <button
          type="button"
          className="kpi-card kpi-purple"
          onClick={() => onNavigateToSection("all")}
          title="Click to view all saved academic tasks"
        >
          <div className="kpi-card-header">
            <span className="kpi-card-label">Total Academic Tasks</span>
            <div className="kpi-icon-wrapper" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
                <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
              </svg>
            </div>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-number">{stats.total}</span>
            <span className="kpi-meta">Across all categories</span>
          </div>
        </button>

        {/* Card 2: Upcoming Deadlines */}
        <button
          type="button"
          className="kpi-card kpi-blue"
          onClick={() => onNavigateToSection("upcoming")}
          title="Click to filter to upcoming tasks"
        >
          <div className="kpi-card-header">
            <span className="kpi-card-label">Upcoming Deadlines</span>
            <div className="kpi-icon-wrapper" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-number">{stats.upcoming}</span>
            <span className="kpi-meta">{stats.dueToday > 0 ? `${stats.dueToday} due today` : "Active obligations"}</span>
          </div>
        </button>

        {/* Card 3: Needs Review */}
        <button
          type="button"
          className="kpi-card kpi-orange"
          onClick={() => onNavigateToSection("needs_review")}
          title="Click to view tasks requiring review"
        >
          <div className="kpi-card-header">
            <span className="kpi-card-label">Needs Review</span>
            <div className="kpi-icon-wrapper" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-number">{stats.needsReview}</span>
            <span className="kpi-meta">Requires human verification</span>
          </div>
        </button>

        {/* Card 4: Completed Tasks */}
        <button
          type="button"
          className="kpi-card kpi-green"
          onClick={() => onNavigateToSection("completed_archived")}
          title="Click to view completed tasks"
        >
          <div className="kpi-card-header">
            <span className="kpi-card-label">Completed Tasks</span>
            <div className="kpi-icon-wrapper" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
            </div>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-number">{stats.completed}</span>
            <span className="kpi-meta">{stats.total > 0 ? `${Math.round((stats.completed / stats.total) * 100)}% resolution rate` : "No completed tasks"}</span>
          </div>
        </button>
      </div>

      {/* =================================================================== */}
      {/* SECTION 3: MAIN VISUALIZATION (TASK WORKLOAD OVERVIEW)             */}
      {/* =================================================================== */}
      <div className="saas-card chart-visualization-card">
        <div className="card-header-row">
          <div>
            <h3 className="card-section-title">Academic Task Overview</h3>
            <p className="card-section-desc">Distribution of workload across categories and authoritative priorities</p>
          </div>
          {stats.total > 0 && onExportDeadlines && (
            <button
              type="button"
              className="chart-action-link"
              onClick={onExportDeadlines}
            >
              Export Calendar ({stats.deadlines}) →
            </button>
          )}
        </div>

        {stats.total > 0 ? (
          <div className="chart-content-grid">
            {/* Category Breakdown Bar Visualization */}
            <div className="chart-column">
              <div className="chart-column-header">
                <span className="chart-col-title">By Category</span>
                <span className="chart-col-subtitle">{stats.total} total items</span>
              </div>

              <div className="modern-progress-bar" role="progressbar" aria-label="Category distribution">
                {categoryPercentages.map((item) => (
                  <div
                    key={item.cat}
                    className={`bar-seg bar-${item.cat.toLowerCase()}`}
                    style={{ width: `${item.pct}%` }}
                    title={`${item.cat}: ${item.count} (${item.pct}%)`}
                  />
                ))}
              </div>

              <div className="chart-legend-grid">
                {categoryPercentages.map((item) => (
                  <div key={item.cat} className="chart-legend-item">
                    <span className={`legend-bullet bullet-${item.cat.toLowerCase()}`} />
                    <span className="legend-name">{item.cat}</span>
                    <span className="legend-value">{item.count} <span className="legend-pct">({item.pct}%)</span></span>
                  </div>
                ))}
              </div>
            </div>

            {/* Priority Breakdown Bar Visualization */}
            <div className="chart-column">
              <div className="chart-column-header">
                <span className="chart-col-title">By Priority</span>
                <span className="chart-col-subtitle">Authoritative severity</span>
              </div>

              <div className="modern-progress-bar" role="progressbar" aria-label="Priority distribution">
                {priorityPercentages.map((item) => (
                  <div
                    key={item.pri}
                    className={`bar-seg bar-pri-${item.pri.toLowerCase()}`}
                    style={{ width: `${item.pct}%` }}
                    title={`${item.pri}: ${item.count} (${item.pct}%)`}
                  />
                ))}
              </div>

              <div className="chart-legend-grid">
                {priorityPercentages.map((item) => (
                  <div key={item.pri} className="chart-legend-item">
                    <span className={`legend-bullet bullet-pri-${item.pri.toLowerCase()}`} />
                    <span className="legend-name">{item.pri}</span>
                    <span className="legend-value">{item.count} <span className="legend-pct">({item.pct}%)</span></span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="chart-empty-state">
            <div className="empty-state-icon" aria-hidden="true">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
            </div>
            <h4>No Academic Data Yet</h4>
            <p>Import your first communication export or manual note to visualize your academic workload.</p>
            <button
              type="button"
              className="saas-secondary-btn"
              onClick={onSwitchToAnalyze}
            >
              Start Analysis →
            </button>
          </div>
        )}
      </div>

      {/* =================================================================== */}
      {/* SECTIONS 4 & 5: DUAL WIDGET ROW (UPCOMING DEADLINES & NEEDS REVIEW) */}
      {/* =================================================================== */}
      <div className="dashboard-widgets-grid">
        {/* Section 4: Upcoming Tasks Widget */}
        <div className="saas-card widget-card">
          <div className="card-header-row">
            <div>
              <h3 className="card-section-title">Upcoming Deadlines</h3>
              <p className="card-section-desc">Earliest scheduled deliverables</p>
            </div>
            <button
              type="button"
              className="widget-view-all-link"
              onClick={() => onNavigateToSection("upcoming")}
            >
              View All →
            </button>
          </div>

          <div className="widget-content">
            {upcomingDeadlines.length > 0 ? (
              <div className="deadline-rows-list">
                {upcomingDeadlines.map((t) => {
                  const isOverdue = Boolean(t.due_date) && Boolean(todayStr) && t.due_date < todayStr;
                  const isDueToday = Boolean(t.due_date) && Boolean(todayStr) && t.due_date === todayStr;

                  return (
                    <div key={t.id} className="deadline-row-item">
                      <div className="deadline-row-main">
                        <div className="deadline-row-badges">
                          <span className={`category-tag tag-${(t.category || "announcement").toLowerCase()}`}>
                            {t.category}
                          </span>
                          {t.priority && (
                            <span className={`priority-tag pri-${t.priority.toLowerCase()}`}>
                              {t.priority}
                            </span>
                          )}
                          {isOverdue && <span className="status-badge-urgent">Overdue</span>}
                          {isDueToday && <span className="status-badge-today">Due Today</span>}
                        </div>
                        <h4 className="deadline-row-title">{t.title}</h4>
                      </div>

                      <div className="deadline-row-side">
                        <div className="deadline-row-date">
                          <span className="date-label">Due</span>
                          <span className="date-val">{t.due_date}</span>
                          {t.deadline_time && <span className="time-val">{t.deadline_time}</span>}
                        </div>

                        <div className="deadline-row-actions">
                          <button
                            type="button"
                            className="mini-action-btn"
                            onClick={() => onUpdateTaskStatus(t.id, "completed")}
                            title="Mark as completed"
                            aria-label={`Mark ${t.title} completed`}
                          >
                            ✓
                          </button>
                          {onOpenEdit && (
                            <button
                              type="button"
                              className="mini-action-btn"
                              onClick={() => onOpenEdit(t)}
                              title="Edit task details"
                              aria-label={`Edit ${t.title}`}
                            >
                              ✏️
                            </button>
                          )}
                          <button
                            type="button"
                            className="mini-action-btn"
                            onClick={() => onOpenEvidence(t)}
                            title="Inspect source evidence"
                            aria-label={`Inspect evidence for ${t.title}`}
                          >
                            🔍
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="widget-empty-state">
                <span className="empty-glyph" aria-hidden="true">✓</span>
                <p>No upcoming deadlines scheduled.</p>
              </div>
            )}
          </div>
        </div>

        {/* Section 5: Needs Review Widget */}
        <div className="saas-card widget-card">
          <div className="card-header-row">
            <div>
              <h3 className="card-section-title">Needs Your Attention</h3>
              <p className="card-section-desc">Ambiguous dates or low extraction confidence</p>
            </div>
            <button
              type="button"
              className="widget-view-all-link"
              onClick={() => onNavigateToSection("needs_review")}
            >
              View All →
            </button>
          </div>

          <div className="widget-content">
            {tasksNeedingReview.length > 0 ? (
              <div className="review-rows-list">
                {tasksNeedingReview.map((t) => (
                  <div key={t.id} className="review-row-item">
                    <div className="review-row-main">
                      <div className="review-row-badges">
                        <ConfidenceBadge
                          confidence={t.confidence}
                          reasons={t.confidence_reasons}
                        />
                        <ReviewIndicator
                          reviewRequired={t.review_required}
                          confidence={t.confidence}
                          reasons={t.review_reasons && t.review_reasons.length > 0 ? t.review_reasons : t.confidence_reasons}
                        />
                      </div>
                      <h4 className="review-row-title">{t.title}</h4>
                      {t.review_reasons && t.review_reasons.length > 0 && (
                        <p className="review-row-reason">
                          {t.review_reasons[0]}
                        </p>
                      )}
                    </div>

                    <div className="review-row-action" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      {onMarkReviewed && (
                        <button
                          type="button"
                          className="saas-primary-btn-sm"
                          onClick={() => onMarkReviewed(t.id, "pending")}
                          title="Confirm and mark pending"
                          aria-label={`Confirm and approve ${t.title}`}
                        >
                          ✓ Approve
                        </button>
                      )}
                      <button
                        type="button"
                        className="saas-outline-btn-sm"
                        onClick={() => onOpenEvidence(t)}
                      >
                        Inspect Evidence
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="widget-empty-state widget-empty-cleared">
                <span className="empty-glyph" aria-hidden="true">✓</span>
                <div>
                  <strong>All clear!</strong>
                  <p>Zero active items currently pending human verification.</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* =================================================================== */}
      {/* SECTION 6.5: MY ENROLLED COURSES & STUDY RESOURCES                 */}
      {/* =================================================================== */}
      <div className="dashboard-bottom-grid" role="region" aria-label="Course and Study Resources">
        {/* Enrolled Courses Card */}
        <div className="saas-card-widget">
          <div className="widget-header">
            <div>
              <h3 className="widget-title">Enrolled Courses</h3>
              <p className="widget-subtitle">Academic units tracked in Google Classroom</p>
            </div>
            <span className="badge-outline">{courses.length} Active</span>
          </div>
          <div className="widget-content">
            {courses.length > 0 ? (
              <div className="mini-courses-list">
                {courses.slice(0, 3).map((c) => (
                  <div key={c.id} className="mini-course-row">
                    <div className="mini-course-icon" aria-hidden="true">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                      </svg>
                    </div>
                    <div className="mini-course-info">
                      <span className="mini-course-title">{c.name}</span>
                      <span className="mini-course-sub">{c.section || "Semester Course"} · {c.teacher_email || "Instructor"}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="widget-empty-state">
                <p>No active courses indexed. Sync Google Classroom to populate.</p>
              </div>
            )}
          </div>
        </div>

        {/* Recent Study Materials Card */}
        <div className="saas-card-widget">
          <div className="widget-header">
            <div>
              <h3 className="widget-title">Recent Study Materials</h3>
              <p className="widget-subtitle">Attachments from Gmail and Classroom files</p>
            </div>
            <span className="badge-outline">{materials.length} Items</span>
          </div>
          <div className="widget-content">
            {materials.length > 0 ? (
              <div className="mini-materials-list">
                {materials.slice(0, 3).map((m) => (
                  <div key={m.id} className="mini-material-row">
                    <span className="mini-mat-icon" aria-hidden="true">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                        <line x1="16" y1="13" x2="8" y2="13" />
                        <line x1="16" y1="17" x2="8" y2="17" />
                        <polyline points="10 9 9 9 8 9" />
                      </svg>
                    </span>
                    <div className="mini-mat-info">
                      <span className="mini-mat-title">{m.title}</span>
                      <span className="mini-mat-sub">{m.course_name || "Academic File"}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="widget-empty-state">
                <p>No study materials indexed yet.</p>
              </div>
            )}
          </div>
        </div>

        {/* Competition Opportunities Card */}
        {opportunities.length > 0 && (
          <div className="saas-card-widget" style={{ gridColumn: "1 / -1" }}>
            <div className="widget-header">
              <div>
                <h3 className="widget-title">Discovered Competitions &amp; Opportunities</h3>
                <p className="widget-subtitle">Active hackathons, contests, and academic challenges</p>
              </div>
              <span className="badge-outline">{opportunities.length} Total</span>
            </div>
            <div className="widget-content">
              <div className="mini-courses-list">
                {opportunities.slice(0, 2).map((opp) => (
                  <div key={opp.id} className="mini-course-row">
                    <div className="mini-course-icon" aria-hidden="true">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="8" r="7" />
                        <polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88" />
                      </svg>
                    </div>
                    <div className="mini-course-info" style={{ flex: 1 }}>
                      <span className="mini-course-title">{opp.name}</span>
                      <span className="mini-course-sub">{opp.organizer || "University"} · Deadline: {opp.registration_deadline || "Open"}</span>
                    </div>
                    {onTrackOpportunity && (
                      <button
                        type="button"
                        onClick={() =>
                          onTrackOpportunity({
                            opportunity_id: opp.id,
                            title: opp.name,
                            organizer: opp.organizer,
                            category: opp.category || "Competition",
                            description: opp.description,
                            registration_url: opp.registration_url,
                            registration_deadline: opp.registration_deadline,
                            event_date: opp.event_date,
                            source_platform: opp.source_type || "gmail",
                            source_reference: opp.evidence_text,
                            isNewTracking: true,
                          })
                        }
                        style={{
                          background: "#ede9fe",
                          color: "#5b21b6",
                          border: "1px solid #c4b5fd",
                          padding: "0.3rem 0.65rem",
                          borderRadius: "6px",
                          fontSize: "0.76rem",
                          fontWeight: 700,
                          cursor: "pointer",
                          whiteSpace: "nowrap",
                        }}
                      >
                        🎯 Track
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* =================================================================== */}
      {/* SECTION 7: QUICK ACTION BANNER                                     */}
      {/* =================================================================== */}
      <div className="saas-quick-action-banner" role="region" aria-label="Stay ahead banner">
        <div className="banner-visual-mark" aria-hidden="true">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2v4" />
            <path d="M12 18v4" />
            <path d="M4.93 4.93l2.83 2.83" />
            <path d="M16.24 16.24l2.83 2.83" />
            <path d="M2 12h4" />
            <path d="M18 12h4" />
            <path d="M4.93 19.07l2.83-2.83" />
            <path d="M16.24 7.76l2.83-2.83" />
          </svg>
        </div>
        <div className="banner-text-content">
          <h3 className="banner-heading">Stay ahead of your academic deadlines.</h3>
          <p className="banner-subtext">
            Analyze your latest academic messages and identify important tasks with deterministic, verifiable extraction.
          </p>
        </div>
        <div className="banner-action-wrapper">
          <button
            type="button"
            className="banner-primary-btn"
            onClick={onSwitchToAnalyze}
          >
            Analyze Messages →
          </button>
        </div>
      </div>
    </div>
  );
}
