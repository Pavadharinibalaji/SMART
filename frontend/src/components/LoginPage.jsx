import { useState } from "react";

export default function LoginPage({ onLoginSuccess }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSignIn = async (targetEmail) => {
    const loginEmail = targetEmail || email;
    if (!loginEmail.trim()) {
      setError("Please enter your academic email address.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      await onLoginSuccess(loginEmail.trim());
    } catch (err) {
      setError(err.message || "Failed to sign in. Please verify your account.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-screen-wrapper">
      <div className="login-panel-container">
        {/* Brand Header */}
        <div className="login-brand-header">
          <div className="brand-logo-mark large" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <h1 className="login-app-title">SMART</h1>
          <p className="login-app-tagline">Academic Communication Intelligence System</p>
        </div>

        {/* Card Body */}
        <div className="login-card">
          <div className="login-card-header">
            <h2>Institutional Sign In</h2>
            <p>Access your university tasks, coursework progress, and academic deadlines.</p>
          </div>

          {error && (
            <div className="login-error-alert" role="alert">
              <span className="error-icon" aria-hidden="true">⚠️</span>
              <span>{error}</span>
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSignIn();
            }}
            className="login-form"
          >
            <div className="form-group">
              <label htmlFor="login-email-input">Academic Email Address</label>
              <input
                id="login-email-input"
                type="email"
                className="login-input"
                placeholder="e.g. alex.morgan@university.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading}
                autoFocus
              />
              <span className="form-help-text">Only pre-provisioned university accounts can access the dashboard.</span>
            </div>

            <button
              type="submit"
              className="btn btn-primary login-submit-btn"
              disabled={loading || !email.trim()}
            >
              {loading ? "Authenticating..." : "Sign In with University Account"}
            </button>
          </form>

          {/* Development / Demo Mode Identities */}
          <div className="demo-sign-in-section">
            <div className="demo-divider">
              <span>DEVELOPMENT DEMO IDENTITIES</span>
            </div>
            <p className="demo-explainer">
              Select an offline demo account. Role switching during active sessions is disabled.
            </p>

            <div className="demo-actions-grid">
              <button
                type="button"
                className="demo-account-btn student"
                onClick={() => handleSignIn("alex.morgan@university.edu")}
                disabled={loading}
              >
                <div className="demo-btn-role-badge">STUDENT</div>
                <div className="demo-btn-name">Alex Morgan</div>
                <div className="demo-btn-meta">alex.morgan@university.edu · B.Tech CS</div>
              </button>

              <button
                type="button"
                className="demo-account-btn teacher"
                onClick={() => handleSignIn("e.vance@university.edu")}
                disabled={loading}
              >
                <div className="demo-btn-role-badge">TEACHER</div>
                <div className="demo-btn-name">Dr. Elena Vance</div>
                <div className="demo-btn-meta">e.vance@university.edu · Faculty Lead</div>
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="login-footer">
          <span>Local-First Academic Intelligence · Powered by SQLite &amp; FastAPI</span>
        </div>
      </div>
    </div>
  );
}
