import { useState, useEffect, useId, useMemo, useCallback } from "react";
import "./App.css";
import ConfidenceBadge from "./components/ConfidenceBadge";
import ReviewIndicator from "./components/ReviewIndicator";
import EvidenceDrawer from "./components/EvidenceDrawer";
import { matchesConfidence } from "./utils/confidenceFilter";
import {
  extractAcademic,
  saveAcademicItem,
  getAcademicItems,
  updateAcademicItemStatus,
  deleteAcademicItem,
  getExportIcsUrl,
} from "./api";

const CATEGORY_COLORS = {
  Assignment: { bg: "#eff6ff", text: "#1d4ed8", border: "#bfdbfe" },
  Exam: { bg: "#fff1f2", text: "#be123c", border: "#fecdd3" },
  Announcement: { bg: "#f1f5f9", text: "#334155", border: "#cbd5e1" },
  Opportunity: { bg: "#fef3c7", text: "#92400e", border: "#fcd34d" },
  Event: { bg: "#ecfdf5", text: "#047857", border: "#a7f3d0" },
};

export default function App() {
  // Navigation: "analyze" or "tasks"
  const [activeTab, setActiveTab] = useState("analyze");

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

  // Task filtering state
  const [taskSearch, setTaskSearch] = useState("");
  const [taskCategory, setTaskCategory] = useState("ALL");
  const [taskStatus, setTaskStatus] = useState("ALL");
  const [taskConfidence, setTaskConfidence] = useState("ALL");
  const [taskDueBefore, setTaskDueBefore] = useState("");
  const [taskDueAfter, setTaskDueAfter] = useState("");

  // Modals & Notifications
  const [deleteModalItem, setDeleteModalItem] = useState(null);
  const [selectedEvidenceItem, setSelectedEvidenceItem] = useState(null);
  const [exportNotice, setExportNotice] = useState("");

  const fileInputId = useId();

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

  // Fetch saved tasks on mount
  useEffect(() => {
    loadSavedTasks();
  }, [loadSavedTasks]);

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
        review_required: candidate.review_required,
        review_reasons: candidate.review_reasons,
        evidence_text: candidate.evidence_text,
        evidence_start_index: candidate.evidence_start_index,
        evidence_end_index: candidate.evidence_end_index,
        candidate_token: candidate.candidate_token,
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
      (t) => t.due_date && (t.date_type || "").toLowerCase() === "deadline"
    ).length;

    if (deadlineCount === 0) {
      setExportNotice(
        "No confirmed deadlines available to export. Items must have a confirmed due date and date type 'deadline'."
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

  // Filtered saved tasks (My Academic Tasks tab)
  const filteredTasks = useMemo(() => {
    return savedTasks.filter((task) => {
      // Category filter
      if (taskCategory !== "ALL" && task.category !== taskCategory) {
        return false;
      }

      // Status filter
      if (taskStatus !== "ALL" && (task.status || "").toLowerCase() !== taskStatus.toLowerCase()) {
        return false;
      }

      // Confidence filter
      if (!matchesConfidence(task, taskConfidence)) {
        return false;
      }

      // Search keyword filter
      if (taskSearch.trim()) {
        const query = taskSearch.toLowerCase().trim();
        const inTitle = (task.title || "").toLowerCase().includes(query);
        const inDesc = (task.description || "").toLowerCase().includes(query);
        const inSource = (task.source_text || "").toLowerCase().includes(query);
        const inSender = (task.source_sender || "").toLowerCase().includes(query);
        if (!inTitle && !inDesc && !inSource && !inSender) {
          return false;
        }
      }

      // Date range filter
      if (taskDueBefore) {
        if (!task.due_date || task.due_date > taskDueBefore) {
          return false;
        }
      }

      if (taskDueAfter) {
        if (!task.due_date || task.due_date < taskDueAfter) {
          return false;
        }
      }

      return true;
    });
  }, [savedTasks, taskCategory, taskStatus, taskConfidence, taskSearch, taskDueBefore, taskDueAfter]);

  // Tasks statistics
  const taskStats = useMemo(() => {
    const total = savedTasks.length;
    const pending = savedTasks.filter((t) => (t.status || "").toLowerCase() === "pending").length;
    const completed = savedTasks.filter((t) => (t.status || "").toLowerCase() === "completed").length;
    const deadlines = savedTasks.filter(
      (t) => t.due_date && (t.date_type || "").toLowerCase() === "deadline"
    ).length;
    return { total, pending, completed, deadlines };
  }, [savedTasks]);

  const hasActiveTaskFilters =
    taskSearch !== "" ||
    taskCategory !== "ALL" ||
    taskStatus !== "ALL" ||
    taskConfidence !== "ALL" ||
    taskDueBefore !== "" ||
    taskDueAfter !== "";

  const handleClearTaskFilters = () => {
    setTaskSearch("");
    setTaskCategory("ALL");
    setTaskStatus("ALL");
    setTaskConfidence("ALL");
    setTaskDueBefore("");
    setTaskDueAfter("");
  };

  return (
    <div className="app-layout">
      {/* Top Navbar */}
      <header className="navbar">
        <div className="navbar-container">
          <div className="navbar-brand">
            <span className="brand-badge" aria-hidden="true">S</span>
            <div className="brand-text">
              <h1>SMART</h1>
              <p>Academic Intelligence Dashboard</p>
            </div>
          </div>
          <div className="navbar-meta">
            <span className="prototype-tag">
              <span className="dot" aria-hidden="true"></span> Local Prototype
            </span>
          </div>
        </div>
      </header>

      {/* Main Tab Switcher */}
      <nav className="nav-tabs-wrapper" aria-label="Main Navigation">
        <div className="nav-tabs-container">
          <button
            type="button"
            className={`nav-tab-btn ${activeTab === "analyze" ? "active" : ""}`}
            onClick={() => setActiveTab("analyze")}
            aria-selected={activeTab === "analyze"}
            role="tab"
          >
            <span>💬 Analyze Chat</span>
          </button>
          <button
            type="button"
            className={`nav-tab-btn ${activeTab === "tasks" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("tasks");
              loadSavedTasks();
            }}
            aria-selected={activeTab === "tasks"}
            role="tab"
          >
            <span>📋 My Academic Tasks</span>
            <span className="nav-tab-badge" title="Saved tasks count">
              {savedTasks.length}
            </span>
          </button>
        </div>
      </nav>

      <main className="content-container">
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
                  <h2 id="upload-heading" className="card-title">Import Conversation Export</h2>
                  <p className="card-subtitle">
                    Select or drop a WhatsApp exported <code>.txt</code> file (up to 5 MB).
                  </p>
                </div>
                <span className="step-tag">STEP 1</span>
              </div>

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
                    {file ? "Change file" : "Browse files"}
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
                              </span>
                            </div>

                            {item.date_status && item.date_status !== "not_found" && (
                              <div className="date-status-tag">
                                Status: {item.date_status.replace(/_/g, " ")}
                              </div>
                            )}
                          </div>

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

            {/* Task Statistics Bar */}
            <div className="stats-grid">
              <div className="stat-card">
                <span className="stat-label">Total Saved Tasks</span>
                <span className="stat-value">{taskStats.total}</span>
                <span className="stat-desc">In SQLite database</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Pending</span>
                <span className="stat-value text-amber">{taskStats.pending}</span>
                <span className="stat-desc">Awaiting completion</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Completed</span>
                <span className="stat-value" style={{ color: "#059669" }}>
                  {taskStats.completed}
                </span>
                <span className="stat-desc">Tasks finished</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Confirmed Deadlines</span>
                <span className="stat-value text-blue">{taskStats.deadlines}</span>
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

                {/* Clear Filters */}
                {hasActiveTaskFilters && (
                  <button
                    type="button"
                    onClick={handleClearTaskFilters}
                    className="btn-clear-filters"
                  >
                    Clear Filters
                  </button>
                )}
              </div>

              {/* Status & Category Pills */}
              <div className="status-pill-group">
                <span className="status-control-label" style={{ alignSelf: "center" }}>
                  Status:
                </span>
                {["ALL", "pending", "completed", "dismissed"].map((st) => (
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

              {/* Confidence Filter Pills */}
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
                          </span>
                        </div>

                        {task.date_status && task.date_status !== "not_found" && (
                          <div className="date-status-tag">
                            Status: {task.date_status.replace(/_/g, " ")}
                          </div>
                        )}
                      </div>

                      {/* Review Explanations */}
                      <ReviewIndicator
                        reviewRequired={task.review_required}
                        confidence={task.confidence}
                        reasons={task.review_reasons && task.review_reasons.length > 0 ? task.review_reasons : task.confidence_reasons}
                        variant="box"
                      />

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

                      {/* Actions Row: Status Switcher & Delete */}
                      <div className="task-actions-row">
                        <div className="status-switch-group">
                          <span className="status-control-label">Update Status:</span>

                          <button
                            type="button"
                            onClick={() => handleUpdateStatus(task.id, "pending")}
                            disabled={isUpdating || task.status === "pending"}
                            className={`btn-status-option ${task.status === "pending" ? "active" : ""}`}
                            aria-label="Mark task as pending"
                          >
                            Pending
                          </button>

                          <button
                            type="button"
                            onClick={() => handleUpdateStatus(task.id, "completed")}
                            disabled={isUpdating || task.status === "completed"}
                            className={`btn-status-option ${task.status === "completed" ? "active" : ""}`}
                            aria-label="Mark task as completed"
                          >
                            ✓ Completed
                          </button>

                          <button
                            type="button"
                            onClick={() => handleUpdateStatus(task.id, "dismissed")}
                            disabled={isUpdating || task.status === "dismissed"}
                            className={`btn-status-option ${task.status === "dismissed" ? "active" : ""}`}
                            aria-label="Dismiss task"
                          >
                            Dismiss
                          </button>

                          {isUpdating && <span className="spinner" aria-hidden="true"></span>}
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <button
                            type="button"
                            className="btn-evidence"
                            onClick={() => setSelectedEvidenceItem(task)}
                            aria-label={`View evidence for ${task.title}`}
                          >
                            🔍 Evidence
                          </button>

                          <button
                            type="button"
                            onClick={() => setDeleteModalItem(task)}
                            className="btn-delete-task"
                            aria-label={`Delete task ${task.title}`}
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
      </main>

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

      {/* Evidence Inspection Drawer */}
      {selectedEvidenceItem && (
        <EvidenceDrawer
          item={selectedEvidenceItem}
          onClose={() => setSelectedEvidenceItem(null)}
        />
      )}

      {/* Footer */}
      <footer className="footer">
        <div className="footer-container">
          <span>SMART · Academic Communication Intelligence System</span>
          <span>Phase 2 · SQLite Persistence &amp; Task Management</span>
        </div>
      </footer>
    </div>
  );
}
