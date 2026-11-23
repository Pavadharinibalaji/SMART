import assert from "node:assert/strict";

// Helper function implementing the getApiBaseUrl logic for isolated unit testing
function resolveApiBaseUrl(env, windowObj = null) {
  const envUrl = env.VITE_API_URL;
  if (envUrl && typeof envUrl === "string" && envUrl.trim()) {
    return envUrl.trim().replace(/\/+$/, "");
  }

  // In production builds, never silently default to localhost or current hostname:8000
  if (env.PROD) {
    throw new Error(
      "Configuration Error: VITE_API_URL is not defined in the production build environment. " +
      "Please set VITE_API_URL in your Vercel Project Settings (Environment Variables) and redeploy without build cache."
    );
  }

  // Local development fallback
  if (windowObj && windowObj.location && windowObj.location.hostname) {
    return `http://${windowObj.location.hostname}:8000`;
  }
  return "http://127.0.0.1:8000";
}

function resolveWsUrl(apiBaseUrl, courseId) {
  const baseUrl = apiBaseUrl.replace(/^http/, "ws");
  return `${baseUrl}/ws/courses/${encodeURIComponent(courseId)}/messages`;
}

console.log("Running getApiBaseUrl & WebSocket URL unit tests...");

// Test 1: Production with valid HTTPS URL
{
  const env = { PROD: true, VITE_API_URL: "https://smart-backend.onrender.com" };
  const url = resolveApiBaseUrl(env);
  assert.equal(url, "https://smart-backend.onrender.com");
  console.log("[PASS] 1. Production with valid HTTPS URL resolves correctly");
}

// Test 2: Production with trailing slashes and whitespace
{
  const env = { PROD: true, VITE_API_URL: "  https://smart-backend.onrender.com///  " };
  const url = resolveApiBaseUrl(env);
  assert.equal(url, "https://smart-backend.onrender.com");
  console.log("[PASS] 2. Trailing slashes and whitespace are properly trimmed");
}

// Test 3: Production with missing VITE_API_URL must throw configuration error
{
  const env = { PROD: true, VITE_API_URL: "" };
  assert.throws(
    () => resolveApiBaseUrl(env),
    /Configuration Error: VITE_API_URL is not defined/
  );
  console.log("[PASS] 3. Missing VITE_API_URL in production throws clear configuration error");
}

// Test 4: Production with undefined VITE_API_URL must throw configuration error
{
  const env = { PROD: true };
  assert.throws(
    () => resolveApiBaseUrl(env),
    /Configuration Error: VITE_API_URL is not defined/
  );
  console.log("[PASS] 4. Undefined VITE_API_URL in production throws clear configuration error");
}

// Test 5: Development with window.location.hostname
{
  const env = { DEV: true, PROD: false, VITE_API_URL: undefined };
  const mockWindow = { location: { hostname: "192.168.1.50" } };
  const url = resolveApiBaseUrl(env, mockWindow);
  assert.equal(url, "http://192.168.1.50:8000");
  console.log("[PASS] 5. Development with hostname falls back to hostname:8000");
}

// Test 6: Development fallback without window
{
  const env = { DEV: true, PROD: false, VITE_API_URL: undefined };
  const url = resolveApiBaseUrl(env, null);
  assert.equal(url, "http://127.0.0.1:8000");
  console.log("[PASS] 6. Development fallback without window returns 127.0.0.1:8000");
}

// Test 7: WebSocket URL conversion from HTTPS to WSS
{
  const apiUrl = "https://smart-backend.onrender.com";
  const wsUrl = resolveWsUrl(apiUrl, 42);
  assert.equal(wsUrl, "wss://smart-backend.onrender.com/ws/courses/42/messages");
  console.log("[PASS] 7. WebSocket URL converts HTTPS to WSS properly");
}

// Test 8: WebSocket URL conversion from HTTP to WS in dev
{
  const apiUrl = "http://localhost:8000";
  const wsUrl = resolveWsUrl(apiUrl, 101);
  assert.equal(wsUrl, "ws://localhost:8000/ws/courses/101/messages");
  console.log("[PASS] 8. WebSocket URL converts HTTP to WS properly");
}

console.log("All 8 getApiBaseUrl and WebSocket URL tests passed successfully!");
