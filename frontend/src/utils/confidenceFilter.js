/**
 * Confidence filtering utility for SMART 2.0.
 *
 * Normalizes confidence levels consistently across candidate items and saved tasks:
 * - HIGH: Explicit validated items
 * - MEDIUM: Relative or unconfirmed dates
 * - LOW: Ambiguous items
 * - UNASSESSED: Manual tasks, legacy pre-Phase 3 records, null/undefined/empty/unsupported values
 *
 * Provides pure, non-mutating filtering functions that integrate with existing filters.
 */

export const ALLOWED_CONFIDENCE_LEVELS = ["HIGH", "MEDIUM", "LOW", "UNASSESSED"];
export const CONFIDENCE_FILTER_OPTIONS = ["ALL", ...ALLOWED_CONFIDENCE_LEVELS];

/**
 * Normalizes any confidence input to one of the four standard levels.
 * Consistent with ConfidenceBadge and backend persistence rules:
 * Missing, null, undefined, empty, or unsupported values resolve safely to UNASSESSED.
 *
 * @param {any} confidence
 * @returns {"HIGH" | "MEDIUM" | "LOW" | "UNASSESSED"}
 */
export function normalizeConfidence(confidence) {
  if (typeof confidence !== "string") {
    return "UNASSESSED";
  }
  const clean = confidence.trim().toUpperCase();
  if (clean === "HIGH" || clean === "MEDIUM" || clean === "LOW") {
    return clean;
  }
  return "UNASSESSED";
}

/**
 * Checks whether an item's confidence matches a selected confidence filter.
 *
 * @param {Object} item - Candidate item or saved task object
 * @param {string} selectedConfidence - "ALL" | "HIGH" | "MEDIUM" | "LOW" | "UNASSESSED"
 * @returns {boolean}
 */
export function matchesConfidence(item, selectedConfidence) {
  if (!selectedConfidence || typeof selectedConfidence !== "string") {
    return true;
  }
  const filterKey = selectedConfidence.trim().toUpperCase();
  if (filterKey === "ALL" || !filterKey) {
    return true;
  }
  const itemConfidence = normalizeConfidence(item?.confidence);
  return itemConfidence === filterKey;
}

/**
 * Filters an array of items by confidence level without mutating the original array or objects.
 *
 * @param {Array} items
 * @param {string} selectedConfidence
 * @returns {Array} New filtered array
 */
export function filterByConfidence(items, selectedConfidence) {
  if (!Array.isArray(items)) {
    return [];
  }
  if (!selectedConfidence || selectedConfidence.trim().toUpperCase() === "ALL") {
    return [...items];
  }
  const filterKey = selectedConfidence.trim().toUpperCase();
  return items.filter((item) => normalizeConfidence(item?.confidence) === filterKey);
}

/**
 * Pure evaluation function combining all saved-task filter criteria:
 * search, category, status, confidence, due_before, due_after.
 *
 * @param {Object} task
 * @param {Object} filters
 * @returns {boolean}
 */
export function matchesTaskFilters(task, filters = {}) {
  if (!task || typeof task !== "object") {
    return false;
  }

  // 1. Confidence filter
  if (filters.confidence && !matchesConfidence(task, filters.confidence)) {
    return false;
  }

  // 2. Category filter
  if (filters.category && filters.category !== "ALL" && task.category !== filters.category) {
    return false;
  }

  // 3. Status filter
  if (
    filters.status &&
    filters.status !== "ALL" &&
    (task.status || "").toLowerCase() !== filters.status.toLowerCase()
  ) {
    return false;
  }

  // 4. Search keyword filter (title, description, source_text, source_sender)
  if (filters.search && typeof filters.search === "string" && filters.search.trim()) {
    const query = filters.search.toLowerCase().trim();
    const inTitle = (task.title || "").toLowerCase().includes(query);
    const inDesc = (task.description || "").toLowerCase().includes(query);
    const inSource = (task.source_text || "").toLowerCase().includes(query);
    const inSender = (task.source_sender || "").toLowerCase().includes(query);
    if (!inTitle && !inDesc && !inSource && !inSender) {
      return false;
    }
  }

  // 5. Date range filter
  if (filters.due_before) {
    if (!task.due_date || task.due_date > filters.due_before) {
      return false;
    }
  }

  if (filters.due_after) {
    if (!task.due_date || task.due_date < filters.due_after) {
      return false;
    }
  }

  return true;
}

/**
 * Pure filter function for a list of saved tasks combining all criteria.
 * Non-mutating.
 *
 * @param {Array} tasks
 * @param {Object} filters
 * @returns {Array} New filtered array
 */
export function filterTasks(tasks, filters = {}) {
  if (!Array.isArray(tasks)) {
    return [];
  }
  return tasks.filter((t) => matchesTaskFilters(t, filters));
}
