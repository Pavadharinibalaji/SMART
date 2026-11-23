/**
 * Centralized API service for SMART frontend.
 * Provides unified fetch wrappers, error propagation, network error handling,
 * and consistent base URL matching the local FastAPI backend.
 */

export function getApiBaseUrl() {
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl && typeof envUrl === "string" && envUrl.trim()) {
    return envUrl.trim().replace(/\/+$/, "");
  }

  // In production builds, never silently default to localhost or current hostname:8000
  if (import.meta.env.PROD) {
    throw new Error(
      "Configuration Error: VITE_API_URL is not defined in the production build environment. " +
      "Please set VITE_API_URL in your Vercel Project Settings (Environment Variables) and redeploy without build cache."
    );
  }

  // Local development fallback
  if (typeof window !== "undefined" && window.location && window.location.hostname) {
    return `http://${window.location.hostname}:8000`;
  }
  return "http://127.0.0.1:8000";
}

export const API_BASE_URL = getApiBaseUrl();

/**
 * Log in provisioned user or demo identity with HttpOnly cookie session.
 */
export async function loginUser(email, idToken = null) {
  let resp;
  const payload = { email };
  if (idToken) {
    payload.id_token = idToken;
  }
  try {
    resp = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });
  } catch (netErr) {
    throw new Error(`Could not connect to SMART backend at ${API_BASE_URL}.`, { cause: netErr });
  }

  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const error = new Error(data.detail || `Login failed (HTTP ${resp.status}).`);
    error.status = resp.status;
    throw error;
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
 * Mark a task as reviewed / confirmed by human review, optionally setting its status (e.g. 'pending').
 */
export async function markTaskReviewed(itemId, status = "pending") {
  return updateAcademicItem(itemId, {
    review_required: false,
    status: status,
  });
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

export async function getGoogleAuthUrl(role = "student", redirectUri = null) {
  const params = new URLSearchParams({ role });
  if (redirectUri) {
    params.append("redirect_uri", redirectUri);
  }
  const resp = await fetch(`${API_BASE_URL}/api/auth/google/url?${params.toString()}`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to retrieve Google Auth URL");
  }
  return resp.json();
}

export async function getGoogleAuthStatus(role = "student") {
  const resp = await fetch(`${API_BASE_URL}/api/auth/google/status`, {
    headers: { "X-User-Role": role },
    credentials: "include",
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
  const resp = await fetch(url, {
    method: "POST",
    credentials: "include",
  });
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
    credentials: "include",
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
    credentials: "include",
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
  const resp = await fetch(url, {
    headers,
    credentials: "include",
  });
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
    credentials: "include",
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

export async function turnInCoursework(courseworkId, alternateLink = null, role = "student", email = null) {
  const headers = {
    "Content-Type": "application/json",
    "X-User-Role": role,
  };
  if (email) headers["X-User-Email"] = email;
  const resp = await fetch(`${API_BASE_URL}/api/classroom/submissions/turn-in`, {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify({
      coursework_id: courseworkId,
      alternate_link: alternateLink,
    }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to turn in coursework");
  }
  return resp.json();
}

export async function gradeSubmission(submissionId, assignedGrade, role = "teacher", email = null) {
  const headers = {
    "Content-Type": "application/json",
    "X-User-Role": role,
  };
  if (email) headers["X-User-Email"] = email;
  const resp = await fetch(`${API_BASE_URL}/api/classroom/submissions/${encodeURIComponent(submissionId)}/grade`, {
    method: "PATCH",
    headers,
    credentials: "include",
    body: JSON.stringify({
      assigned_grade: Number(assignedGrade),
    }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to submit grade");
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

// -------------------------------------------------------------
// SMART 3.0 Collaboration & Engagement API Endpoints
// -------------------------------------------------------------

export async function getSmartCourses() {
  const resp = await fetch(`${API_BASE_URL}/api/courses`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch courses");
  }
  const data = await resp.json();
  const list = Array.isArray(data) ? data : (data.courses || []);
  return { courses: list };
}

export async function createSmartCourse(data) {
  const resp = await fetch(`${API_BASE_URL}/api/courses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to create course");
  }
  return resp.json();
}

export async function getSmartCourseDetails(courseId) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch course details");
  }
  return resp.json();
}

export async function regenerateCourseJoinCode(courseId) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/regenerate-code`, {
    method: "POST",
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to regenerate join code");
  }
  return resp.json();
}

export async function joinSmartCourse(joinCode) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ join_code: joinCode }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to join course");
  }
  return resp.json();
}

export async function getCourseMembers(courseId) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/members`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch course members");
  }
  const data = await resp.json();
  const list = Array.isArray(data) ? data : (data.members || []);
  return { members: list };
}

export async function removeCourseMember(courseId, studentId) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/members/${encodeURIComponent(studentId)}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to remove course member");
  }
  return resp.json();
}

export async function inviteStudentToCourse(courseId, email) {
  const cleanEmail = (email || "").trim();
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/invitations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ student_email: cleanEmail, email: cleanEmail }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to invite student");
  }
  return resp.json();
}

export async function getPendingInvitations() {
  const resp = await fetch(`${API_BASE_URL}/api/student/invitations`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch student invitations");
  }
  const data = await resp.json();
  const list = Array.isArray(data) ? data : (data.invitations || []);
  return { invitations: list };
}

export async function acceptCourseInvitation(invitationId) {
  const resp = await fetch(`${API_BASE_URL}/api/student/invitations/${encodeURIComponent(invitationId)}/accept`, {
    method: "POST",
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to accept course invitation");
  }
  return resp.json();
}

export async function getCourseMessages(courseId, limit = 50) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/messages?limit=${limit}`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch messages");
  }
  const data = await resp.json();
  const list = Array.isArray(data) ? data : (data.messages || []);
  return { messages: list };
}

export async function sendCourseMessage(courseId, content, attachmentUrl = null) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ content, attachment_url: attachmentUrl }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to send message");
  }
  const data = await resp.json();
  return data.message ? data : { message: data };
}

export async function markCourseMessagesRead(courseId) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/messages/read`, {
    method: "POST",
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to mark messages as read");
  }
  return resp.json();
}

export async function getUnreadMessageCount() {
  const resp = await fetch(`${API_BASE_URL}/api/messages/unread-count`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    const error = new Error(err.detail || "Failed to get unread message count");
    error.status = resp.status;
    throw error;
  }
  return resp.json();
}

export async function getCourseAnnouncements(courseId) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/announcements`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch announcements");
  }
  const data = await resp.json();
  const list = Array.isArray(data) ? data : (data.announcements || []);
  return { announcements: list };
}

export async function createCourseAnnouncement(courseId, data) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/announcements`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to post announcement");
  }
  return resp.json();
}

export async function acknowledgeAnnouncement(courseId, announcementId) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/announcements/${encodeURIComponent(announcementId)}/acknowledge`, {
    method: "POST",
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to acknowledge announcement");
  }
  return resp.json();
}

