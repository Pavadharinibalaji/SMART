export default function Sidebar({
  activeTab,
  onSelectTab,
  tasksCount = 0,
  candidatesCount = 0,
  opportunitiesCount = 0,
  materialsCount = 0,
  unreadMessagesCount = 0,
  unreadNotificationsCount = 0,
  user = null,
  googleAccount = null,
  onSyncGmail,
  onSyncClassroom,
  onLogout,
  isOpen = false,
  onClose,
}) {
  const userRole = user?.role || "student";
  const isTeacher = userRole === "teacher";

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          className="sidebar-backdrop"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside className={`saas-sidebar ${isOpen ? "sidebar-open" : ""}`} aria-label="Main Navigation">
        {/* Brand Header */}
        <div className="sidebar-brand">
          <div className="brand-logo-mark" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <div className="brand-info">
            <span className="brand-title">SMART</span>
            <span className="brand-subtitle">Academic Intelligence</span>
          </div>
          {onClose && (
            <button
              type="button"
              className="sidebar-close-btn"
              onClick={onClose}
              aria-label="Close navigation sidebar"
            >
              ✕
            </button>
          )}
        </div>

        {/* Navigation Section */}
        <nav className="sidebar-nav">
          <div className="nav-group-label">WORKSPACE</div>
          <ul className="nav-list">
            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "dashboard" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("dashboard");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "dashboard" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="7" height="7" rx="1.5" />
                    <rect x="14" y="3" width="7" height="7" rx="1.5" />
                    <rect x="14" y="14" width="7" height="7" rx="1.5" />
                    <rect x="3" y="14" width="7" height="7" rx="1.5" />
                  </svg>
                </span>
                <span className="nav-item-label">{isTeacher ? "Teacher Overview" : "Student Dashboard"}</span>
              </button>
            </li>

            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "tasks" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("tasks");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "tasks" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 11l3 3L22 4" />
                    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                  </svg>
                </span>
                <span className="nav-item-label">My Academic Tasks</span>
                {tasksCount > 0 && (
                  <span className="sidebar-counter-badge" title={`${tasksCount} saved tasks`}>
                    {tasksCount}
                  </span>
                )}
              </button>
            </li>

            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "analyze" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("analyze");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "analyze" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    <path d="M8 10h.01" />
                    <path d="M12 10h.01" />
                    <path d="M16 10h.01" />
                  </svg>
                </span>
                <span className="nav-item-label">Analyze Messages</span>
                {candidatesCount > 0 && (
                  <span className="sidebar-counter-badge sidebar-badge-highlight" title={`${candidatesCount} candidates extracted`}>
                    {candidatesCount}
                  </span>
                )}
              </button>
            </li>
          </ul>

          <div className="nav-group-label" style={{ marginTop: "1rem" }}>COLLABORATION &amp; COMMUNITY</div>
          <ul className="nav-list">
            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "courses" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("courses");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "courses" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                  </svg>
                </span>
                <span className="nav-item-label">{isTeacher ? "Manage Courses" : "My Courses"}</span>
              </button>
            </li>

            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "communication" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("communication");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "communication" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
                  </svg>
                </span>
                <span className="nav-item-label">Live Chat</span>
                {unreadMessagesCount > 0 && (
                  <span className="sidebar-counter-badge sidebar-badge-highlight" title={`${unreadMessagesCount} unread messages`}>
                    {unreadMessagesCount}
                  </span>
                )}
              </button>
            </li>

            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "announcements" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("announcements");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "announcements" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 17H2a3 3 0 0 0 3-3V9a7 7 0 0 1 14 0v5a3 3 0 0 0 3 3zm-8.27 4a2 2 0 0 1-3.46 0" />
                  </svg>
                </span>
                <span className="nav-item-label">Announcements</span>
              </button>
            </li>

            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "polls" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("polls");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "polls" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="20" x2="18" y2="10" />
                    <line x1="12" y1="20" x2="12" y2="4" />
                    <line x1="6" y1="20" x2="6" y2="14" />
                  </svg>
                </span>
                <span className="nav-item-label">Interactive Polls</span>
              </button>
            </li>

            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "notifications" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("notifications");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "notifications" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                  </svg>
                </span>
                <span className="nav-item-label">Notifications</span>
                {unreadNotificationsCount > 0 && (
                  <span className="sidebar-counter-badge sidebar-badge-opp" title={`${unreadNotificationsCount} unread notifications`}>
                    {unreadNotificationsCount}
                  </span>
                )}
              </button>
            </li>

            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "analytics" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("analytics");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "analytics" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 3v18h18" />
                    <path d="M18 9l-5 5-4-4-3 3" />
                  </svg>
                </span>
                <span className="nav-item-label">{isTeacher ? "Class Analytics" : "My Analytics"}</span>
              </button>
            </li>
          </ul>

          <div className="nav-group-label" style={{ marginTop: "1rem" }}>ACADEMIC INTEGRATIONS</div>
          <ul className="nav-list">
            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "opportunities" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("opportunities");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "opportunities" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="8" r="7" />
                    <polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88" />
                  </svg>
                </span>
                <span className="nav-item-label">Competitions &amp; Opps</span>
                {opportunitiesCount > 0 && (
                  <span className="sidebar-counter-badge sidebar-badge-opp" title={`${opportunitiesCount} opportunities discovered`}>
                    {opportunitiesCount}
                  </span>
                )}
              </button>
            </li>

            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "classroom" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("classroom");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "classroom" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                  </svg>
                </span>
                <span className="nav-item-label">Classroom &amp; Progress</span>
              </button>
            </li>

            <li>
              <button
                type="button"
                className={`sidebar-nav-item ${activeTab === "materials" ? "active" : ""}`}
                onClick={() => {
                  onSelectTab("materials");
                  if (onClose) onClose();
                }}
                aria-current={activeTab === "materials" ? "page" : undefined}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                  </svg>
                </span>
                <span className="nav-item-label">Study Materials</span>
                {materialsCount > 0 && (
                  <span className="sidebar-counter-badge" title={`${materialsCount} materials indexed`}>
                    {materialsCount}
                  </span>
                )}
              </button>
            </li>

            {isTeacher && (
              <li>
                <button
                  type="button"
                  className={`sidebar-nav-item ${activeTab === "teacher" ? "active" : ""}`}
                  onClick={() => {
                    onSelectTab("teacher");
                    if (onClose) onClose();
                  }}
                  aria-current={activeTab === "teacher" ? "page" : undefined}
                >
                  <span className="nav-item-icon" aria-hidden="true">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                      <circle cx="9" cy="7" r="4" />
                      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                    </svg>
                  </span>
                  <span className="nav-item-label">Teacher Course View</span>
                </button>
              </li>
            )}
          </ul>
        </nav>

        {/* Google Sync Status in Sidebar */}
        <div className="sidebar-google-section">
          <div className="google-status-row">
            <span className="google-icon-sm" aria-hidden="true">G</span>
            <div className="google-status-meta">
              <span className="google-title">Google Integration</span>
              <span className="google-sub">
                {googleAccount?.connected
                  ? `${googleAccount.email} (${googleAccount.is_demo ? "Demo" : "Live"})`
                  : "Not Connected"}
              </span>
            </div>
          </div>
          {googleAccount?.connected && (
            <div className="google-quick-sync-btns">
              <button
                type="button"
                className="btn-sync-sm"
                onClick={onSyncGmail}
                title="Sync Gmail messages for opportunities and deadlines"
              >
                Sync Gmail
              </button>
              <button
                type="button"
                className="btn-sync-sm"
                onClick={onSyncClassroom}
                title="Sync Google Classroom courses and coursework"
              >
                Sync Class
              </button>
            </div>
          )}
        </div>

        {/* User Profile & Logout Section */}
        <div className="sidebar-footer">
          <div className="user-profile-card">
            <div className="user-avatar" aria-hidden="true">
              <span>{user?.name ? user.name.slice(0, 2).toUpperCase() : (isTeacher ? "EV" : "AM")}</span>
            </div>
            <div className="user-meta">
              <span className="user-name">{user?.name || (isTeacher ? "Dr. Elena Vance" : "Alex Morgan")}</span>
              <span className="user-role-tag">{isTeacher ? "Teacher Account" : "Student Account"}</span>
            </div>
            {onLogout && (
              <button
                type="button"
                className="btn-logout"
                onClick={onLogout}
                title="Sign out of your session"
                aria-label="Sign out"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
              </button>
            )}
          </div>
          {user?.is_demo && (
            <div className="sidebar-storage-badge demo">
              <span className="storage-dot demo" aria-hidden="true" />
              <span>OFFLINE DEMO SESSION</span>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
