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

export const ALLOWED_PRIORITY_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
export const ALLOWED_IMPORTANCE_LEVELS = ["HIGH", "MEDIUM", "LOW", "UNASSESSED"];
export const ALLOWED_URGENCY_LEVELS = [
  "CRITICAL",
  "HIGH",
  "MEDIUM",
  "LOW",
  "NO_DEADLINE",
  "NEEDS_REVIEW",
];
export const ALLOWED_ACADEMIC_INTENTS = [
  "assignment",
  "exam",
  "laboratory",
  "project",
  "seminar",
  "attendance",
  "scholarship",
  "placement",
  "competition",
  "workshop",
  "administrative",
  "academic_announcement",
];

export const ALLOWED_SOURCE_TYPES = ["whatsapp", "gmail", "google_classroom", "manual"];
export const SOURCE_TYPE_OPTIONS = ["ALL", ...ALLOWED_SOURCE_TYPES];

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

  // 6. Priority filter
  if (filters.priority && filters.priority !== "ALL") {
    if ((task.priority || "").toUpperCase() !== filters.priority.toUpperCase()) {
      return false;
    }
  }

  // 7. Urgency filter
  if (filters.urgency && filters.urgency !== "ALL") {
    if ((task.urgency || "").toUpperCase() !== filters.urgency.toUpperCase()) {
      return false;
    }
  }

  // 8. Importance filter
  if (filters.importance && filters.importance !== "ALL") {
    if ((task.importance || "").toUpperCase() !== filters.importance.toUpperCase()) {
      return false;
    }
  }

  // 9. Academic Intent filter
  if (filters.academic_intent && filters.academic_intent !== "ALL") {
    if ((task.academic_intent || "").toLowerCase() !== filters.academic_intent.toLowerCase()) {
      return false;
    }
  }

  // 10. Review Required filter
  if (filters.review_required && filters.review_required !== "ALL") {
    const wantsReview = filters.review_required === "NEEDS_REVIEW" || filters.review_required === true;
    if (Boolean(task.review_required) !== wantsReview) {
      return false;
    }
  }

  // 11. Section filter
  if (filters.section && filters.section !== "all") {
    if (!taskMatchesSection(task, filters.section, filters.todayStr)) {
      return false;
    }
  }

  // 12. Source Type filter
  if (filters.source_type && filters.source_type !== "ALL") {
    const taskSource = (task.source_type || "whatsapp").toLowerCase();
    if (taskSource !== filters.source_type.toLowerCase()) {
      return false;
    }
  }

  return true;
}

/**
 * Checks whether an academic task belongs to a specific dashboard section.
 *
 * Sections:
 * - 'today': Active tasks overdue or due today
 * - 'upcoming': Active tasks with future deadlines
 * - 'high_priority': Active tasks with CRITICAL or HIGH priority
 * - 'needs_review': Tasks requiring review, ambiguous dates, or low confidence
 * - 'completed_archived': Tasks with status completed, cancelled, superseded, or dismissed
 * - 'all': All tasks
 *
 * @param {Object} task
 * @param {string} section
 * @param {string} [todayStr] - Reference date 'YYYY-MM-DD'
 * @returns {boolean}
 */
export function taskMatchesSection(task, section, todayStr) {
  if (!task) return false;
  const status = (task.status || "pending").toLowerCase();
  const isArchived = ["completed", "cancelled", "superseded", "dismissed"].includes(status);

  if (section === "all" || !section) {
    return true;
  }

  if (section === "completed_archived") {
    return isArchived;
  }

  // Inactive tasks do not appear in active obligation sections
  if (isArchived) {
    return false;
  }

  const isOverdue =
    (task.urgency === "CRITICAL" &&
      (task.delta_days < 0 ||
        (Array.isArray(task.urgency_reasons) &&
          task.urgency_reasons.some((r) => r.toLowerCase().includes("overdue"))))) ||
    (Boolean(task.due_date) && Boolean(todayStr) && task.due_date < todayStr);

  const isDueToday =
    (task.urgency === "CRITICAL" && task.delta_days === 0) ||
    (Boolean(task.due_date) && Boolean(todayStr) && task.due_date === todayStr);

  if (section === "today") {
    return isOverdue || isDueToday;
  }

  if (section === "upcoming") {
    return Boolean(
      task.due_date &&
        (!todayStr || task.due_date > todayStr) &&
        (task.delta_days === undefined || task.delta_days > 0)
    );
  }

  if (section === "high_priority") {
    return task.priority === "CRITICAL" || task.priority === "HIGH";
  }

  if (section === "needs_review") {
    return (
      Boolean(task.review_required) ||
      task.date_status === "needs_review" ||
      task.urgency === "NEEDS_REVIEW" ||
      task.confidence === "LOW"
    );
  }

  return true;
}

