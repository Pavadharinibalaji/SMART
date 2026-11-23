/**
 * Centralized API service for SMART frontend.
 * Provides unified fetch wrappers, error propagation, network error handling,
 * and consistent base URL matching the local FastAPI backend.
 */

export function getApiBaseUrl() {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  // Default to 127.0.0.1:8000 to match FastAPI --host 127.0.0.1 binding
  // and prevent Windows IPv6 [::1] connection refusal issues.
  return "http://127.0.0.1:8000";
}

export const API_BASE_URL = getApiBaseUrl();

/**
 * Log in provisioned user or demo identity with HttpOnly cookie session.
 */
export async function loginUser(email) {
  let resp;
  try {
    resp = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email }),
    });
  } catch (netErr) {
    throw new Error(`Could not connect to SMART backend at ${API_BASE_URL}.`, { cause: netErr });
  }

  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.detail || `Login failed (HTTP ${resp.status}).`);
  }
  return data;
}

/**
 * Get current authenticated user session profile.
 */
export async function getCurrentUser() {
  let resp;
  try {
    resp = await fetch(`${API_BASE_URL}/api/auth/me`, {
      credentials: "include",
    });
  } catch (netErr) {
    throw new Error(`Could not connect to SMART backend at ${API_BASE_URL}.`, { cause: netErr });
  }

  if (resp.status === 401) {
    return null;
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.detail || `Failed to fetch user session (HTTP ${resp.status}).`);
  }
  return data.user;
}

/**
 * Terminate user session and clear cookie.
 */
export async function logoutUser() {
  const resp = await fetch(`${API_BASE_URL}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  return resp.json().catch(() => ({ status: "logged_out" }));
}

/**
 * Upload and extract candidate academic items from a WhatsApp .txt export.
 */
export async function extractAcademic(file) {
  const formData = new FormData();
  formData.append("file", file);

  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/extract-academic`, {
      method: "POST",
      body: formData,
    });
  } catch (netErr) {
    throw new Error(
      `Could not connect to the SMART backend at ${API_BASE_URL}. Please ensure the FastAPI server is running (e.g. py -m uvicorn main:app --host 127.0.0.1 --port 8000).`,
      { cause: netErr }
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg =
      data?.detail ||
      `Backend extraction failed with HTTP ${response.status} (${response.statusText}).`;
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data;
}

/**
 * Extract candidate academic items from any supported communication source.
 * Supports WhatsApp, Gmail, Google Classroom, and Manual entry.
 */
export async function extractAcademicFromSource(sourcePayload) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/extract-academic-source`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(sourcePayload),
    });
  } catch (netErr) {
    throw new Error(
      `Could not connect to the SMART backend at ${API_BASE_URL}. Please ensure the FastAPI server is running.`,
      { cause: netErr }
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg =
      data?.detail ||
      `Source extraction failed with HTTP ${response.status} (${response.statusText}).`;
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data;
}

/**
 * Save an extracted candidate item into the persistent SQLite database.
 */
export async function saveAcademicItem(payload) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/academic-items`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
  } catch (netErr) {
    throw new Error(
      `Could not connect to the SMART backend at ${API_BASE_URL}. Please ensure the FastAPI server is running.`,
      { cause: netErr }
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg =
      data?.detail ||
      `Failed to save academic item with HTTP ${response.status} (${response.statusText}).`;
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data;
}

/**
 * Query and filter saved academic tasks.
 */
export async function getAcademicItems(filters = {}) {
  const params = new URLSearchParams();

  if (filters.category && filters.category !== "ALL") {
    params.append("category", filters.category);
  }
  if (filters.status && filters.status !== "ALL") {
    params.append("status", filters.status.toLowerCase());
  }
  if (filters.search && filters.search.trim()) {
    params.append("search", filters.search.trim());
  }
  if (filters.due_before) {
    params.append("due_before", filters.due_before);
  }
  if (filters.due_after) {
    params.append("due_after", filters.due_after);
  }
  if (filters.confidence && filters.confidence !== "ALL") {
    params.append("confidence", filters.confidence.toUpperCase());
  }
  if (filters.priority && filters.priority !== "ALL") {
    params.append("priority", filters.priority.toUpperCase());
  }
  if (filters.importance && filters.importance !== "ALL") {
    params.append("importance", filters.importance.toUpperCase());
  }
  if (filters.urgency && filters.urgency !== "ALL") {
    params.append("urgency", filters.urgency.toUpperCase());
  }
  if (filters.academic_intent && filters.academic_intent !== "ALL") {
    params.append("academic_intent", filters.academic_intent.toLowerCase());
  }
  if (filters.source_type && filters.source_type !== "ALL") {
    params.append("source_type", filters.source_type.toLowerCase());
  }

  const queryString = params.toString() ? `?${params.toString()}` : "";
  const endpointUrl = `${API_BASE_URL}/api/academic-items${queryString}`;

  let response;
  try {
    response = await fetch(endpointUrl);
  } catch (netErr) {
    throw new Error(
      `Could not connect to SMART backend at ${API_BASE_URL}. Please make sure the FastAPI backend is running at http://127.0.0.1:8000.`,
      { cause: netErr }
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg =
      data?.detail ||
      `Failed to load academic tasks (HTTP ${response.status} ${response.statusText}).`;
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return Array.isArray(data) ? data : (data?.items || []);
}

/**
 * Update editable fields of a saved academic task ('title', 'category', 'due_date', 'description', 'importance', 'status', etc.).
 */
export async function updateAcademicItem(itemId, updatePayload) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/academic-items/${itemId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(updatePayload),
    });
  } catch (netErr) {
    throw new Error(
      `Could not connect to SMART backend at ${API_BASE_URL}. Please ensure the server is running.`,
      { cause: netErr }
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg =
      data?.detail ||
      `Failed to update item #${itemId} (HTTP ${response.status}).`;
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data;
}

/**
 * Retrieve a single academic item by ID.
 */
export async function getAcademicItemById(itemId) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/academic-items/${itemId}`);
  } catch (netErr) {
    throw new Error(
      `Could not connect to SMART backend at ${API_BASE_URL}.`,
      { cause: netErr }
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg =
      data?.detail ||
      `Failed to retrieve item #${itemId} (HTTP ${response.status}).`;
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data;
}

/**
 * Update the status of a saved academic task ('pending', 'completed', 'dismissed').
 */
export async function updateAcademicItemStatus(itemId, newStatus) {
  return updateAcademicItem(itemId, { status: newStatus });
}

/**
 * Delete a saved academic task permanently.
 */
export async function deleteAcademicItem(itemId) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/academic-items/${itemId}`, {
      method: "DELETE",
    });
  } catch (netErr) {
    throw new Error(
      `Could not connect to SMART backend at ${API_BASE_URL}. Please ensure the server is running.`,
      { cause: netErr }
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg =
      data?.detail ||
      `Failed to delete item #${itemId} (HTTP ${response.status}).`;
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data;
}