export async function getCoursePolls(courseId) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/polls`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch course polls");
  }
  const data = await resp.json();
  const list = Array.isArray(data) ? data : (data.polls || []);
  return { polls: list };
}

export async function createCoursePoll(courseId, data) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/polls`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to create poll");
  }
  return resp.json();
}

export async function submitPollVote(courseId, pollId, optionId, shortFeedback = null) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/polls/${encodeURIComponent(pollId)}/vote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      option_id: optionId,
      feedback_text: shortFeedback,
      short_feedback: shortFeedback,
    }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to cast vote");
  }
  return resp.json();
}

export async function closeCoursePoll(courseId, pollId) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/polls/${encodeURIComponent(pollId)}/close`, {
    method: "POST",
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to close poll");
  }
  return resp.json();
}

export async function getNotifications(unreadOnly = false) {
  const q = unreadOnly ? "?unread_only=true" : "";
  const resp = await fetch(`${API_BASE_URL}/api/notifications${q}`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    const error = new Error(err.detail || "Failed to fetch notifications");
    error.status = resp.status;
    throw error;
  }
  return resp.json();
}

export async function markNotificationRead(notifId) {
  const resp = await fetch(`${API_BASE_URL}/api/notifications/${encodeURIComponent(notifId)}/read`, {
    method: "POST",
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    const error = new Error(err.detail || "Failed to mark notification read");
    error.status = resp.status;
    throw error;
  }
  return resp.json();
}

export async function markAllNotificationsRead() {
  const resp = await fetch(`${API_BASE_URL}/api/notifications/read-all`, {
    method: "POST",
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    const error = new Error(err.detail || "Failed to mark all notifications read");
    error.status = resp.status;
    throw error;
  }
  return resp.json();
}

export async function getUnreadNotificationCount() {
  const resp = await fetch(`${API_BASE_URL}/api/notifications/unread-count`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    const error = new Error(err.detail || "Failed to get unread notification count");
    error.status = resp.status;
    throw error;
  }
  return resp.json();
}

export async function getCourseAnalytics(courseId) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/analytics`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch course analytics");
  }
  return resp.json();
}

