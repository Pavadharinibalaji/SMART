import { useState } from "react";
import { getGoogleAuthUrl } from "../api";

export default function LoginPage({ onLoginSuccess }) {
  const [email, setEmail] = useState("");
  const [idToken, setIdToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSignIn = async (targetEmail, targetToken = null) => {
    const loginEmail = targetEmail || email;
    if (!loginEmail.trim()) {
      setError("Please enter your academic email address.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      await onLoginSuccess(loginEmail.trim(), targetToken || idToken.trim() || null);
    } catch (err) {
      setError(err.message || "Failed to sign in. Please verify your account.");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await getGoogleAuthUrl("student");
      if (res && res.auth_url) {
        window.location.href = res.auth_url;
      } else {
        setError("Could not retrieve Google sign-in URL.");
      }
    } catch (err) {
      setError(err.message || "Google sign-in initiation failed.");
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

          <div className="google-sso-container" style={{ marginBottom: "1.25rem" }}>
            <button
              type="button"
              className="btn btn-secondary google-signin-btn"
              onClick={handleGoogleSignIn}
              disabled={loading}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.6rem",
                padding: "0.75rem 1rem",
                borderRadius: "8px",
                border: "1px solid #d1d5db",
                backgroundColor: "#ffffff",
                color: "#1f2937",
                fontWeight: 600,
                cursor: "pointer",
                boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
              </svg>
              <span>Sign in with Google Workspace</span>
            </button>
          </div>

          <div className="demo-divider" style={{ marginBottom: "1.25rem" }}>
            <span>OR ENTER CREDENTIALS</span>
          </div>

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
                placeholder="e.g. pavadharinibg.csbs2024@citchennai.net"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading}
                autoFocus
              />
              <span className="form-help-text">Only pre-provisioned university accounts can access the dashboard.</span>
            </div>

            <div className="form-group" style={{ marginTop: "0.75rem" }}>
              <label htmlFor="login-token-input">Google ID Token (Optional / Manual Verification)</label>
              <input
                id="login-token-input"
                type="password"
                className="login-input"
                placeholder="Required for institutional accounts if not using Google SSO"
                value={idToken}
                onChange={(e) => setIdToken(e.target.value)}
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary login-submit-btn"
              disabled={loading || !email.trim()}
              style={{ marginTop: "0.5rem" }}
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