/**
 * Calculates academic dashboard metrics from saved tasks.
 * Ensures inactive tasks (cancelled, superseded, dismissed) are separated from active obligations.
 *
 * @param {Array} tasks
 * @param {string} [todayStr]
 * @returns {Object} Dashboard summary statistics
 */
export function calculateDashboardStats(tasks, todayStr) {
  if (!Array.isArray(tasks)) {
    return {
      total: 0,
      active: 0,
      pending: 0,
      completed: 0,
      cancelled: 0,
      superseded: 0,
      dismissed: 0,
      dueToday: 0,
      overdue: 0,
      upcoming: 0,
      highPriority: 0,
      needsReview: 0,
      deadlines: 0,
      attentionRequired: 0,
      categoryCounts: {},
      priorityCounts: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 },
      intentCounts: {},
      sourceTypeCounts: { whatsapp: 0, gmail: 0, google_classroom: 0, manual: 0 },
    };
  }

  const categoryCounts = {};
  const priorityCounts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
  const intentCounts = {};
  const sourceTypeCounts = { whatsapp: 0, gmail: 0, google_classroom: 0, manual: 0 };

  let total = tasks.length;
  let pending = 0;
  let completed = 0;
  let cancelled = 0;
  let superseded = 0;
  let dismissed = 0;
  let dueToday = 0;
  let overdue = 0;
  let upcoming = 0;
  let highPriority = 0;
  let needsReview = 0;
  let deadlines = 0;

  for (const t of tasks) {
    const status = (t.status || "pending").toLowerCase();
    if (status === "pending") pending++;
    else if (status === "completed") completed++;
    else if (status === "cancelled") cancelled++;
    else if (status === "superseded") superseded++;
    else if (status === "dismissed") dismissed++;

    const isArchived = ["completed", "cancelled", "superseded", "dismissed"].includes(status);

    const st = (t.source_type || "whatsapp").toLowerCase();
    if (sourceTypeCounts[st] !== undefined) {
      sourceTypeCounts[st]++;
    } else {
      sourceTypeCounts[st] = 1;
    }

    if (t.category) {
      categoryCounts[t.category] = (categoryCounts[t.category] || 0) + 1;
    }
    if (t.academic_intent) {
      intentCounts[t.academic_intent] = (intentCounts[t.academic_intent] || 0) + 1;
    }
    if (t.priority && priorityCounts[t.priority.toUpperCase()] !== undefined) {
      priorityCounts[t.priority.toUpperCase()]++;
    }

    // Active-only metrics to prevent inactive tasks from being counted as obligations
    if (!isArchived) {
      const isOvd =
        (t.urgency === "CRITICAL" &&
          (t.delta_days < 0 ||
            (Array.isArray(t.urgency_reasons) &&
              t.urgency_reasons.some((r) => r.toLowerCase().includes("overdue"))))) ||
        (Boolean(t.due_date) && Boolean(todayStr) && t.due_date < todayStr);

      const isToday =
        (t.urgency === "CRITICAL" && t.delta_days === 0) ||
        (Boolean(t.due_date) && Boolean(todayStr) && t.due_date === todayStr);

      if (isOvd) overdue++;
      if (isToday) dueToday++;
      if (
        t.due_date &&
        (!todayStr || t.due_date > todayStr) &&
        (t.delta_days === undefined || t.delta_days > 0)
      ) {
        upcoming++;
      }
      if (t.priority === "CRITICAL" || t.priority === "HIGH") {
        highPriority++;
      }
      if (
        Boolean(t.review_required) ||
        t.date_status === "needs_review" ||
        t.urgency === "NEEDS_REVIEW" ||
        t.confidence === "LOW"
      ) {
        needsReview++;
      }
      if (t.due_date && (t.date_type || "").toLowerCase() === "deadline") {
        deadlines++;
      }
    }
  }

  const active = pending;
  const attentionRequired = overdue + dueToday + needsReview;

  return {
    total,
    active,
    pending,
    completed,
    cancelled,
    superseded,
    dismissed,
    dueToday,
    overdue,
    upcoming,
    highPriority,
    needsReview,
    deadlines,
    attentionRequired,
    categoryCounts,
    priorityCounts,
    intentCounts,
    sourceTypeCounts,
  };
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
