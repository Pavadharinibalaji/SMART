import { useState, useEffect, useId, useMemo, useCallback } from "react";
import "./App.css";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import ConfidenceBadge from "./components/ConfidenceBadge";
import ReviewIndicator from "./components/ReviewIndicator";
import EvidenceDrawer from "./components/EvidenceDrawer";
import EditTaskModal from "./components/EditTaskModal";
import TaskRelationshipsModal from "./components/TaskRelationshipsModal";
import DashboardOverview from "./components/DashboardOverview";
import LoginPage from "./components/LoginPage";
import OpportunityExplorer from "./components/OpportunityExplorer";
import OpportunityTrackingModal from "./components/OpportunityTrackingModal";
import ClassroomProgress from "./components/ClassroomProgress";
import StudyMaterialsView from "./components/StudyMaterialsView";
import TeacherDashboard from "./components/TeacherDashboard";
import CoursesView from "./components/CoursesView";
import CommunicationView from "./components/CommunicationView";
import AnnouncementsView from "./components/AnnouncementsView";
import PollsView from "./components/PollsView";
import NotificationsCenter from "./components/NotificationsCenter";
import AnalyticsView from "./components/AnalyticsView";
import {
  matchesConfidence,
  matchesTaskFilters,
  calculateDashboardStats,
  ALLOWED_ACADEMIC_INTENTS,
} from "./utils/confidenceFilter";
import {
  extractAcademic,
  extractAcademicFromSource,
  saveAcademicItem,
  getAcademicItems,
  updateAcademicItem,
  updateAcademicItemStatus,
  deleteAcademicItem,
  getExportIcsUrl,
  getGoogleAuthUrl,
  getGoogleAuthStatus,
  disconnectGoogleAccount,
  toggleDemoData,
  syncGmail,
  syncClassroom,
  getOpportunities,
  updateStudentOpportunityStatus,
  getTeacherOpportunitiesOverview,
  getClassroomCourses,
  getClassroomCoursework,
  getClassroomSubmissions,
  getTeacherCourseworkOverview,
  getStudyMaterials,
  loginUser,
  getCurrentUser,
  logoutUser,
  markTaskReviewed,
  getUnreadMessageCount,
  getUnreadNotificationCount,
} from "./api";

const CATEGORY_COLORS = {
  Assignment: { bg: "#eff6ff", text: "#1d4ed8", border: "#bfdbfe" },
  Exam: { bg: "#fff1f2", text: "#be123c", border: "#fecdd3" },
  Announcement: { bg: "#f1f5f9", text: "#334155", border: "#cbd5e1" },
  Opportunity: { bg: "#fef3c7", text: "#92400e", border: "#fcd34d" },
  Event: { bg: "#ecfdf5", text: "#047857", border: "#a7f3d0" },
};