/**
 * Retrieve relationship hierarchy and revision lineage for an academic task.
 */
export async function getTaskRelationships(itemId) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/academic-items/${itemId}/relationships`);
  } catch (netErr) {
    throw new Error(
      `Could not connect to SMART backend at ${API_BASE_URL}.`,
      { cause: netErr }
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg =
      data?.detail ||
      `Failed to fetch relationships for task #${itemId} (HTTP ${response.status}).`;
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data;
}

/**
 * Helper to get direct iCalendar download URL.
 */
export function getExportIcsUrl() {
  return `${API_BASE_URL}/api/academic-items/export-ics`;
}

/* ==========================================================================
   SMART 2.1 — Google OAuth, Opportunities, Classroom & Materials APIs
   ========================================================================== */

export async function getGoogleAuthUrl(role = "student") {
  const resp = await fetch(`${API_BASE_URL}/api/auth/google/url?role=${encodeURIComponent(role)}`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to retrieve Google Auth URL");
  }
  return resp.json();
}

export async function getGoogleAuthStatus(role = "student") {
  const resp = await fetch(`${API_BASE_URL}/api/auth/google/status`, {
    headers: { "X-User-Role": role },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to check Google connection status");
  }
  return resp.json();
}

export async function disconnectGoogleAccount(email) {
  const url = email
    ? `${API_BASE_URL}/api/auth/google/disconnect?email=${encodeURIComponent(email)}`
    : `${API_BASE_URL}/api/auth/google/disconnect`;
  const resp = await fetch(url, { method: "POST" });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to disconnect Google account");
  }
  return resp.json();
}

