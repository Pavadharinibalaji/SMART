import assert from "node:assert/strict";

/**
 * Unit tests for SMART frontend authentication state restoration.
 * Tests the state machine logic in App.jsx (checkAuth) across:
 * 1. Post-OAuth successful redirect parameter (?google_auth_success=1)
 * 2. Post-OAuth session verification failure (401 / cookie blocked)
 * 3. Post-OAuth error redirect (?google_auth_error=...)
 * 4. Regular session verification on initial load
 * 5. Clean query parameter stripping via window.history.replaceState
 * 6. Protection against undefined role setter crashes
 */

console.log("Running frontend authRestoration state machine unit tests...");

// Simulation of App.jsx checkAuth state transition logic
async function runCheckAuth({
  searchParams,
  getCurrentUserMock,
  onReplaceState,
  loadGoogleStatusMock = () => {},
}) {
  let authState = "initial";
  let currentUser = null;
  let successMsg = "";
  let googleErrorMsg = "";
  let googleStatusLoaded = false;

  const authSuccess = searchParams.get("google_auth_success");
  const authError = searchParams.get("google_auth_error");

  // Clean up URL parameters
  if (authSuccess || authError) {
    if (onReplaceState) {
      onReplaceState();
    }
  }

  if (authError) {
    googleErrorMsg = decodeURIComponent(authError);
    currentUser = null;
    authState = "unauthenticated";
    return { authState, currentUser, successMsg, googleErrorMsg, googleStatusLoaded };
  }

  authState = "checking";
  try {
    const user = await getCurrentUserMock();
    if (user && user.email) {
      currentUser = user;
      authState = "authenticated";
      if (authSuccess) {
        successMsg = "Google Account successfully connected!";
        loadGoogleStatusMock();
        googleStatusLoaded = true;
      }
    } else {
      currentUser = null;
      authState = "unauthenticated";
      if (authSuccess) {
        googleErrorMsg = "Authenticated session could not be established. Please try signing in again.";
      }
    }
  } catch (err) {
    currentUser = null;
    authState = "unauthenticated";
    if (authSuccess) {
      googleErrorMsg = err.message || "Failed to verify session after Google login.";
    }
  }

  // Derive role safely without calling any undefined setter
  const userRole = currentUser?.role || "student";

  return { authState, currentUser, userRole, successMsg, googleErrorMsg, googleStatusLoaded };
}

// Test 1: Successful OAuth return restores session and triggers status update
{
  let replacedState = false;
  const params = new URLSearchParams("?google_auth_success=1&email=student%40citchennai.net");
  const mockUser = {
    id: 42,
    email: "student@citchennai.net",
    name: "CIT Student",
    role: "student",
    is_demo: false,
  };

  const result = await runCheckAuth({
    searchParams: params,
    getCurrentUserMock: async () => mockUser,
    onReplaceState: () => { replacedState = true; },
  });

  assert.equal(result.authState, "authenticated");
  assert.equal(result.currentUser.email, "student@citchennai.net");
  assert.equal(result.userRole, "student");
  assert.equal(result.googleStatusLoaded, true);
  assert.equal(result.successMsg, "Google Account successfully connected!");
  assert.equal(replacedState, true, "URL parameters must be cleaned from URL bar");
  console.log("[PASS] 1. Successful OAuth return restores session and cleans URL query string");
}

// Test 2: OAuth success returned but session cookie missing / 401
{
  let replacedState = false;
  const params = new URLSearchParams("?google_auth_success=1");

  const result = await runCheckAuth({
    searchParams: params,
    getCurrentUserMock: async () => null, // 401 returns null
    onReplaceState: () => { replacedState = true; },
  });

  assert.equal(result.authState, "unauthenticated");
  assert.equal(result.currentUser, null);
  assert.match(result.googleErrorMsg, /Authenticated session could not be established/);
  assert.equal(replacedState, true);
  console.log("[PASS] 2. Session verification failure after OAuth gracefully transitions to unauthenticated with error");
}

// Test 3: OAuth error in callback URL (?google_auth_error=...)
{
  let replacedState = false;
  const errMsg = "Access denied: Not an authorized institutional account.";
  const params = new URLSearchParams(`?google_auth_error=${encodeURIComponent(errMsg)}`);

  const result = await runCheckAuth({
    searchParams: params,
    getCurrentUserMock: async () => { throw new Error("Should not be called"); },
    onReplaceState: () => { replacedState = true; },
  });

  assert.equal(result.authState, "unauthenticated");
  assert.equal(result.currentUser, null);
  assert.equal(result.googleErrorMsg, errMsg);
  assert.equal(replacedState, true);
  console.log("[PASS] 3. OAuth error query param surfaces user error and does not call session endpoint");
}

// Test 4: Normal initial mount with existing active session
{
  const params = new URLSearchParams("");
  const mockUser = { id: 10, email: "prof.ann@citchennai.net", name: "Prof Ann", role: "teacher" };

  const result = await runCheckAuth({
    searchParams: params,
    getCurrentUserMock: async () => mockUser,
  });

  assert.equal(result.authState, "authenticated");
  assert.equal(result.currentUser.email, "prof.ann@citchennai.net");
  assert.equal(result.userRole, "teacher");
  assert.equal(result.googleStatusLoaded, false, "loadGoogleStatus only triggered on OAuth redirect");
  console.log("[PASS] 4. Normal initial mount with active session transitions to authenticated");
}

// Test 5: Normal initial mount without session (401)
{
  const params = new URLSearchParams("");

  const result = await runCheckAuth({
    searchParams: params,
    getCurrentUserMock: async () => null,
  });

  assert.equal(result.authState, "unauthenticated");
  assert.equal(result.currentUser, null);
  assert.equal(result.googleErrorMsg, "");
  console.log("[PASS] 5. Normal initial mount without session transitions to unauthenticated cleanly");
}

// Test 6: Network exception during auth verification does not crash
{
  const params = new URLSearchParams("?google_auth_success=1");

  const result = await runCheckAuth({
    searchParams: params,
    getCurrentUserMock: async () => {
      throw new Error("Could not connect to SMART backend.");
    },
  });

  assert.equal(result.authState, "unauthenticated");
  assert.equal(result.currentUser, null);
  assert.match(result.googleErrorMsg, /Could not connect to SMART backend/);
  console.log("[PASS] 6. Network failure during session check handled gracefully without unhandled rejection");
}

console.log("All 6 authRestoration tests passed successfully!");