export async function getStudentAnalytics() {
  const resp = await fetch(`${API_BASE_URL}/api/student/analytics`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch student analytics");
  }
  return resp.json();
}

// ==============================================================================
// SMART 3.1: Native Study Materials & Resource Management
// ==============================================================================

export async function uploadCourseMaterial(courseId, formData) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/materials`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to upload study material");
  }
  return resp.json();
}

export async function getCourseMaterials(courseId, category = null, search = null) {
  const params = new URLSearchParams();
  if (category && category !== "ALL") params.append("category", category);
  if (search && search.trim()) params.append("search", search.trim());
  const qs = params.toString() ? `?${params.toString()}` : "";
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/materials${qs}`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch study materials");
  }
  return resp.json();
}

export async function getMaterialMetadata(materialId) {
  const resp = await fetch(`${API_BASE_URL}/api/materials/${encodeURIComponent(materialId)}`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch material details");
  }
  return resp.json();
}

export async function updateCourseMaterial(materialId, updates) {
  const resp = await fetch(`${API_BASE_URL}/api/materials/${encodeURIComponent(materialId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(updates),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to update study material");
  }
  return resp.json();
}

export async function deleteCourseMaterial(materialId) {
  const resp = await fetch(`${API_BASE_URL}/api/materials/${encodeURIComponent(materialId)}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to delete study material");
  }
  return resp.json();
}

export function getMaterialDownloadUrl(materialId) {
  return `${API_BASE_URL}/api/materials/${encodeURIComponent(materialId)}/download`;
}

export function getMaterialPreviewUrl(materialId) {
  return `${API_BASE_URL}/api/materials/${encodeURIComponent(materialId)}/preview`;
}

// ==============================================================================
// SMART 3.2: Student Competitions & Opportunities Tracking with Faculty Analytics
// ==============================================================================

export async function getStudentTrackedOpportunities(category = null, status = null, search = null, courseId = null) {
  const params = new URLSearchParams();
  if (category && category !== "All") params.append("category", category);
  if (status && status !== "All") params.append("status", status);
  if (search && search.trim()) params.append("search", search.trim());
  if (courseId) params.append("course_id", courseId);

  const qs = params.toString() ? `?${params.toString()}` : "";
  const resp = await fetch(`${API_BASE_URL}/api/student/opportunities${qs}`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch tracked opportunities");
  }
  return resp.json();
}

export async function trackOpportunity(data) {
  const resp = await fetch(`${API_BASE_URL}/api/student/opportunities`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to track opportunity");
  }
  return resp.json();
}

export async function updateTrackedOpportunity(id, data) {
  const resp = await fetch(`${API_BASE_URL}/api/student/opportunities/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to update opportunity");
  }
  return resp.json();
}

export async function deleteTrackedOpportunity(id) {
  const resp = await fetch(`${API_BASE_URL}/api/student/opportunities/${encodeURIComponent(id)}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to delete tracked opportunity");
  }
  return resp.json();
}

export async function checkOpportunityReminders() {
  const resp = await fetch(`${API_BASE_URL}/api/student/opportunities/check-reminders`, {
    method: "POST",
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to check deadline reminders");
  }
  return resp.json();
}

export async function getCourseOpportunitiesAnalytics(courseId) {
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/opportunities/analytics`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch course opportunities analytics");
  }
  return resp.json();
}

export async function getCourseOpportunitiesParticipation(courseId, category = null, status = null) {
  const params = new URLSearchParams();
  if (category && category !== "All") params.append("category", category);
  if (status && status !== "All") params.append("status", status);

  const qs = params.toString() ? `?${params.toString()}` : "";
  const resp = await fetch(`${API_BASE_URL}/api/courses/${encodeURIComponent(courseId)}/opportunities/participation${qs}`, {
    credentials: "include",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch course opportunities participation");
  }
  return resp.json();
}