export async function toggleDemoData(enable = true, studentEmail = "student.demo@univ.edu") {
  const resp = await fetch(`${API_BASE_URL}/api/auth/demo-toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enable, student_email: studentEmail }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to toggle demo data");
  }
  return resp.json();
}

export async function syncGmail(role = "student", email = null) {
  const headers = { "X-User-Role": role };
  if (email) headers["X-User-Email"] = email;
  const resp = await fetch(`${API_BASE_URL}/api/sync/gmail`, {
    method: "POST",
    headers,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to sync Gmail");
  }
  return resp.json();
}

export async function getOpportunities(statusFilter = null, email = null) {
  const params = new URLSearchParams();
  if (statusFilter && statusFilter !== "ALL") {
    params.append("status", statusFilter);
  }
  const headers = {};
  if (email) headers["X-User-Email"] = email;
  const url = `${API_BASE_URL}/api/opportunities${params.toString() ? `?${params.toString()}` : ""}`;
  const resp = await fetch(url, { headers });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch opportunities");
  }
  return resp.json();
}

export async function updateOpportunityStatus(opportunityId, status, notes = "", ref = "", email = null) {
  const headers = { "Content-Type": "application/json" };
  if (email) headers["X-User-Email"] = email;
  const resp = await fetch(`${API_BASE_URL}/api/opportunities/${opportunityId}/status`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({
      status,
      evidence_notes: notes,
      confirmation_source_ref: ref,
    }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to update opportunity status");
  }
  return resp.json();
}

// Alias for convenience
export const updateStudentOpportunityStatus = (oppId, status, email = null) =>
  updateOpportunityStatus(oppId, status, "", "", email);

export async function getTeacherOpportunitiesOverview(role = "teacher") {
  const resp = await fetch(`${API_BASE_URL}/api/teacher/opportunities-overview`, {
    headers: { "X-User-Role": role },
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to load teacher opportunities overview");
  }
  return resp.json();
}

export async function syncClassroom(role = "student", email = null) {
  const headers = { "X-User-Role": role };
  if (email) headers["X-User-Email"] = email;
  const resp = await fetch(`${API_BASE_URL}/api/sync/classroom`, {
    method: "POST",
    headers,
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to sync Classroom");
  }
  return resp.json();
}

export async function getClassroomCourses(role = null) {
  const params = role ? `?role=${encodeURIComponent(role)}` : "";
  const resp = await fetch(`${API_BASE_URL}/api/classroom/courses${params}`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch classroom courses");
  }
  return resp.json();
}

export async function getClassroomCoursework(courseId = null) {
  const params = courseId ? `?course_id=${encodeURIComponent(courseId)}` : "";
  const resp = await fetch(`${API_BASE_URL}/api/classroom/coursework${params}`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch coursework");
  }
  return resp.json();
}

export async function getClassroomSubmissions(courseId = null, role = "student", email = null) {
  const params = courseId ? `?course_id=${encodeURIComponent(courseId)}` : "";
  const headers = { "X-User-Role": role };
  if (email) headers["X-User-Email"] = email;
  const resp = await fetch(`${API_BASE_URL}/api/classroom/submissions${params}`, {
    headers,
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch submissions");
  }
  return resp.json();
}

export async function getTeacherCourseworkOverview(roleOrEmail = "teacher", email = null) {
  let role = "teacher";
  let userEmail = email;
  if (roleOrEmail && roleOrEmail.includes("@")) {
    userEmail = roleOrEmail;
    role = email || "teacher";
  } else if (roleOrEmail) {
    role = roleOrEmail;
  }
  const headers = { "X-User-Role": role };
  if (userEmail) headers["X-User-Email"] = userEmail;
  const resp = await fetch(`${API_BASE_URL}/api/teacher/coursework-overview`, {
    headers,
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch teacher coursework overview");
  }
  return resp.json();
}

export async function getStudyMaterials(courseId = null, sourceType = null) {
  const params = new URLSearchParams();
  if (courseId) params.append("course_id", courseId);
  if (sourceType) params.append("source_type", sourceType);
  const q = params.toString() ? `?${params.toString()}` : "";
  const resp = await fetch(`${API_BASE_URL}/api/materials${q}`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch study materials");
  }
  return resp.json();
}