function getTodayIsoString() {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatSourceLabel(sourceType) {
  const s = (sourceType || "whatsapp").toLowerCase();
  switch (s) {
    case "gmail":
      return "✉️ Gmail";
    case "google_classroom":
      return "🏫 Classroom";
    case "manual":
      return "✍️ Manual";
    case "whatsapp":
    default:
      return "💬 WhatsApp";
  }
}

export default function App() {
  // Navigation: "dashboard" | "tasks" | "analyze"
  const [activeTab, setActiveTab] = useState("dashboard");

  // Chat analysis state
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [items, setItems] = useState([]);
  const [filename, setFilename] = useState("");
  const [totalMessages, setTotalMessages] = useState(0);
  const [reviewCount, setReviewCount] = useState(0);
  const [categoryCounts, setCategoryCounts] = useState({});
  const [selectedFilter, setSelectedFilter] = useState("ALL");
  const [candidateConfidence, setCandidateConfidence] = useState("ALL");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Track save status for candidate cards: { [cardIndex]: { status: 'idle'|'saving'|'saved'|'error', message?: string, savedId?: number } }
  const [saveStatusMap, setSaveStatusMap] = useState({});

  // Saved tasks state
  const [savedTasks, setSavedTasks] = useState([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState("");
  const [updatingTaskId, setUpdatingTaskId] = useState(null);

  // Section and Task filtering state
  const [taskSection, setTaskSection] = useState("all");
  const [taskSearch, setTaskSearch] = useState("");
  const [taskCategory, setTaskCategory] = useState("ALL");
  const [taskStatus, setTaskStatus] = useState("ALL");
  const [taskConfidence, setTaskConfidence] = useState("ALL");
  const [taskPriority, setTaskPriority] = useState("ALL");
  const [taskUrgency, setTaskUrgency] = useState("ALL");
  const [taskImportance, setTaskImportance] = useState("ALL");
  const [taskIntent, setTaskIntent] = useState("ALL");
  const [taskReview, setTaskReview] = useState("ALL");
  const [taskDueBefore, setTaskDueBefore] = useState("");
  const [taskDueAfter, setTaskDueAfter] = useState("");
  const [taskSourceType, setTaskSourceType] = useState("ALL");

  // Multi-source chat/message input state (Phase 4.5)
  const [inputSource, setInputSource] = useState("whatsapp"); // 'whatsapp' | 'gmail' | 'google_classroom' | 'manual'
  const [manualText, setManualText] = useState("");

  // SMART 2.1 - Authenticated User & Google State
  const [currentUser, setCurrentUser] = useState(null);
  const [authState, setAuthState] = useState("checking"); // 'checking' | 'authenticated' | 'unauthenticated'
  const [googleAccount, setGoogleAccount] = useState({ connected: false });
  const [googleLoading, setGoogleLoading] = useState(false);
  const [googleError, setGoogleError] = useState("");

  // SMART 2.1 - Academic Data States
  const [opportunities, setOpportunities] = useState([]);
  const [classroomCourses, setClassroomCourses] = useState([]);
  const [classroomCoursework, setClassroomCoursework] = useState([]);
  const [classroomSubmissions, setClassroomSubmissions] = useState([]);
  const [classroomLoading, setClassroomLoading] = useState(false);
  const [studyMaterials, setStudyMaterials] = useState([]);
  const [teacherOverview, setTeacherOverview] = useState({ coursework: [], opportunities: [] });

  // SMART 3.0 - Collaboration & Notification Counters
  const [activeCourseChatId, setActiveCourseChatId] = useState(null);
  const [unreadMessagesCount, setUnreadMessagesCount] = useState(0);
  const [unreadNotificationsCount, setUnreadNotificationsCount] = useState(0);

  const currentEmail = currentUser?.email || "";
  const userRole = currentUser?.role || "student";

  // Modals & Notifications
  const [deleteModalItem, setDeleteModalItem] = useState(null);
  const [selectedEvidenceItem, setSelectedEvidenceItem] = useState(null);
  const [editModalTask, setEditModalTask] = useState(null);
  const [relationshipsModalTask, setRelationshipsModalTask] = useState(null);
  const [trackingModalData, setTrackingModalData] = useState(null);
  const [showTrackingModal, setShowTrackingModal] = useState(false);
  const [exportNotice, setExportNotice] = useState("");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const fileInputId = useId();
  const todayStr = useMemo(() => getTodayIsoString(), []);

  // Load saved tasks from backend
  const loadSavedTasks = useCallback(async () => {
    setTasksLoading(true);
    setTasksError("");
    try {
      const data = await getAcademicItems();
      setSavedTasks(data);
    } catch (err) {
      setTasksError(err.message || "Failed to load saved tasks from database.");
    } finally {
      setTasksLoading(false);
    }
  }, []);

  // Fetch Google Auth Status
  const loadGoogleStatus = useCallback(async () => {
    try {
      const status = await getGoogleAuthStatus(currentEmail, userRole);
      setGoogleAccount(status);
    } catch {
      setGoogleAccount({ connected: false });
    }
  }, [currentEmail, userRole]);

  // Fetch Opportunities
  const loadOpportunities = useCallback(async () => {
    try {
      const data = await getOpportunities(currentEmail, userRole);
      setOpportunities(data);
    } catch (err) {
      console.error("Failed to load opportunities:", err);
    }
  }, [currentEmail, userRole]);

  // Fetch Classroom Data
  const loadClassroomData = useCallback(async () => {
    setClassroomLoading(true);
    try {
      const [courses, coursework, subs] = await Promise.all([
        getClassroomCourses(currentEmail, userRole),
        getClassroomCoursework(null, currentEmail, userRole),
        getClassroomSubmissions(null, currentEmail, userRole),
      ]);
      setClassroomCourses(courses);
      setClassroomCoursework(coursework);
      setClassroomSubmissions(subs);
    } catch (err) {
      console.error("Failed to load classroom data:", err);
    } finally {
      setClassroomLoading(false);
    }
  }, [currentEmail, userRole]);

  // Fetch Study Materials
  const loadMaterials = useCallback(async () => {
    try {
      const mats = await getStudyMaterials(null, currentEmail, userRole);
      setStudyMaterials(mats);
    } catch (err) {
      console.error("Failed to load materials:", err);
    }
  }, [currentEmail, userRole]);

  // Fetch Teacher Overview
  const loadTeacherOverview = useCallback(async () => {
    if (userRole !== "teacher") return;
    try {
      const [cw, opp] = await Promise.all([
        getTeacherCourseworkOverview(userRole, currentEmail),
        getTeacherOpportunitiesOverview(userRole),
      ]);
      setTeacherOverview({ coursework: cw, opportunities: opp });
    } catch (err) {
      console.error("Failed to load teacher overview:", err);
    }
  }, [currentEmail, userRole]);

  // Check existing session on mount
  useEffect(() => {
    async function checkAuth() {
      setAuthState("checking");
      try {
        const user = await getCurrentUser();
        if (user) {
          setCurrentUser(user);
          setAuthState("authenticated");
        } else {
          setCurrentUser(null);
          setAuthState("unauthenticated");
        }
      } catch {
        setCurrentUser(null);
        setAuthState("unauthenticated");
      }
    }
    checkAuth();
  }, []);

  // Login handler with authoritative verification via /api/auth/me
  const handleLogin = async (email, idToken = null) => {
    setAuthState("checking");
    try {
      await loginUser(email, idToken);
      const verifiedUser = await getCurrentUser();
      if (!verifiedUser) {
        throw new Error("Session verification failed after login.");
      }
      setCurrentUser(verifiedUser);
      setAuthState("authenticated");
      setActiveTab("dashboard");
    } catch (err) {
      setCurrentUser(null);
      setAuthState("unauthenticated");
      throw err;
    }
  };

  // Logout handler
  const handleLogout = async () => {
    try {
      await logoutUser();
    } catch {
      // quiet ignore
    }
    setCurrentUser(null);
    setAuthState("unauthenticated");
    setUnreadMessagesCount(0);
    setUnreadNotificationsCount(0);
    setActiveTab("dashboard");
  };

  // Refresh unread counters for SMART 3.0
  // Transient counter failures are handled independently and NEVER invalidate a valid SMART session
  const refreshCounters = useCallback(async () => {
    if (!currentUser || authState !== "authenticated") return;
    try {
      const [msgRes, notifRes] = await Promise.all([
        getUnreadMessageCount().catch(() => ({ unread_count: 0 })),
        getUnreadNotificationCount().catch(() => ({ unread_count: 0 })),
      ]);
      setUnreadMessagesCount(msgRes?.unread_count || 0);
      setUnreadNotificationsCount(notifRes?.unread_count || 0);
    } catch {
      // Counter fetch failure does not alter session state
    }
  }, [currentUser, authState]);

  // Initial and reactive load
  useEffect(() => {
    if (!currentUser || authState !== "authenticated") return;
    loadSavedTasks();
    loadGoogleStatus();
    loadOpportunities();
    loadClassroomData();
    loadMaterials();
    if (userRole === "teacher") {
      loadTeacherOverview();
    }

    refreshCounters();
    const interval = setInterval(refreshCounters, 20000);
    return () => clearInterval(interval);
  }, [currentUser, authState, refreshCounters, loadSavedTasks, loadGoogleStatus, loadOpportunities, loadClassroomData, loadMaterials, loadTeacherOverview, userRole]);

  // Check post-OAuth redirect query params on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const authSuccess = params.get("google_auth_success");
    const authError = params.get("google_auth_error");

    if (authSuccess) {
      setSuccess("Google Account successfully connected!");
      getCurrentUser()
        .then((user) => {
          if (user && user.email) {
            setCurrentUser(user);
            setUserRole(user.role || "student");
            setAuthState("authenticated");
          }
        })
        .catch(() => {});
      loadGoogleStatus();
      // Clean up query string from browser URL bar without reloading
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (authError) {
      setGoogleError(decodeURIComponent(authError));
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, [loadGoogleStatus]);

  // Handlers for SMART 2.1
  const handleConnectGoogle = async () => {
    try {
      setGoogleLoading(true);
      setGoogleError("");
      const res = await getGoogleAuthUrl(userRole);
      if (res.auth_url) {
        window.location.href = res.auth_url;
      }
    } catch (err) {
      setGoogleError(err.message || "Failed to start Google OAuth flow.");
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleDisconnectGoogle = async () => {
    try {
      await disconnectGoogleAccount(currentEmail, userRole);
      await loadGoogleStatus();
    } catch (err) {
      setGoogleError(err.message || "Failed to disconnect account.");
    }
  };

  const handleToggleDemoData = async () => {
    try {
      setGoogleLoading(true);
      await toggleDemoData(currentEmail, userRole, !googleAccount?.is_demo);
      await Promise.all([
        loadGoogleStatus(),
        loadOpportunities(),
        loadClassroomData(),
        loadMaterials(),
        userRole === "teacher" ? loadTeacherOverview() : Promise.resolve(),
      ]);
    } catch (err) {
      setGoogleError(err.message || "Failed to switch demo mode.");
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleSyncGmail = async () => {
    setGoogleLoading(true);
    setGoogleError("");
    try {
      await syncGmail(currentEmail, userRole);
      await Promise.all([
        loadOpportunities(),
        loadMaterials(),
        loadSavedTasks(),
      ]);
      setSuccess("Gmail messages, opportunities, and attachments synchronized successfully.");
    } catch (err) {
      setGoogleError(err.message || "Failed to sync Gmail.");
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleSyncClassroom = async () => {
    setClassroomLoading(true);
    setGoogleError("");
    try {
      await syncClassroom(currentEmail, userRole);
      await Promise.all([
        loadClassroomData(),
        loadMaterials(),
        userRole === "teacher" ? loadTeacherOverview() : Promise.resolve(),
      ]);
      setSuccess("Classroom coursework, submissions, and course materials synchronized.");
    } catch (err) {
      setGoogleError(err.message || "Failed to sync Classroom.");
    } finally {
      setClassroomLoading(false);
    }
  };

  const handleUpdateOpportunityStatus = async (oppId, newStatus) => {
    try {
      await updateStudentOpportunityStatus(oppId, newStatus, currentEmail, userRole);
      await loadOpportunities();
      if (userRole === "teacher") {
        await loadTeacherOverview();
      }
    } catch (err) {
      setError(err.message || "Failed to update opportunity registration status.");
    }
  };

  // Handle uploaded file selection
  const handleSelectedFile = (selectedFile) => {
    setError("");
    setSuccess("");
    setItems([]);
    setSaveStatusMap({});
    setFilename("");
    setTotalMessages(0);
    setReviewCount(0);
    setCategoryCounts({});

    if (!selectedFile) {
      setFile(null);
      return;
    }

    if (!selectedFile.name.toLowerCase().endsWith(".txt")) {
      setError("Please select a WhatsApp chat export in .txt format.");
      setFile(null);
      return;
    }

    if (selectedFile.size > 5 * 1024 * 1024) {
      setError("The file is too large. Maximum supported size is 5 MB.");
      setFile(null);
      return;
    }

    if (selectedFile.size === 0) {
      setError("The selected file is empty. Please choose a valid WhatsApp export.");
      setFile(null);
      return;
    }

    setFile(selectedFile);
  };

  const handleFileInputChange = (event) => {
    const selected = event.target.files?.[0] ?? null;
    handleSelectedFile(selected);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile) {
      handleSelectedFile(droppedFile);
    }
  };

  // Upload and parse chat
  const handleUpload = async (event) => {
    event.preventDefault();

    if (!file) {
      setError("Please choose a WhatsApp .txt file first.");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");
    setSaveStatusMap({});

    try {
      const data = await extractAcademic(file);
      setFilename(data.filename || file.name);
      setTotalMessages(data.total_messages ?? 0);
      const extractedItems = Array.isArray(data.items) ? data.items : [];
      setItems(extractedItems);
      setReviewCount(
        data.review_required_count ??
          extractedItems.filter((i) => i.review_required).length
      );
      setCategoryCounts(data.category_counts ?? {});
      setSelectedFilter("ALL");
      setCandidateConfidence("ALL");
      setSuccess("Chat processed and candidate items identified successfully.");

      // Check if any candidate item was already saved in previous sessions
      const initialSaveStatus = {};
      extractedItems.forEach((cand, idx) => {
        const found = savedTasks.find(
          (t) =>
            (t.source_text || "").trim() === (cand.source_text || "").trim() &&
            t.category === cand.category &&
            (t.source_sender || "").trim() === (cand.source_sender || "").trim() &&
            (t.source_timestamp || "").trim() === (cand.source_timestamp || "").trim()
        );
        if (found) {
          initialSaveStatus[idx] = {
            status: "saved",
            savedId: found.id,
            message: `Already saved as Task #${found.id}`,
          };
        }
      });
      setSaveStatusMap(initialSaveStatus);
    } catch (err) {
      if (err instanceof TypeError) {
        setError(
          "Could not connect to the SMART backend. Make sure the FastAPI service is running at http://localhost:8000."
        );
      } else {
        setError(err.message || "Something went wrong while processing the chat.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setItems([]);
    setSaveStatusMap({});
    setFilename("");
    setTotalMessages(0);
    setReviewCount(0);
    setCategoryCounts({});
    setSelectedFilter("ALL");
    setError("");
    setSuccess("");

    const input = document.getElementById(fileInputId);
    if (input) input.value = "";
  };

  // Analyze manual text input (Phase 4.5)
  const handleManualExtract = async (event) => {
    event.preventDefault();
    if (!manualText.trim()) {
      setError("Please enter or paste communication text to analyze.");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");
    setSaveStatusMap({});

    try {
      const data = await extractAcademicFromSource({
        source_type: "manual",
        raw_text: manualText.trim(),
        sender: "Manual Note",
      });
      setFilename("Manual Note");
      setTotalMessages(data.total_messages ?? 1);
      const extractedItems = Array.isArray(data.items) ? data.items : [];
      setItems(extractedItems);
      setReviewCount(
        data.review_required_count ??
          extractedItems.filter((i) => i.review_required).length
      );
      setCategoryCounts(data.category_counts ?? {});
      setSelectedFilter("ALL");
      setCandidateConfidence("ALL");
      setSuccess("Manual text analyzed and candidate items identified successfully.");
    } catch (err) {
      setError(err.message || "Something went wrong while analyzing manual text.");
    } finally {
      setLoading(false);
    }
  };

  // Save a candidate item to database
  const handleSaveCandidate = async (candidate, index) => {
    setSaveStatusMap((prev) => ({
      ...prev,
      [index]: { status: "saving" },
    }));

    try {
      const payload = {
        title: candidate.title,
        category: candidate.category,
        description: candidate.source_text,
        date_text: candidate.date_text,
        due_date: candidate.due_date,
        date_type: candidate.date_type,
        date_status: candidate.date_status,
        status: "pending",
        source_sender: candidate.source_sender,
        source_timestamp: candidate.source_timestamp,
        source_text: candidate.source_text,
        source_filename: filename || file?.name || "",
        source_type: candidate.source_type || inputSource || "whatsapp",
        source_id: candidate.source_id || null,
        source_metadata: candidate.source_metadata || null,
        review_required: candidate.review_required,
        review_reasons: candidate.review_reasons,
        evidence_text: candidate.evidence_text,
        evidence_start_index: candidate.evidence_start_index,
        evidence_end_index: candidate.evidence_end_index,
        candidate_token: candidate.candidate_token,
        is_actionable: candidate.is_actionable !== undefined ? candidate.is_actionable : true,
        actionability_type: candidate.actionability_type || "action_required",
        update_type: candidate.update_type || null,
        is_range: candidate.is_range !== undefined ? candidate.is_range : false,
        previous_due_date: candidate.previous_due_date || null,
        replaces_task_id: candidate.replaces_task_id || null,
        importance: candidate.importance || "UNASSESSED",
        academic_intent: candidate.academic_intent || null,
      };

      const saved = await saveAcademicItem(payload);

      setSaveStatusMap((prev) => ({
        ...prev,
        [index]: {
          status: "saved",
          savedId: saved.id,
          message: `Saved as Task #${saved.id}`,
        },
      }));

      // Refresh tasks list
      await loadSavedTasks();
    } catch (err) {
      if (err.status === 409) {
        // Duplicate save handled gracefully
        setSaveStatusMap((prev) => ({
          ...prev,
          [index]: {
            status: "saved",
            message: err.message || "Already saved to tasks",
          },
        }));
      } else {
        setSaveStatusMap((prev) => ({
          ...prev,
          [index]: {
            status: "error",
            message: err.message || "Failed to save item.",
          },
        }));
      }
    }
  };

  // Update task status (Pending, Completed, Dismissed)
  const handleUpdateStatus = async (taskId, newStatus) => {
    setUpdatingTaskId(taskId);
    setTasksError("");
    try {
      const updated = await updateAcademicItemStatus(taskId, newStatus);
      setSavedTasks((prev) =>
        prev.map((t) => (t.id === taskId ? updated : t))
      );
    } catch (err) {
      setTasksError(err.message || "Failed to update task status.");
    } finally {
      setUpdatingTaskId(null);
    }
  };

  // Review and confirm task (clears review_required, sets status)
  const handleMarkReviewed = async (taskId, newStatus = "pending") => {
    setUpdatingTaskId(taskId);
    setTasksError("");
    try {
      const updated = await markTaskReviewed(taskId, newStatus);
      setSavedTasks((prev) =>
        prev.map((t) => (t.id === taskId ? updated : t))
      );
      if (selectedEvidenceItem && selectedEvidenceItem.id === taskId) {
        setSelectedEvidenceItem(updated);
      }
    } catch (err) {
      setTasksError(err.message || "Failed to mark task as reviewed.");
    } finally {
      setUpdatingTaskId(null);
    }
  };

  // Update task via edit modal
  const handleEditSave = async (updates) => {
    if (!editModalTask) return;
    const taskId = editModalTask.id;
    setTasksError("");
    const updated = await updateAcademicItem(taskId, updates);
    setSavedTasks((prev) =>
      prev.map((t) => (t.id === taskId ? updated : t))
    );
    setEditModalTask(null);
  };

  const handleNavigateToSection = (sec) => {
    setTaskSection(sec);
    setActiveTab("tasks");
  };

  // Delete task after confirmation
  const handleConfirmDelete = async () => {
    if (!deleteModalItem) return;
    const itemId = deleteModalItem.id;
    setTasksError("");

    try {
      await deleteAcademicItem(itemId);
      setSavedTasks((prev) => prev.filter((t) => t.id !== itemId));
      setDeleteModalItem(null);

      // Also reset save status in candidate view if matched
      setSaveStatusMap((prev) => {
        const next = { ...prev };
        Object.keys(next).forEach((key) => {
          if (next[key]?.savedId === itemId) {
            delete next[key];
          }
        });
        return next;
      });
    } catch (err) {
      setTasksError(err.message || `Failed to delete task #${itemId}.`);
      setDeleteModalItem(null);
    }
  };

  // Export deadlines button click
  const handleExportDeadlines = () => {
    const deadlineCount = savedTasks.filter(
      (t) =>
        t.due_date &&
        (t.date_type || "").toLowerCase() === "deadline" &&
        !["completed", "cancelled", "superseded", "dismissed"].includes((t.status || "").toLowerCase())
    ).length;

    if (deadlineCount === 0) {
      setExportNotice(
        "No confirmed active deadlines available to export. Deadlines must be active and have date type 'deadline'."
      );
      return;
    }

    // Trigger download of .ics file
    window.location.href = getExportIcsUrl();
  };

  // Filtered candidate items (Analyze Chat tab)
  const filteredCandidateItems = useMemo(() => {
    return items.filter((item) => {
      // Category / Review filter
      if (selectedFilter === "REVIEW" && !item.review_required) return false;
      if (selectedFilter !== "ALL" && selectedFilter !== "REVIEW" && item.category !== selectedFilter) return false;

      // Confidence filter
      if (!matchesConfidence(item, candidateConfidence)) return false;

      return true;
    });
  }, [items, selectedFilter, candidateConfidence]);

  // Overall dashboard statistics
  const dashboardStats = useMemo(() => {
    return calculateDashboardStats(savedTasks, todayStr);
  }, [savedTasks, todayStr]);

  // Filtered saved tasks (My Academic Tasks tab)
  const filteredTasks = useMemo(() => {
    return savedTasks.filter((task) =>
      matchesTaskFilters(task, {
        search: taskSearch,
        category: taskCategory,
        status: taskStatus,
        confidence: taskConfidence,
        priority: taskPriority,
        urgency: taskUrgency,
        importance: taskImportance,
        academic_intent: taskIntent,
        review_required: taskReview,
        due_before: taskDueBefore,
        due_after: taskDueAfter,
        section: taskSection,
        source_type: taskSourceType,
        todayStr,
      })
    );
  }, [
    savedTasks,
    taskSearch,
    taskCategory,
    taskStatus,
    taskConfidence,
    taskPriority,
    taskUrgency,
    taskImportance,
    taskIntent,
    taskReview,
    taskDueBefore,
    taskDueAfter,
    taskSection,
    taskSourceType,
    todayStr,
  ]);

  const hasActiveTaskFilters =
    taskSearch !== "" ||
    taskCategory !== "ALL" ||
    taskStatus !== "ALL" ||
    taskConfidence !== "ALL" ||
    taskPriority !== "ALL" ||
    taskUrgency !== "ALL" ||
    taskImportance !== "ALL" ||
    taskIntent !== "ALL" ||
    taskReview !== "ALL" ||
    taskSourceType !== "ALL" ||
    taskDueBefore !== "" ||
    taskDueAfter !== "" ||
    taskSection !== "all";

  const handleClearTaskFilters = () => {
    setTaskSearch("");
    setTaskCategory("ALL");
    setTaskStatus("ALL");
    setTaskConfidence("ALL");
    setTaskPriority("ALL");
    setTaskUrgency("ALL");
    setTaskImportance("ALL");
    setTaskIntent("ALL");
    setTaskReview("ALL");
    setTaskSourceType("ALL");
    setTaskDueBefore("");
    setTaskDueAfter("");
    setTaskSection("all");
  };

  if (authState === "checking") {
    return (
      <div className="auth-loading-screen">
        <div className="auth-spinner" aria-hidden="true" />
        <p>Verifying SMART academic session...</p>
      </div>
    );
  }

  if (authState !== "authenticated" || !currentUser) {
    return <LoginPage onLoginSuccess={handleLogin} />;
  }

  return (
    <div className="saas-app-layout">
      {/* SaaS Purple Gradient Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={(tab) => {
          setActiveTab(tab);
          if (tab === "tasks") {
            loadSavedTasks();
          }
          if (tab === "notifications") {
            refreshCounters();
          }
        }}
        tasksCount={savedTasks.length}
        candidatesCount={items.length}
        opportunitiesCount={opportunities.length}
        materialsCount={studyMaterials.length}
        unreadMessagesCount={unreadMessagesCount}
        unreadNotificationsCount={unreadNotificationsCount}
        user={currentUser}
        googleAccount={googleAccount}
        onSyncGmail={handleSyncGmail}
        onSyncClassroom={handleSyncClassroom}
        onLogout={handleLogout}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

      {/* Main SaaS Workspace Area */}
      <div className="saas-main-wrapper">
        <Topbar
          activeTab={activeTab}
          onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
          searchQuery={taskSearch}
          onSearchChange={(q) => {
            setTaskSearch(q);
            if (activeTab !== "tasks" && q.trim()) {
              setActiveTab("tasks");
            }
          }}
          onExportCalendar={handleExportDeadlines}
          onNavigateToAnalyze={() => setActiveTab("analyze")}
          deadlineCount={dashboardStats.deadlines}
          user={currentUser}
          googleAccount={googleAccount}
          onConnectGoogle={handleConnectGoogle}
          onDisconnectGoogle={handleDisconnectGoogle}
          onLogout={handleLogout}
        />

        {googleError && (
          <div className="alert alert-error" role="alert" style={{ margin: "10px 24px" }}>
            <span>⚠️ {googleError}</span>
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={handleToggleDemoData}
              style={{ marginLeft: "12px" }}
            >
              Use Offline Demo Data
            </button>
          </div>
        )}
        {googleLoading && (
          <div className="alert alert-info" role="status" style={{ margin: "10px 24px" }}>
            <span>⏳ Synchronizing with Google account...</span>
          </div>
        )}

        <main className="saas-content-workspace">
          {/* ================================================================= */}
          {/* TAB 0: DASHBOARD OVERVIEW (STUDENT OR TEACHER)                     */}
          {/* ================================================================= */}
          {activeTab === "dashboard" && userRole === "student" && (
            <DashboardOverview
              stats={dashboardStats}
              tasks={savedTasks}
              user={currentUser}
              courses={classroomCourses}
              opportunities={opportunities}
              materials={studyMaterials}
              onNavigateToSection={handleNavigateToSection}
              onExportDeadlines={handleExportDeadlines}
              onSwitchToAnalyze={() => setActiveTab("analyze")}
              onUpdateTaskStatus={handleUpdateStatus}
              onMarkReviewed={handleMarkReviewed}
              onOpenEvidence={(task) => setSelectedEvidenceItem(task)}
              onOpenEdit={(task) => setEditModalTask(task)}
              onTrackOpportunity={(data) => {
                setTrackingModalData(data);
                setShowTrackingModal(true);
              }}
              todayStr={todayStr}
            />
          )}

          {activeTab === "dashboard" && userRole === "teacher" && (
            <TeacherDashboard
              coursesOverview={teacherOverview.coursework}
              opportunitiesOverview={teacherOverview.opportunities}
              user={currentUser}
              submissions={classroomSubmissions}
              onRefresh={() => {
                loadTeacherOverview();
                loadClassroomData();
              }}
              onSubmissionGraded={() => {
                loadTeacherOverview();
                loadClassroomData();
              }}
              onNavigateToTab={(tab) => setActiveTab(tab)}
            />
          )}
        {/* ================================================================= */}
        {/* TAB 1: ANALYZE CHAT                                              */}
        {/* ================================================================= */}
        {activeTab === "analyze" && (
          <div>
            {/* Hero Section */}
            <section className="hero-section">
              <span className="hero-eyebrow">ACADEMIC COMMUNICATION INTELLIGENCE</span>
              <h2 className="hero-title">
                Surface crucial deadlines and notices buried in chat histories.
              </h2>
              <p className="hero-description">
                Group conversations easily obscure assignment due dates, exam circulars,
                workshops, and opportunities. SMART parses exported WhatsApp chats locally
                using deterministic rules, surfaces candidate items with verifiable source
                evidence, and saves confirmed items to your task database.
              </p>
            </section>

            {/* Upload Card */}
            <section className="card upload-card" aria-labelledby="upload-heading">
              <div className="card-header">
                <div>
                  <h2 id="upload-heading" className="card-title">Import Academic Communication</h2>
                  <p className="card-subtitle">
                    Select communication source: WhatsApp export, Gmail, Google Classroom, or direct manual text.
                  </p>
                </div>
                <span className="step-tag">STEP 1</span>
              </div>

              {/* Source Switcher Tabs (Phase 4.5) */}
              <div className="source-switcher-tabs" role="tablist" aria-label="Communication Source Selection">
                <button
                  type="button"
                  role="tab"
                  aria-selected={inputSource === "whatsapp"}
                  className={`source-tab-btn ${inputSource === "whatsapp" ? "active" : ""}`}
                  onClick={() => {
                    setInputSource("whatsapp");
                    setError("");
                  }}
                >
                  <span className="source-tab-icon">💬</span> WhatsApp Export
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={inputSource === "gmail"}
                  className={`source-tab-btn ${inputSource === "gmail" ? "active" : ""}`}
                  onClick={() => {
                    setInputSource("gmail");
                    setError("");
                  }}
                >
                  <span className="source-tab-icon">✉️</span> Gmail <span className="coming-soon-pill">Preview</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={inputSource === "google_classroom"}
                  className={`source-tab-btn ${inputSource === "google_classroom" ? "active" : ""}`}
                  onClick={() => {
                    setInputSource("google_classroom");
                    setError("");
                  }}
                >
                  <span className="source-tab-icon">🏫</span> Google Classroom <span className="coming-soon-pill">Preview</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={inputSource === "manual"}
                  className={`source-tab-btn ${inputSource === "manual" ? "active" : ""}`}
                  onClick={() => {
                    setInputSource("manual");
                    setError("");
                  }}
                >
                  <span className="source-tab-icon">✍️</span> Manual Text
                </button>
              </div>

              {/* WhatsApp Dropzone */}
              {inputSource === "whatsapp" && (
                <form onSubmit={handleUpload}>
                  <label
                    htmlFor={fileInputId}
                    className={`dropzone ${isDragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                  >
                    <div className="dropzone-icon" aria-hidden="true">📄</div>
                    <div className="dropzone-text">
                      <span className="dropzone-primary">
                        {file ? file.name : "Choose a WhatsApp chat .txt file"}
                      </span>
                      <span className="dropzone-secondary">
                        {file
                          ? `${(file.size / 1024).toFixed(1)} KB · Ready to analyze`
                          : "Drag and drop export file here, or click to browse"}
                      </span>
                    </div>
                    <span className="browse-button">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                      </svg>
                      <span>{file ? "Change file" : "Browse files"}</span>
                    </span>
                    <input
                      id={fileInputId}
                      type="file"
                      accept=".txt,text/plain"
                      onChange={handleFileInputChange}
                      disabled={loading}
                      className="visually-hidden"
                    />
                  </label>

                  <div className="upload-footer">
                    <p className="privacy-badge">
                      <span className="info-icon" aria-hidden="true">🔒</span>
                      Private and local: Processed entirely on your machine. No cloud APIs or external data transfer.
                    </p>
                    <div className="action-buttons">
                      {file && (
                        <button
                          type="button"
                          onClick={handleReset}
                          className="btn btn-secondary"
                          disabled={loading}
                        >
                          Clear
                        </button>
                      )}
                      <button
                        type="submit"
                        className="btn btn-primary"
                        disabled={!file || loading}
                      >
                        {loading ? (
                          <>
                            <span className="spinner" aria-hidden="true"></span>
                            Parsing conversation...
                          </>
                        ) : (
                          "Analyze conversation →"
                        )}
                      </button>
                    </div>
                  </div>
                </form>
              )}

              {/* Gmail Integration Preview Card */}
              {inputSource === "gmail" && (
                <div className="coming-soon-card">
                  <div className="coming-soon-icon">✉️</div>
                  <h3>Gmail Direct Ingestion (Integration Preview)</h3>
                  <p>
                    Connect institutional Gmail accounts to automatically scan academic circulars, exam notices, and course emails without manual exporting.
                  </p>
                  <div className="coming-soon-details">
                    <span className="feature-chip">✓ Secure OAuth 2.0</span>
                    <span className="feature-chip">✓ Label-based filtering</span>
                    <span className="feature-chip">✓ RFC 2822 header parsing</span>
                  </div>
                  <p className="coming-soon-hint">
                    To test email extraction right now, switch to <strong>Manual Text</strong> or use the backend <code>/api/extract-academic-source</code> endpoint with email payloads.
                  </p>
                </div>
              )}

              {/* Google Classroom Integration Preview Card */}
              {inputSource === "google_classroom" && (
                <div className="coming-soon-card">
                  <div className="coming-soon-icon">🏫</div>
                  <h3>Google Classroom Ingestion (Integration Preview)</h3>
                  <p>
                    Sync course announcements, lab submissions, and assignments directly from enrolled Google Classroom courses.
                  </p>
                  <div className="coming-soon-details">
                    <span className="feature-chip">✓ Classroom API v1</span>
                    <span className="feature-chip">✓ Coursework & Materials</span>
                    <span className="feature-chip">✓ Automatic due date tracking</span>
                  </div>
                  <p className="coming-soon-hint">
                    To test Classroom coursework extraction right now, switch to <strong>Manual Text</strong> or use the backend <code>/api/extract-academic-source</code> endpoint with coursework JSON.
                  </p>
                </div>
              )}

              {/* Manual Text Input Form */}
              {inputSource === "manual" && (
                <form onSubmit={handleManualExtract} className="manual-extract-form">
                  <label htmlFor="manual-text-input" className="form-label">
                    Paste Academic Announcement, Assignment, or Notice:
                  </label>
                  <textarea
                    id="manual-text-input"
                    rows={6}
                    className="form-textarea"
                    placeholder="e.g. Dr. Rao: Assignment 4 on Dynamic Programming is due on 2026-12-05 by 11:59 PM. Please submit your GitHub repository link."
                    value={manualText}
                    onChange={(e) => setManualText(e.target.value)}
                    disabled={loading}
                  />
                  <div className="upload-footer" style={{ marginTop: 12 }}>
                    <p className="privacy-badge">
                      <span className="info-icon" aria-hidden="true">🔒</span>
                      Processed entirely on your machine via local heuristic intelligence.
                    </p>
                    <div className="action-buttons">
                      {manualText && (
                        <button
                          type="button"
                          onClick={() => setManualText("")}
                          className="btn btn-secondary"
                          disabled={loading}
                        >
                          Clear
                        </button>
                      )}
                      <button
                        type="submit"
                        className="btn btn-primary"
                        disabled={!manualText.trim() || loading}
                      >
                        {loading ? "Analyzing..." : "Analyze Manual Text →"}
                      </button>
                    </div>
                  </div>
                </form>
              )}

              {error && (
                <div className="alert alert-error" role="alert">
                  <span className="alert-icon" aria-hidden="true">⚠️</span>
                  <div className="alert-body">
                    <strong>Upload & Processing Error</strong>
                    <p>{error}</p>
                  </div>
                </div>
              )}

              {success && (
                <div className="alert alert-success" role="status">
                  <span className="alert-icon" aria-hidden="true">✓</span>
                  <div className="alert-body">
                    <p>{success}</p>
                  </div>
                </div>
              )}
            </section>

            {/* Candidate Items Results Section */}
            {items.length > 0 && (
              <section className="results-section" aria-labelledby="results-heading">
                <div className="results-header">
                  <div>
                    <span className="results-eyebrow">EXTRACTION REPORT</span>
                    <h2 id="results-heading" className="results-title">Candidate Academic Items</h2>
                    <p className="results-file">
                      Source: <strong>{filename}</strong>
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleReset}
                    className="btn btn-secondary"
                    disabled={loading}
                  >
                    Upload another chat
                  </button>
                </div>

                {/* Disclaimer Alert */}
                <div className="disclaimer-banner" role="region" aria-label="Disclaimer">
                  <span className="disclaimer-icon" aria-hidden="true">ℹ️</span>
                  <p>
                    <strong>Candidate Detections:</strong> Extracted using deterministic rules.
                    Review source evidence carefully before saving items to your task database.
                  </p>
                </div>

                {/* Summary Statistics */}
                <div className="stats-grid">
                  <div className="stat-card">
                    <span className="stat-label">Messages Parsed</span>
                    <span className="stat-value">{totalMessages}</span>
                    <span className="stat-desc">From WhatsApp export</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-label">Candidate Items</span>
                    <span className="stat-value">{items.length}</span>
                    <span className="stat-desc">Academic notices identified</span>
                  </div>
                  <div className="stat-card stat-highlight">
                    <span className="stat-label">Requires Review</span>
                    <span className="stat-value text-amber">{reviewCount}</span>
                    <span className="stat-desc">Ambiguous dates or weak signals</span>
                  </div>
                </div>

                {/* Category Filter Pills */}
                <div className="filter-bar" role="tablist" aria-label="Filter items by category">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={selectedFilter === "ALL"}
                    onClick={() => setSelectedFilter("ALL")}
                    className={`filter-btn ${selectedFilter === "ALL" ? "active" : ""}`}
                  >
                    All Items ({items.length})
                  </button>

                  {reviewCount > 0 && (
                    <button
                      type="button"
                      role="tab"
                      aria-selected={selectedFilter === "REVIEW"}
                      onClick={() => setSelectedFilter("REVIEW")}
                      className={`filter-btn filter-btn-review ${selectedFilter === "REVIEW" ? "active" : ""}`}
                    >
                      Needs Review ({reviewCount})
                    </button>
                  )}

                  {["Assignment", "Exam", "Opportunity", "Event", "Announcement"].map((cat) => {
                    const count = categoryCounts[cat] || 0;
                    if (count === 0) return null;
                    return (
                      <button
                        key={cat}
                        type="button"
                        role="tab"
                        aria-selected={selectedFilter === cat}
                        onClick={() => setSelectedFilter(cat)}
                        className={`filter-btn ${selectedFilter === cat ? "active" : ""}`}
                      >
                        {cat} ({count})
                      </button>
                    );
                  })}
                </div>

                {/* Confidence Filter Pills */}
                <div className="confidence-filter-bar" role="toolbar" aria-label="Filter candidate items by confidence">
                  <span className="filter-group-label">Confidence:</span>
                  {["ALL", "HIGH", "MEDIUM", "LOW", "UNASSESSED"].map((level) => (
                    <button
                      key={level}
                      type="button"
                      onClick={() => setCandidateConfidence(level)}
                      className={`filter-btn filter-btn-confidence ${candidateConfidence === level ? "active" : ""}`}
                      aria-pressed={candidateConfidence === level}
                    >
                      {level === "ALL" ? "All Confidence" : level}
                    </button>
                  ))}
                </div>

                {/* Candidate Items List */}
                <div className="items-list">
                  {filteredCandidateItems.length === 0 ? (
                    <div className="empty-filter">
                      <p>No candidate items match the selected filter criteria.</p>
                      {(selectedFilter !== "ALL" || candidateConfidence !== "ALL") && (
                        <button
                          type="button"
                          className="btn btn-secondary"
                          style={{ marginTop: 8 }}
                          onClick={() => {
                            setSelectedFilter("ALL");
                            setCandidateConfidence("ALL");
                          }}
                        >
                          Clear Filters
                        </button>
                      )}
                    </div>
                  ) : (
                    filteredCandidateItems.map((item, idx) => {
                      const style = CATEGORY_COLORS[item.category] || {
                        bg: "#f1f5f9",
                        text: "#334155",
                        border: "#cbd5e1",
                      };

                      const saveInfo = saveStatusMap[idx] || { status: "idle" };
                      const isSaved = saveInfo.status === "saved";
                      const isSaving = saveInfo.status === "saving";

                      return (
                        <article
                          key={`${item.item_id}-${idx}`}
                          className={`item-card ${item.review_required ? "item-needs-review" : ""}`}
                        >
                          <div className="item-card-top">
                            <div className="badge-group">
                              <span
                                className="category-pill"
                                style={{
                                  backgroundColor: style.bg,
                                  color: style.text,
                                  borderColor: style.border,
                                }}
                              >
                                {item.category}
                              </span>

                              <span className={`source-pill source-pill-${(item.source_type || inputSource || "whatsapp").toLowerCase()}`}>
                                {formatSourceLabel(item.source_type || inputSource)}
                              </span>

                              <ConfidenceBadge
                                confidence={item.confidence}
                                reasons={item.confidence_reasons}
                              />

                              <ReviewIndicator
                                reviewRequired={item.review_required}
                                confidence={item.confidence}
                                reasons={item.review_reasons && item.review_reasons.length > 0 ? item.review_reasons : item.confidence_reasons}
                              />

                              {item.date_type && item.date_type !== "none" && (
                                <span className="datetype-pill">
                                  {item.date_type === "deadline" ? "Submission Deadline" : "Event Date"}
                                </span>
                              )}

                              {item.update_type && (
                                <span className="datetype-pill" style={{ backgroundColor: "#fef3c7", color: "#92400e", borderColor: "#fde68a" }}>
                                  {item.update_type.charAt(0).toUpperCase() + item.update_type.slice(1)}
                                </span>
                              )}

                              {item.is_actionable === false && (
                                <span className="datetype-pill" style={{ backgroundColor: "#f1f5f9", color: "#475569", borderColor: "#cbd5e1" }}>
                                  Informational
                                </span>
                              )}

                              {item.priority && (
                                <span className={`priority-pill priority-${item.priority.toLowerCase()}`} title={item.priority_reasons?.join("; ") || ""}>
                                  {item.priority}
                                </span>
                              )}

                              {item.importance && item.importance !== "UNASSESSED" && (
                                <span className={`importance-pill importance-${item.importance.toLowerCase()}`} title={item.importance_reasons?.join("; ") || ""}>
                                  {item.importance === "HIGH" ? "High Impact" : (item.importance === "MEDIUM" ? "Core" : "Optional")}
                                </span>
                              )}

                              {item.academic_intent && item.academic_intent !== item.category?.toLowerCase() && (
                                <span className="intent-pill" title={item.academic_intent_reasons?.join("; ") || ""}>
                                  {item.academic_intent.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                                </span>
                              )}
                            </div>

                            <span className="method-pill">Method: {item.extraction_method}</span>
                          </div>

                          <h3 className="item-title">{item.title}</h3>

                          {/* Date Details */}
                          <div className="item-date-row">
                            <div className="date-field">
                              <span className="date-label">Detected Date:</span>
                              <span className="date-val">
                                {item.due_date ? (
                                  <strong>{item.due_date}</strong>
                                ) : item.date_text ? (
                                  <span className="text-unconfirmed">{item.date_text} (unconfirmed year/format)</span>
                                ) : (
                                  <span className="text-muted">No explicit date specified</span>
                                )}
                                {item.previous_due_date && (
                                  <span className="text-muted" style={{ marginLeft: "8px" }}>
                                    (Prev: {item.previous_due_date})
                                  </span>
                                )}
                                {item.urgency && item.urgency !== "NO_DEADLINE" && (
                                  <span className={`urgency-pill urgency-${item.urgency.toLowerCase()}`} title={item.urgency_reasons?.join("; ") || ""}>
                                    {item.urgency === "CRITICAL" ? "Urgent" : item.urgency.replace(/_/g, " ")}
                                  </span>
                                )}
                              </span>
                            </div>

                            {item.date_status && item.date_status !== "not_found" && (
                              <div className="date-status-tag">
                                Status: {item.date_status.replace(/_/g, " ")}
                              </div>
                            )}
                          </div>

                          {/* Priority Rationale Box */}
                          {item.priority_reasons && item.priority_reasons.length > 0 && (
                            <div className="priority-reason-box">
                              <span className="priority-reason-label">Priority Rationale:</span>
                              <span className="priority-reason-text">{item.priority_reasons[0]}</span>
                            </div>
                          )}

                          {/* Review Explanations */}
                          <ReviewIndicator
                            reviewRequired={item.review_required}
                            confidence={item.confidence}
                            reasons={item.review_reasons && item.review_reasons.length > 0 ? item.review_reasons : item.confidence_reasons}
                            variant="box"
                          />

                          {/* Extracted URLs */}
                          {Array.isArray(item.urls) && item.urls.length > 0 && (
                            <div className="item-links-section">
                              <span className="links-header">Extracted URLs:</span>
                              <div className="links-row">
                                {item.urls.map((url, uIdx) => (
                                  <a
                                    key={uIdx}
                                    href={url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="item-url-link"
                                  >
                                    {url} ↗
                                  </a>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Expandable Evidence */}
                          <details className="source-evidence">
                            <summary className="evidence-summary">
                              <span>Inspect Original Source Evidence</span>
                            </summary>
                            <div className="evidence-body">
                              <div className="evidence-meta">
                                <span><strong>Sender:</strong> {item.source_sender || "Unknown"}</span>
                                <span><strong>Timestamp:</strong> {item.source_timestamp || "N/A"}</span>
                                <span><strong>Message #{item.source_message_id}</strong></span>
                              </div>
                              <blockquote className="evidence-text">
                                {item.source_text}
                              </blockquote>
                            </div>
                          </details>

                          {/* Save to Tasks Action Row */}
                          <div className="candidate-actions">
                            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                              {isSaved ? (
                                <span className="btn-saved">
                                  <span>✓</span> Already Saved
                                </span>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => handleSaveCandidate(item, idx)}
                                  disabled={isSaving}
                                  className="btn-save"
                                  aria-label={`Save ${item.title} to tasks`}
                                >
                                  {isSaving ? (
                                    <>
                                      <span className="spinner" aria-hidden="true"></span>
                                      Saving...
                                    </>
                                  ) : (
                                    <>
                                      <span>+</span> Save to Tasks
                                    </>
                                  )}
                                </button>
                              )}

                              <button
                                type="button"
                                className="btn-evidence"
                                onClick={() => setSelectedEvidenceItem(item)}
                                aria-label={`View evidence for ${item.title}`}
                              >
                                🔍 Evidence
                              </button>
                            </div>

                            {saveInfo.message && (
                              <span className="btn-saved-tag">{saveInfo.message}</span>
                            )}

                            {saveInfo.status === "error" && (
                              <span className="text-unconfirmed">
                                Error: {saveInfo.message}
                              </span>
                            )}
                          </div>
                        </article>
                      );
                    })
                  )}
                </div>
              </section>
            )}

            {/* Empty state when processed chat had 0 items */}
            {!loading && success && items.length === 0 && (
              <section className="card empty-card" role="region" aria-label="No items detected">
                <div className="empty-icon" aria-hidden="true">🔍</div>
                <h3>No candidate academic items detected</h3>
                <p>
                  SMART successfully parsed <strong>{totalMessages}</strong> messages from{" "}
                  <strong>{filename}</strong>, but none matched the current academic rule sets
                  (assignments, exams, circulars, workshops, or opportunities).
                </p>
                <button type="button" onClick={handleReset} className="btn btn-secondary">
                  Upload another chat export
                </button>
              </section>
            )}
          </div>
        )}

        {/* ================================================================= */}
        {/* TAB 2: MY ACADEMIC TASKS (PHASE 2 PERSISTENCE)                    */}
        {/* ================================================================= */}
        {activeTab === "tasks" && (
          <section aria-labelledby="tasks-heading">
            {/* Tasks Header */}
            <div className="tasks-header">
              <div className="tasks-title-area">
                <h2 id="tasks-heading">My Academic Tasks</h2>
                <p>
                  Browse, search, manage task status, and export confirmed academic deadlines.
                </p>
              </div>

              <button
                type="button"
                onClick={handleExportDeadlines}
                className="btn-export-ics"
                title="Download confirmed deadlines as .ics file for calendar apps"
              >
                <span>📅</span>
                <span>Export Confirmed Deadlines (.ics)</span>
              </button>
            </div>

            {/* Export Notification / Alert */}
            {exportNotice && (
              <div className="toast-notice toast-notice-info" role="status">
                <span>ℹ️ {exportNotice}</span>
                <button
                  type="button"
                  className="toast-close-btn"
                  onClick={() => setExportNotice("")}
                  aria-label="Close notification"
                >
                  ✕
                </button>
              </div>
            )}

            {tasksError && (
              <div className="toast-notice toast-notice-error" role="alert">
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span>⚠️ {tasksError}</span>
                  <button
                    type="button"
                    onClick={loadSavedTasks}
                    className="btn btn-secondary"
                    style={{ padding: "3px 10px", fontSize: "12px", height: "auto" }}
                  >
                    Retry
                  </button>
                </div>
                <button
                  type="button"
                  className="toast-close-btn"
                  onClick={() => setTasksError("")}
                  aria-label="Close error"
                >
                  ✕
                </button>
              </div>
            )}

            {/* Section Selector Pills */}
            <div className="section-pill-group" role="tablist" aria-label="Task Sections">
              {[
                { id: "all", label: "All Tasks", count: dashboardStats.total },
                { id: "today", label: "☀️ Today & Overdue", count: dashboardStats.overdue + dashboardStats.dueToday },
                { id: "upcoming", label: "⏳ Upcoming", count: dashboardStats.upcoming },
                { id: "high_priority", label: "⚡ High Priority", count: dashboardStats.highPriority },
                { id: "needs_review", label: "⚠️ Needs Review", count: dashboardStats.needsReview },
                {
                  id: "completed_archived",
                  label: "📁 Completed & Archived",
                  count: dashboardStats.completed + dashboardStats.cancelled + dashboardStats.superseded + dashboardStats.dismissed,
                },
              ].map((sec) => (
                <button
                  key={sec.id}
                  type="button"
                  role="tab"
                  aria-selected={taskSection === sec.id}
                  onClick={() => setTaskSection(sec.id)}
                  className={`section-tab-btn ${taskSection === sec.id ? "active" : ""}`}
                >
                  <span>{sec.label}</span>
                  <span className="section-tab-badge">{sec.count}</span>
                </button>
              ))}
            </div>

            {/* Task Statistics Bar */}
            <div className="task-stats-grid stats-grid">
              <div className="stat-card">
                <span className="stat-label">Tasks in View</span>
                <span className="stat-value">{filteredTasks.length}</span>
                <span className="stat-desc">Of {dashboardStats.total} total</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Pending Active</span>
                <span className="stat-value text-amber">{dashboardStats.active}</span>
                <span className="stat-desc">Awaiting completion</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Completed</span>
                <span className="stat-value" style={{ color: "#059669" }}>
                  {dashboardStats.completed}
                </span>
                <span className="stat-desc">Tasks finished</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Confirmed Deadlines</span>
                <span className="stat-value text-blue">{dashboardStats.deadlines}</span>
                <span className="stat-desc">Exportable to Calendar</span>
              </div>
            </div>

            {/* Filter & Search Panel */}
            <div className="tasks-filter-card">
              <div className="search-and-dates-grid">
                {/* Search */}
                <div className="filter-input-group">
                  <label htmlFor="task-search-input">Search Tasks</label>
                  <input
                    id="task-search-input"
                    type="text"
                    value={taskSearch}
                    onChange={(e) => setTaskSearch(e.target.value)}
                    placeholder="Search by title, details, or sender..."
                    className="filter-input"
                  />
                </div>

                {/* Due After */}
                <div className="filter-input-group">
                  <label htmlFor="task-due-after">Due From</label>
                  <input
                    id="task-due-after"
                    type="date"
                    value={taskDueAfter}
                    onChange={(e) => setTaskDueAfter(e.target.value)}
                    className="filter-input"
                  />
                </div>

                {/* Due Before */}
                <div className="filter-input-group">
                  <label htmlFor="task-due-before">Due Before</label>
                  <input
                    id="task-due-before"
                    type="date"
                    value={taskDueBefore}
                    onChange={(e) => setTaskDueBefore(e.target.value)}
                    className="filter-input"
                  />
                </div>

                {/* Academic Intent Dropdown */}
                <div className="filter-input-group">
                  <label htmlFor="task-intent-select">Academic Intent</label>
                  <select
                    id="task-intent-select"
                    value={taskIntent}
                    onChange={(e) => setTaskIntent(e.target.value)}
                    className="filter-input"
                  >
                    <option value="ALL">All Intents</option>
                    {ALLOWED_ACADEMIC_INTENTS.map((intent) => (
                      <option key={intent} value={intent}>
                        {intent.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Clear Filters */}
                {hasActiveTaskFilters && (
                  <button
                    type="button"
                    onClick={handleClearTaskFilters}
                    className="btn-clear-filters"
                  >
                    Clear All Filters
                  </button>
                )}
              </div>

              {/* Status & Category Pills */}
              <div className="status-pill-group">
                <span className="status-control-label" style={{ alignSelf: "center" }}>
                  Status:
                </span>
                {["ALL", "pending", "completed", "cancelled", "superseded", "dismissed"].map((st) => (
                  <button
                    key={st}
                    type="button"
                    onClick={() => setTaskStatus(st)}
                    className={`status-tab-btn ${taskStatus === st ? "active" : ""}`}
                  >
                    {st === "ALL" ? "All Statuses" : st.charAt(0).toUpperCase() + st.slice(1)}
                  </button>
                ))}

                <span
                  className="status-control-label"
                  style={{ alignSelf: "center", marginLeft: "12px" }}
                >
                  Category:
                </span>
                {["ALL", "Assignment", "Exam", "Opportunity", "Event", "Announcement"].map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setTaskCategory(cat)}
                    className={`status-tab-btn ${taskCategory === cat ? "active" : ""}`}
                  >
                    {cat === "ALL" ? "All Categories" : cat}
                  </button>
                ))}
              </div>

              {/* Priority & Importance Pills */}
              <div className="status-pill-group" style={{ marginTop: "10px" }}>
                <span className="status-control-label" style={{ alignSelf: "center" }}>
                  Priority:
                </span>
                {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((pri) => (
                  <button
                    key={pri}
                    type="button"
                    onClick={() => setTaskPriority(pri)}
                    className={`status-tab-btn ${taskPriority === pri ? "active" : ""}`}
                  >
                    {pri === "ALL" ? "All Priority" : pri}
                  </button>
                ))}

                <span
                  className="status-control-label"
                  style={{ alignSelf: "center", marginLeft: "12px" }}
                >
                  Importance:
                </span>
                {["ALL", "HIGH", "MEDIUM", "LOW", "UNASSESSED"].map((imp) => (
                  <button
                    key={imp}
                    type="button"
                    onClick={() => setTaskImportance(imp)}
                    className={`status-tab-btn ${taskImportance === imp ? "active" : ""}`}
                  >
                    {imp === "ALL" ? "All Importance" : imp === "HIGH" ? "High Impact" : imp === "MEDIUM" ? "Core" : imp}
                  </button>
                ))}
              </div>

              {/* Confidence & Review Requirement Pills */}
              <div className="status-pill-group" style={{ marginTop: "10px" }}>
                <span className="status-control-label" style={{ alignSelf: "center" }}>
                  Confidence:
                </span>
                {["ALL", "HIGH", "MEDIUM", "LOW", "UNASSESSED"].map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => setTaskConfidence(level)}
                    className={`status-tab-btn ${taskConfidence === level ? "active" : ""}`}
                    aria-pressed={taskConfidence === level}
                  >
                    {level === "ALL" ? "All Confidence" : level}
                  </button>
                ))}

                <span
                  className="status-control-label"
                  style={{ alignSelf: "center", marginLeft: "12px" }}
                >
                  Review:
                </span>
                {[
                  { id: "ALL", label: "All Review" },
                  { id: "NEEDS_REVIEW", label: "⚠️ Needs Review" },
                  { id: "NO_REVIEW", label: "✓ Clear" },
                ].map((rev) => (
                  <button
                    key={rev.id}
                    type="button"
                    onClick={() => setTaskReview(rev.id)}
                    className={`status-tab-btn ${taskReview === rev.id ? "active" : ""}`}
                  >
                    {rev.label}
                  </button>
                ))}
              </div>

              {/* Source Type Filter Pills (Phase 4.5) */}
              <div className="status-pill-group" style={{ marginTop: "10px" }}>
                <span className="status-control-label" style={{ alignSelf: "center" }}>
                  Source:
                </span>
                {[
                  { id: "ALL", label: "All Sources" },
                  { id: "whatsapp", label: "💬 WhatsApp" },
                  { id: "gmail", label: "✉️ Gmail" },
                  { id: "google_classroom", label: "🏫 Classroom" },
                  { id: "manual", label: "✍️ Manual" },
                ].map((st) => (
                  <button
                    key={st.id}
                    type="button"
                    onClick={() => setTaskSourceType(st.id)}
                    className={`status-tab-btn ${taskSourceType === st.id ? "active" : ""}`}
                  >
                    {st.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Saved Tasks List */}
            {tasksLoading ? (
              <div className="card empty-card">
                <span className="spinner" aria-hidden="true" style={{ fontSize: 24 }}></span>
                <p>Loading your saved academic tasks from SQLite database...</p>
              </div>
            ) : savedTasks.length === 0 ? (
              /* Completely Empty State */
              <div className="card empty-card">
                <div className="empty-icon" aria-hidden="true">📝</div>
                <h3>No Academic Tasks Saved Yet</h3>
                <p>
                  Switch to the <strong>Analyze Chat</strong> tab to upload a WhatsApp export,
                  inspect candidate assignments, exams, and notices, and save them to your task list.
                </p>
                <button
                  type="button"
                  onClick={() => setActiveTab("analyze")}
                  className="btn btn-primary"
                >
                  Go to Analyze Chat →
                </button>
              </div>
            ) : filteredTasks.length === 0 ? (
              /* Filter Produced 0 Results */
              <div className="card empty-card">
                <div className="empty-icon" aria-hidden="true">🔍</div>
                <h3>No tasks match your filters</h3>
                <p>Try adjusting your search keywords, category, status, confidence, or date range.</p>
                <button
                  type="button"
                  onClick={handleClearTaskFilters}
                  className="btn btn-secondary"
                >
                  Clear Filters
                </button>
              </div>
            ) : (
              <div className="items-list">
                {filteredTasks.map((task) => {
                  const style = CATEGORY_COLORS[task.category] || {
                    bg: "#f1f5f9",
                    text: "#334155",
                    border: "#cbd5e1",
                  };

                  const isUpdating = updatingTaskId === task.id;
                  const taskMeta = typeof task.source_metadata === "string"
                    ? (() => { try { return JSON.parse(task.source_metadata); } catch { return {}; } })()
                    : (task.source_metadata || {});
                  const gmailLink = taskMeta.gmail_deep_link || (task.source_type === "gmail" && taskMeta.threadId ? `https://mail.google.com/mail/u/0/#all/${taskMeta.threadId}` : null);
                  const taskUrls = Array.isArray(taskMeta.extracted_urls) ? taskMeta.extracted_urls : [];

                  return (
                    <article
                      key={task.id}
                      className={`item-card ${task.review_required ? "item-needs-review" : ""}`}
                    >
                      {/* Top Badges */}
                      <div className="item-card-top">
                        <div className="badge-group">
                          <span
                            className="category-pill"
                            style={{
                              backgroundColor: style.bg,
                              color: style.text,
                              borderColor: style.border,
                            }}
                          >
                            {task.category}
                          </span>

                          {/* Status Pill */}
                          <span className={`badge-status badge-status-${(task.status || "pending").toLowerCase()}`}>
                            {task.status === "completed" && "✓ "}
                            {task.status ? task.status.toUpperCase() : "PENDING"}
                          </span>

                          <span className={`source-pill source-pill-${(task.source_type || "whatsapp").toLowerCase()}`}>
                            {formatSourceLabel(task.source_type)}
                          </span>

                          <ConfidenceBadge
                            confidence={task.confidence}
                            reasons={task.confidence_reasons}
                          />

                          <ReviewIndicator
                            reviewRequired={task.review_required}
                            confidence={task.confidence}
                            reasons={task.review_reasons && task.review_reasons.length > 0 ? task.review_reasons : task.confidence_reasons}
                          />

                          {task.date_type && task.date_type !== "none" && task.date_type !== "unknown" && (
                            <span className="datetype-pill">
                              {task.date_type === "deadline" ? "Submission Deadline" : "Event Date"}
                            </span>
                          )}

                          {task.update_type && (
                            <span className="datetype-pill" style={{ backgroundColor: "#fef3c7", color: "#92400e", borderColor: "#fde68a" }}>
                              {task.update_type.charAt(0).toUpperCase() + task.update_type.slice(1)}
                            </span>
                          )}

                          {task.is_actionable === false && (
                            <span className="datetype-pill" style={{ backgroundColor: "#f1f5f9", color: "#475569", borderColor: "#cbd5e1" }}>
                              Informational
                            </span>
                          )}

                          {task.priority && (
                            <span className={`priority-pill priority-${task.priority.toLowerCase()}`} title={task.priority_reasons?.join("; ") || ""}>
                              {task.priority}
                            </span>
                          )}

                          {task.importance && task.importance !== "UNASSESSED" && (
                            <span className={`importance-pill importance-${task.importance.toLowerCase()}`} title={task.importance_reasons?.join("; ") || ""}>
                              {task.importance === "HIGH" ? "High Impact" : (task.importance === "MEDIUM" ? "Core" : "Optional")}
                            </span>
                          )}

                          {task.academic_intent && task.academic_intent !== task.category?.toLowerCase() && (
                            <span className="intent-pill" title={task.academic_intent_reasons?.join("; ") || ""}>
                              {task.academic_intent.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                            </span>
                          )}

                          {task.replaces_task_id && (
                            <span className="datetype-pill" style={{ backgroundColor: "#e0e7ff", color: "#3730a3", borderColor: "#c7d2fe" }}>
                              Replaces #{task.replaces_task_id}
                            </span>
                          )}
                        </div>

                        <span className="method-pill">Task #{task.id}</span>
                      </div>

                      {/* Title */}
                      <h3 className="item-title">{task.title}</h3>

                      {/* Date Row */}
                      <div className="item-date-row">
                        <div className="date-field">
                          <span className="date-label">Due Date:</span>
                          <span className="date-val">
                            {task.due_date ? (
                              <strong style={{ color: task.date_type === "deadline" ? "#be123c" : "inherit" }}>
                                {task.due_date}
                              </strong>
                            ) : task.date_text ? (
                              <span className="text-unconfirmed">{task.date_text} (unconfirmed)</span>
                            ) : (
                              <span className="text-muted">No date specified</span>
                            )}
                            {task.previous_due_date && (
                              <span className="text-muted" style={{ marginLeft: "8px" }}>
                                (Prev: {task.previous_due_date})
                              </span>
                            )}
                            {task.urgency && task.urgency !== "NO_DEADLINE" && (
                              <span className={`urgency-pill urgency-${task.urgency.toLowerCase()}`} title={task.urgency_reasons?.join("; ") || ""}>
                                {task.urgency === "CRITICAL" ? "Urgent" : task.urgency.replace(/_/g, " ")}
                              </span>
                            )}
                          </span>
                        </div>

                        {task.date_status && task.date_status !== "not_found" && (
                          <div className="date-status-tag">
                            Status: {task.date_status.replace(/_/g, " ")}
                          </div>
                        )}
                      </div>

                      {/* Priority Rationale Box */}
                      {task.priority_reasons && task.priority_reasons.length > 0 && (
                        <div className="priority-reason-box">
                          <span className="priority-reason-label">Priority Rationale:</span>
                          <span className="priority-reason-text">{task.priority_reasons[0]}</span>
                        </div>
                      )}

                      {/* Review Explanations */}
                      <ReviewIndicator
                        reviewRequired={task.review_required}
                        confidence={task.confidence}
                        reasons={task.review_reasons && task.review_reasons.length > 0 ? task.review_reasons : task.confidence_reasons}
                        variant="box"
                      />

                      {/* Shared URLs & Direct Gmail Evidence Link */}
                      {(gmailLink || taskUrls.length > 0) && (
                        <div className="task-links-row" style={{ display: "flex", flexWrap: "wrap", gap: "8px", margin: "10px 0" }}>
                          {gmailLink && (
                            <a
                              href={gmailLink}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="btn-gmail-pill"
                              title="Open original conversation thread in Gmail"
                            >
                              <span>✉️</span> View Original Email ↗
                            </a>
                          )}
                          {taskUrls.map((u, uIdx) => (
                            <a
                              key={uIdx}
                              href={u.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="btn-url-pill"
                              title={u.url}
                            >
                              <span className="url-kind-tag">
                                {u.kind === "google_form"
                                  ? "Form"
                                  : u.kind === "classroom"
                                  ? "Classroom"
                                  : u.kind === "drive"
                                  ? "Drive"
                                  : u.kind === "registration"
                                  ? "Register"
                                  : u.kind === "competition"
                                  ? "Contest"
                                  : u.kind === "meeting"
                                  ? "Meet"
                                  : "Link"}
                              </span>
                              <span>{u.label || "Resource"} ↗</span>
                            </a>
                          ))}
                        </div>
                      )}

                      {/* Expandable Source Evidence */}
                      <details className="source-evidence">
                        <summary className="evidence-summary">
                          <span>Inspect Original Source Evidence</span>
                        </summary>
                        <div className="evidence-body">
                          <div className="evidence-meta">
                            <span><strong>Sender:</strong> {task.source_sender || "Unknown"}</span>
                            <span><strong>Timestamp:</strong> {task.source_timestamp || "N/A"}</span>
                            {task.source_filename && (
                              <span><strong>File:</strong> {task.source_filename}</span>
                            )}
                          </div>
                          <blockquote className="evidence-text">
                            {task.source_text}
                          </blockquote>
                        </div>
                      </details>

                      {/* Actions Row: Status Switcher, Edit, Relationships, Evidence & Delete */}
                      <div className="task-actions-row">
                        <div className="status-switch-group">
                          <span className="status-control-label">Status:</span>

                          {task.review_required && (
                            <button
                              type="button"
                              onClick={() => handleMarkReviewed(task.id, "pending")}
                              disabled={isUpdating}
                              className="btn-review-confirm"
                              title="Approve and mark this task as reviewed pending"
                              aria-label="Approve task"
                            >
                              ✓ Review &amp; Confirm
                            </button>
                          )}

                          {task.status === "completed" ? (
                            <button
                              type="button"
                              onClick={() => handleUpdateStatus(task.id, "pending")}
                              disabled={isUpdating}
                              className="btn-status-option active"
                              aria-label="Reopen task"
                              title="Reopen task and mark pending"
                            >
                              ↺ Reopen Task
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleUpdateStatus(task.id, "completed")}
                              disabled={isUpdating}
                              className="btn-status-option"
                              aria-label="Mark task as completed"
                              title="Mark task completed"
                            >
                              ✓ Complete
                            </button>
                          )}

                          {task.status !== "dismissed" && (
                            <button
                              type="button"
                              onClick={() => handleUpdateStatus(task.id, "dismissed")}
                              disabled={isUpdating}
                              className="btn-status-option"
                              aria-label="Dismiss task"
                              title="Dismiss task"
                            >
                              Dismiss
                            </button>
                          )}

                          {isUpdating && <span className="spinner" aria-hidden="true"></span>}
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                          <button
                            type="button"
                            className="btn-evidence"
                            onClick={() => setEditModalTask(task)}
                            aria-label={`Edit task ${task.title}`}
                            title="Edit task details, due date, category, importance"
                          >
                            ✏️ Edit
                          </button>

                          <button
                            type="button"
                            className="btn-evidence"
                            onClick={() => setRelationshipsModalTask(task)}
                            aria-label={`View relationships for ${task.title}`}
                            title="View task lineage and revisions"
                          >
                            🔗 Lineage
                          </button>

                          <button
                            type="button"
                            className="btn-evidence"
                            onClick={() => setSelectedEvidenceItem(task)}
                            aria-label={`View evidence for ${task.title}`}
                            title="Inspect source message evidence"
                          >
                            🔍 Evidence
                          </button>

                          <button
                            type="button"
                            onClick={() => setDeleteModalItem(task)}
                            className="btn-delete-task"
                            aria-label={`Delete task ${task.title}`}
                            title="Delete task from database"
                          >
                            🗑 Delete
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        )}
          {/* ================================================================= */}
          {/* TAB 3: OPPORTUNITIES & COMPETITIONS (SMART 2.1)                   */}
          {/* ================================================================= */}
          {activeTab === "opportunities" && (
            <OpportunityExplorer
              opportunities={opportunities}
              onUpdateStatus={handleUpdateOpportunityStatus}
              userRole={userRole}
            />
          )}

          {/* ================================================================= */}
          {/* TAB 4: GOOGLE CLASSROOM & PROGRESS (SMART 2.1)                    */}
          {/* ================================================================= */}
          {activeTab === "classroom" && (
            <ClassroomProgress
              courses={classroomCourses}
              coursework={classroomCoursework}
              submissions={classroomSubmissions}
              onSync={handleSyncClassroom}
              onSubmissionsUpdated={loadClassroomData}
              loading={classroomLoading}
            />
          )}

          {/* ================================================================= */}
          {/* TAB 5: STUDY MATERIALS REPOSITORY (SMART 2.1 & 3.1)               */}
          {/* ================================================================= */}
          {activeTab === "materials" && (
            <StudyMaterialsView
              materials={studyMaterials}
              courses={classroomCourses}
              user={currentUser}
              userRole={userRole}
            />
          )}

          {/* ================================================================= */}
          {/* TAB 6: TEACHER COURSE PROGRESS (SMART 2.1 - ROLE RESTRICTED)     */}
          {/* ================================================================= */}
          {activeTab === "teacher" && userRole === "teacher" && (
            <TeacherDashboard
              coursesOverview={teacherOverview.coursework}
              opportunitiesOverview={teacherOverview.opportunities}
              user={currentUser}
              submissions={classroomSubmissions}
              onRefresh={() => {
                loadTeacherOverview();
                loadClassroomData();
              }}
              onSubmissionGraded={() => {
                loadTeacherOverview();
                loadClassroomData();
              }}
              onNavigateToTab={(tab) => setActiveTab(tab)}
            />
          )}

          {/* ================================================================= */}
          {/* TAB 7: SMART COURSES & ROSTERS (SMART 3.0)                        */}
          {/* ================================================================= */}
          {activeTab === "courses" && (
            <CoursesView
              user={currentUser}
              onSelectCourseChat={(courseId) => {
                setActiveCourseChatId(courseId);
                setActiveTab("communication");
              }}
            />
          )}

          {/* ================================================================= */}
          {/* TAB 8: REAL-TIME COMMUNICATION (SMART 3.0)                        */}
          {/* ================================================================= */}
          {activeTab === "communication" && (
            <CommunicationView
              user={currentUser}
              initialCourseId={activeCourseChatId}
            />
          )}

          {/* ================================================================= */}
          {/* TAB 9: ANNOUNCEMENTS & BROADCASTS (SMART 3.0)                     */}
          {/* ================================================================= */}
          {activeTab === "announcements" && (
            <AnnouncementsView
              user={currentUser}
            />
          )}

          {/* ================================================================= */}
          {/* TAB 10: INTERACTIVE POLLS (SMART 3.0)                             */}
          {/* ================================================================= */}
          {activeTab === "polls" && (
            <PollsView
              user={currentUser}
            />
          )}

          {/* ================================================================= */}
          {/* TAB 11: NOTIFICATIONS CENTER (SMART 3.0)                          */}
          {/* ================================================================= */}
          {activeTab === "notifications" && (
            <NotificationsCenter
              onSelectTab={(tab) => setActiveTab(tab)}
              onNotificationUpdate={refreshCounters}
            />
          )}

          {/* ================================================================= */}
          {/* TAB 12: ENGAGEMENT ANALYTICS (SMART 3.0)                          */}
          {/* ================================================================= */}
          {activeTab === "analytics" && (
            <AnalyticsView
              user={currentUser}
            />
          )}
        </main>

        {/* Footer inside main layout column */}
        <footer className="footer">
          <div className="footer-container">
            <span>SMART · Academic Communication Intelligence System</span>
            <span>Phase 2 · SQLite Persistence &amp; Task Management</span>
          </div>
        </footer>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteModalItem && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-modal-title"
          onClick={() => setDeleteModalItem(null)}
        >
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span aria-hidden="true" style={{ fontSize: 20 }}>⚠️</span>
              <h3 id="delete-modal-title">Delete Academic Task</h3>
            </div>
            <div className="modal-body">
              <p>
                Are you sure you want to delete <strong>{deleteModalItem.title}</strong>?
              </p>
              <div className="modal-warning">
                This record will be permanently removed from your SQLite database. The original
                uploaded chat file will not be modified.
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDeleteModalItem(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-danger"
                onClick={handleConfirmDelete}
              >
                Confirm Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Task Modal */}
      {editModalTask && (
        <EditTaskModal
          task={editModalTask}
          onClose={() => setEditModalTask(null)}
          onSave={handleEditSave}
        />
      )}

      {/* Task Lineage & Relationships Modal */}
      {relationshipsModalTask && (
        <TaskRelationshipsModal
          task={relationshipsModalTask}
          onClose={() => setRelationshipsModalTask(null)}
          onSelectTask={(id) => {
            const target = savedTasks.find((t) => t.id === id);
            if (target) {
              setTaskSearch(String(id));
            }
          }}
        />
      )}

      {/* Evidence Inspection Drawer */}
      {selectedEvidenceItem && (
        <EvidenceDrawer
          item={selectedEvidenceItem}
          onClose={() => setSelectedEvidenceItem(null)}
          onMarkReviewed={handleMarkReviewed}
          onTrackOpportunity={(data) => {
            setTrackingModalData(data);
            setShowTrackingModal(true);
          }}
        />
      )}

      {/* Opportunity Tracking Modal (SMART 3.2) */}
      <OpportunityTrackingModal
        isOpen={showTrackingModal}
        onClose={() => {
          setShowTrackingModal(false);
          setTrackingModalData(null);
        }}
        initialData={trackingModalData}
        onSaved={() => {
          loadOpportunitiesData();
        }}
      />
    </div>
  );
}
