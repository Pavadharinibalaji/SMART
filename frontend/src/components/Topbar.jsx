export default function Topbar({
  activeTab,
  onToggleSidebar,
  searchQuery = "",
  onSearchChange,
  onExportCalendar,
  onNavigateToAnalyze,
  deadlineCount = 0,
  user = null,
  googleAccount = null,
  onConnectGoogle,
  onDisconnectGoogle,
  onLogout,
}) {
  const userRole = user?.role || "student";
  const isTeacher = userRole === "teacher";

  const getPageTitle = () => {
    switch (activeTab) {
      case "tasks":
        return {
          title: "My Academic Tasks",
          subtitle: "Manage, filter, and track verified coursework obligations",
        };
      case "analyze":
        return {
          title: "Analyze Messages",
          subtitle: "Extract academic intelligence from communication sources",
        };
      case "opportunities":
        return {
          title: "Academic Competitions & Opportunities",
          subtitle: "Discover hackathons, internships, and track your registration progress",
        };
      case "classroom":
        return {
          title: "Google Classroom & Coursework",
          subtitle: "View enrolled courses, assignment submissions, deadlines, and grades",
        };
      case "materials":
        return {
          title: "Study Materials Repository",
          subtitle: "Unified index of course slides, syllabus, and Gmail academic attachments",
        };
      case "teacher":
        return {
          title: "Teacher Progress & Activity Overview",
          subtitle: "Authorized course oversight, assignment completion, and student competition engagement",
        };
      case "dashboard":
      default:
        return {
          title: isTeacher ? "Instructor Dashboard" : "Academic Dashboard",
          subtitle: isTeacher
            ? "Overview of your assigned courses, submission progress, and student engagement"
            : "Overview of your deadlines, priority workload, and reviews",
        };
    }
  };

  const { title, subtitle } = getPageTitle();

  return (
    <header className="saas-topbar" aria-label="Top utility bar">
      {/* Left: Mobile Toggle & Page Context */}
      <div className="topbar-left">
        <button
          type="button"
          className="topbar-menu-btn"
          onClick={onToggleSidebar}
          aria-label="Toggle navigation menu"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>

        <div className="topbar-page-context">
          <h1 className="topbar-title">{title}</h1>
          <span className="topbar-subtitle">{subtitle}</span>
        </div>
      </div>

      {/* Center & Right: Search, Actions, Profile */}
      <div className="topbar-right">
        {/* Global Task Search */}
        <div className="topbar-search-box">
          <svg className="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="search"
            className="topbar-search-input"
            placeholder="Search academic tasks..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label="Search academic tasks"
          />
        </div>

        {/* Authenticated Role Tag */}
        <div className={`topbar-role-badge role-${userRole}`}>
          <span className="role-dot" />
          <span>{isTeacher ? "Teacher Account" : "Student Account"}</span>
        </div>

        {/* Google Connection Pill */}
        {googleAccount?.connected ? (
          <div className="topbar-google-pill connected" title={`Connected as ${googleAccount.email} (${googleAccount.is_demo ? "Demo Mode" : "Live Account"})`}>
            <span className="google-dot" aria-hidden="true" />
            <span className="google-pill-text">
              {googleAccount.is_demo ? "Demo Sync Active" : "Google Live"}
            </span>
            <button
              type="button"
              className="google-pill-disconnect"
              onClick={onDisconnectGoogle}
              title="Disconnect Google Account"
              aria-label="Disconnect Google Account"
            >
              ✕
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="topbar-btn topbar-btn-google"
            onClick={onConnectGoogle}
            title="Connect Google Account for Gmail and Classroom"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z" />
            </svg>
            <span>Connect Google</span>
          </button>
        )}

        {/* Quick Export Calendar Button */}
        {onExportCalendar && !isTeacher && (
          <button
            type="button"
            className="topbar-btn topbar-btn-export"
            onClick={onExportCalendar}
            title="Download confirmed academic deadlines as .ics file"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
            <span>Export .ics</span>
            {deadlineCount > 0 && (
              <span className="topbar-badge">{deadlineCount}</span>
            )}
          </button>
        )}

        {/* Quick Ingest Button */}
        {activeTab !== "analyze" && onNavigateToAnalyze && (
          <button
            type="button"
            className="topbar-btn topbar-btn-primary"
            onClick={onNavigateToAnalyze}
            aria-label="Analyze new chat or message"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>Analyze Messages</span>
          </button>
        )}

        {/* User Mini Profile Avatar & Logout */}
        <div className="topbar-user-cluster">
          <div className="topbar-avatar" title={`Signed in as ${user?.name || "User"}`}>
            <span>{user?.name ? user.name.slice(0, 2).toUpperCase() : (isTeacher ? "EV" : "AM")}</span>
            <span className="avatar-status-dot" aria-hidden="true" />
          </div>
          {onLogout && (
            <button
              type="button"
              className="topbar-logout-btn"
              onClick={onLogout}
              title="Sign Out"
              aria-label="Sign out of your session"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
              <span>Sign Out</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
