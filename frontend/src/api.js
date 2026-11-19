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
 * Update the status of a saved academic task ('pending', 'completed', 'dismissed').
 */
export async function updateAcademicItemStatus(itemId, newStatus) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/academic-items/${itemId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ status: newStatus }),
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
      `Failed to update status for item #${itemId} (HTTP ${response.status}).`;
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data;
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
 * Helper to get direct iCalendar download URL.
 */
export function getExportIcsUrl() {
  return `${API_BASE_URL}/api/academic-items/export-ics`;
}
