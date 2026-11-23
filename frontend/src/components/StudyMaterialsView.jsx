import { useState, useEffect } from "react";
import {
  getSmartCourses,
  getCourseMaterials,
  uploadCourseMaterial,
  updateCourseMaterial,
  deleteCourseMaterial,
  getMaterialDownloadUrl,
  getMaterialPreviewUrl,
} from "../api";

const CATEGORIES = [
  "All",
  "Lecture Notes",
  "Study Materials",
  "Assignments",
  "Reference Documents",
  "Question Banks",
  "Previous Year Questions",
  "Other",
];

export default function StudyMaterialsView({ materials = [], courses = [], user, userRole }) {
  const isTeacher = (user?.role || userRole) === "teacher";

  // Tab: "native" for SMART Course Materials, "external" for Classroom/Gmail imports
  const [activeTab, setActiveTab] = useState("native");

  // Courses & Selected Course
  const [smartCourses, setSmartCourses] = useState([]);
  const [selectedCourseId, setSelectedCourseId] = useState(null);
  const [coursesLoading, setCoursesLoading] = useState(true);

  // Materials & Filtering
  const [courseMaterials, setCourseMaterials] = useState([]);
  const [materialsLoading, setMaterialsLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusMessage, setStatusMessage] = useState({ type: "", text: "" });

  // External materials filter
  const [externalSourceFilter, setExternalSourceFilter] = useState("ALL");

  // Upload Modal State
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFiles, setUploadFiles] = useState([]);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadDescription, setUploadDescription] = useState("");
  const [uploadCategory, setUploadCategory] = useState("Study Materials");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");

  // Edit Modal State
  const [editingMaterial, setEditingMaterial] = useState(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editCategory, setEditCategory] = useState("Study Materials");
  const [savingEdit, setSavingEdit] = useState(false);

  // Preview Modal State
  const [previewMaterial, setPreviewMaterial] = useState(null);

  // Format bytes helper
  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return "0 KB";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  // Load Smart Courses on mount
  useEffect(() => {
    const fetchCourses = async () => {
      try {
        setCoursesLoading(true);
        const res = await getSmartCourses();
        const list = res.courses || [];
        setSmartCourses(list);
        if (list.length > 0 && !selectedCourseId) {
          setSelectedCourseId(list[0].id);
        }
      } catch (err) {
        console.error("Failed to load smart courses:", err);
      } finally {
        setCoursesLoading(false);
      }
    };
    fetchCourses();
  }, []);

  // Load materials whenever selectedCourseId changes
  const loadMaterials = async () => {
    if (!selectedCourseId) {
      setCourseMaterials([]);
      return;
    }
    try {
      setMaterialsLoading(true);
      const data = await getCourseMaterials(selectedCourseId);
      setCourseMaterials(data || []);
    } catch (err) {
      console.error("Failed to load materials:", err);
      setStatusMessage({ type: "error", text: err.message || "Failed to load study materials." });
    } finally {
      setMaterialsLoading(false);
    }
  };

  useEffect(() => {
    if (selectedCourseId) {
      loadMaterials();
    }
  }, [selectedCourseId]);

  // Handle file selection
  const handleFileChange = (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    // Check size limit: 25MB
    const oversized = files.find((f) => f.size > 25 * 1024 * 1024);
    if (oversized) {
      setUploadError(`File '${oversized.name}' exceeds the 25 MB limit.`);
      return;
    }

    setUploadError("");
    setUploadFiles(files);
    if (!uploadTitle && files.length > 0) {
      const nameWithoutExt = files[0].name.replace(/\.[^/.]+$/, "");
      setUploadTitle(nameWithoutExt);
    }
  };

  // Submit Upload
  const handleUploadSubmit = async (e) => {
    e.preventDefault();
    if (!selectedCourseId) {
      setUploadError("Please select a course first.");
      return;
    }
    if (uploadFiles.length === 0) {
      setUploadError("Please select at least one file to upload.");
      return;
    }
    if (!uploadTitle.trim()) {
      setUploadError("Please provide a title for the material.");
      return;
    }

    try {
      setUploading(true);
      setUploadError("");

      for (let i = 0; i < uploadFiles.length; i++) {
        const file = uploadFiles[i];
        const formData = new FormData();
        formData.append("file", file);
        formData.append("title", uploadFiles.length === 1 ? uploadTitle.trim() : `${uploadTitle.trim()} (Part ${i + 1})`);
        formData.append("description", uploadDescription.trim());
        formData.append("category", uploadCategory);

        await uploadCourseMaterial(selectedCourseId, formData);
      }

      setShowUploadModal(false);
      setUploadFiles([]);
      setUploadTitle("");
      setUploadDescription("");
      setUploadCategory("Study Materials");
      setStatusMessage({ type: "success", text: "Study material published successfully!" });
      loadMaterials();
    } catch (err) {
      setUploadError(err.message || "Failed to upload study material.");
    } finally {
      setUploading(false);
    }
  };

  // Start Edit
  const handleStartEdit = (mat) => {
    setEditingMaterial(mat);
    setEditTitle(mat.title || "");
    setEditDescription(mat.description || "");
    setEditCategory(mat.category || "Study Materials");
  };

  // Save Edit
  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editingMaterial) return;
    if (!editTitle.trim()) {
      alert("Title is required.");
      return;
    }
    try {
      setSavingEdit(true);
      await updateCourseMaterial(editingMaterial.id, {
        title: editTitle.trim(),
        description: editDescription.trim() || null,
        category: editCategory,
      });
      setEditingMaterial(null);
      setStatusMessage({ type: "success", text: "Study material updated." });
      loadMaterials();
    } catch (err) {
      alert(err.message || "Failed to update study material.");
    } finally {
      setSavingEdit(false);
    }
  };

  // Delete Material
  const handleDeleteMaterial = async (mat) => {
    const ok = window.confirm(`Are you sure you want to permanently delete '${mat.title}'?`);
    if (!ok) return;

    try {
      await deleteCourseMaterial(mat.id);
      setStatusMessage({ type: "success", text: "Study material deleted." });
      loadMaterials();
    } catch (err) {
      alert(err.message || "Failed to delete material.");
    }
  };

  // Filter native materials
  const filteredNativeMaterials = courseMaterials.filter((m) => {
    const matchesCategory = selectedCategory === "All" || m.category === selectedCategory;
    const matchesQuery =
      !searchQuery.trim() ||
      (m.title && m.title.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (m.original_filename && m.original_filename.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (m.description && m.description.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchesCategory && matchesQuery;
  });

  // Filter external materials
  const filteredExternalMaterials = materials.filter((m) => {
    if (externalSourceFilter === "ALL") return true;
    return (m.source_type || "").toLowerCase() === externalSourceFilter.toLowerCase();
  });

  // Get file icon & color accent
  const getFileBadge = (ext) => {
    const e = (ext || "").toLowerCase();
    if (e === ".pdf") return { icon: "📄", label: "PDF", bg: "#fee2e2", color: "#991b1b" };
    if (e === ".docx" || e === ".doc") return { icon: "📝", label: "Word", bg: "#dbeafe", color: "#1e40af" };
    if (e === ".pptx" || e === ".ppt") return { icon: "📊", label: "Slides", bg: "#ffedd5", color: "#9a3412" };
    if (e === ".xlsx" || e === ".xls") return { icon: "📈", label: "Excel", bg: "#dcfce7", color: "#166534" };
    if (e === ".txt") return { icon: "📃", label: "Text", bg: "#f1f5f9", color: "#334155" };
    return { icon: "📁", label: "Doc", bg: "#ede9fe", color: "#5b21b6" };
  };

  return (
    <div className="study-materials-view" aria-label="Study Materials & Course Attachments" style={{ maxWidth: 1140, margin: "0 auto", padding: "1.5rem" }}>
      {/* Top Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0, color: "#1e1b4b" }}>
            Study Materials &amp; Resources
          </h1>
          <p style={{ color: "#64748b", margin: "0.35rem 0 0 0", fontSize: "0.95rem" }}>
            Direct course study notes, question banks, previous year papers, and academic attachments.
          </p>
        </div>

        {/* Primary View Switcher */}
        <div style={{ display: "flex", background: "#f1f5f9", padding: "4px", borderRadius: "10px" }}>
          <button
            type="button"
            onClick={() => setActiveTab("native")}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: "8px",
              border: "none",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "0.88rem",
              background: activeTab === "native" ? "#6366f1" : "transparent",
              color: activeTab === "native" ? "#fff" : "#475569",
              transition: "all 0.15s ease",
            }}
          >
            📚 Course Materials
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("external")}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: "8px",
              border: "none",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "0.88rem",
              background: activeTab === "external" ? "#6366f1" : "transparent",
              color: activeTab === "external" ? "#fff" : "#475569",
              transition: "all 0.15s ease",
            }}
          >
            📎 External &amp; Gmail Sync
          </button>
        </div>
      </div>

      {/* Status Alert */}
      {statusMessage.text && (
        <div
          style={{
            padding: "0.75rem 1rem",
            borderRadius: "8px",
            marginBottom: "1.25rem",
            background: statusMessage.type === "error" ? "#fef2f2" : "#f0fdf4",
            color: statusMessage.type === "error" ? "#b91c1c" : "#15803d",
            border: `1px solid ${statusMessage.type === "error" ? "#fecaca" : "#bbf7d0"}`,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>{statusMessage.text}</span>
          <button
            type="button"
            onClick={() => setStatusMessage({ type: "", text: "" })}
            style={{ background: "transparent", border: "none", cursor: "pointer", fontWeight: 700 }}
          >
            ×
          </button>
        </div>
      )}

      {/* ========================================================================= */}
      {/* VIEW 1: NATIVE SMART COURSE MATERIALS                                    */}
      {/* ========================================================================= */}
      {activeTab === "native" && (
        <div>
          {/* Controls Bar: Course Selector + Upload Button */}
          <div
            style={{
              background: "#fff",
              border: "1px solid #e2e8f0",
              borderRadius: "12px",
              padding: "1rem 1.25rem",
              marginBottom: "1.5rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "1rem",
              boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <span style={{ fontSize: "0.9rem", fontWeight: 600, color: "#334155" }}>Course:</span>
              {coursesLoading ? (
                <span style={{ color: "#94a3b8", fontSize: "0.9rem" }}>Loading courses...</span>
              ) : smartCourses.length === 0 ? (
                <span style={{ color: "#e11d48", fontSize: "0.9rem" }}>No enrolled courses found.</span>
              ) : (
                <select
                  value={selectedCourseId || ""}
                  onChange={(e) => setSelectedCourseId(Number(e.target.value))}
                  style={{
                    padding: "0.55rem 0.9rem",
                    borderRadius: "8px",
                    border: "1px solid #cbd5e1",
                    background: "#f8fafc",
                    fontSize: "0.92rem",
                    fontWeight: 600,
                    color: "#1e293b",
                    minWidth: "240px",
                  }}
                >
                  {smartCourses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Teacher Upload Action */}
            {isTeacher && (
              <button
                type="button"
                onClick={() => {
                  setShowUploadModal(true);
                  setUploadError("");
                }}
                disabled={!selectedCourseId}
                style={{
                  background: "#6366f1",
                  color: "#fff",
                  border: "none",
                  padding: "0.6rem 1.25rem",
                  borderRadius: "8px",
                  cursor: selectedCourseId ? "pointer" : "not-allowed",
                  fontWeight: 600,
                  fontSize: "0.9rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  opacity: selectedCourseId ? 1 : 0.6,
                }}
              >
                <span>➕</span> Upload Material
              </button>
            )}
          </div>

          {/* Search & Category Filter Pills */}
          <div style={{ marginBottom: "1.25rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {/* Search Input */}
            <div style={{ position: "relative", maxWidth: "420px" }}>
              <input
                type="text"
                placeholder="Search resources by title, topic, or file..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.55rem 0.85rem 0.55rem 2.2rem",
                  borderRadius: "8px",
                  border: "1px solid #cbd5e1",
                  fontSize: "0.9rem",
                  boxSizing: "border-box",
                }}
              />
              <span style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }}>
                🔍
              </span>
            </div>

            {/* Category Pills */}
            <div style={{ display: "flex", gap: "0.45rem", overflowX: "auto", paddingBottom: "4px" }}>
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setSelectedCategory(cat)}
                  style={{
                    padding: "0.4rem 0.85rem",
                    borderRadius: "20px",
                    border: "1px solid",
                    borderColor: selectedCategory === cat ? "#6366f1" : "#e2e8f0",
                    background: selectedCategory === cat ? "#ede9fe" : "#fff",
                    color: selectedCategory === cat ? "#4f46e5" : "#64748b",
                    fontSize: "0.82rem",
                    fontWeight: selectedCategory === cat ? 700 : 500,
                    cursor: "pointer",
                    whiteSpace: "nowrap",
                  }}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Materials Grid / List */}
          {materialsLoading ? (
            <div style={{ textAlign: "center", padding: "4rem 2rem", color: "#64748b" }}>
              <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>⏳</div>
              <p>Loading course study materials...</p>
            </div>
          ) : !selectedCourseId ? (
            <div style={{ textAlign: "center", padding: "4rem 2rem", background: "#f8fafc", borderRadius: "12px", border: "2px dashed #e2e8f0" }}>
              <h4>No Course Selected</h4>
              <p style={{ color: "#64748b" }}>Select or enroll in a course to view its study materials.</p>
            </div>
          ) : filteredNativeMaterials.length === 0 ? (
            <div style={{ textAlign: "center", padding: "4rem 2rem", background: "#f8fafc", borderRadius: "12px", border: "2px dashed #cbd5e1" }}>
              <div style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>📂</div>
              <h3 style={{ margin: "0 0 0.5rem 0", color: "#334155" }}>No Study Materials Found</h3>
              <p style={{ color: "#64748b", maxWidth: "460px", margin: "0 auto 1.5rem auto", fontSize: "0.92rem" }}>
                {searchQuery || selectedCategory !== "All"
                  ? "No materials match your active search or category filters. Try clearing filters."
                  : isTeacher
                  ? "Upload lecture notes, assignment sheets, or question banks for your students."
                  : "Your instructor has not uploaded any study materials for this course yet."}
              </p>
              {isTeacher && !searchQuery && selectedCategory === "All" && (
                <button
                  type="button"
                  onClick={() => setShowUploadModal(true)}
                  style={{
                    background: "#6366f1",
                    color: "#fff",
                    border: "none",
                    padding: "0.6rem 1.25rem",
                    borderRadius: "8px",
                    cursor: "pointer",
                    fontWeight: 600,
                  }}
                >
                  ➕ Upload the First Material
                </button>
              )}
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1.25rem" }}>
              {filteredNativeMaterials.map((mat) => {
                const badge = getFileBadge(mat.file_extension);
                const isPreviewable = [".pdf", ".txt"].includes((mat.file_extension || "").toLowerCase());
                const uploadDate = mat.created_at ? new Date(mat.created_at).toLocaleDateString() : "Recent";

                return (
                  <div
                    key={mat.id}
                    style={{
                      background: "#fff",
                      border: "1px solid #e2e8f0",
                      borderRadius: "12px",
                      padding: "1.25rem",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                      position: "relative",
                    }}
                  >
                    <div>
                      {/* Top row: Category & File Extension Badge */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                        <span
                          style={{
                            background: badge.bg,
                            color: badge.color,
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            padding: "0.2rem 0.55rem",
                            borderRadius: "6px",
                            display: "flex",
                            alignItems: "center",
                            gap: "0.25rem",
                          }}
                        >
                          {badge.icon} {badge.label}
                        </span>

                        <span
                          style={{
                            background: "#f1f5f9",
                            color: "#475569",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            padding: "0.2rem 0.55rem",
                            borderRadius: "6px",
                          }}
                        >
                          {mat.category || "Study Materials"}
                        </span>
                      </div>

                      {/* Title */}
                      <h3 style={{ fontSize: "1.05rem", fontWeight: 700, margin: "0 0 0.4rem 0", color: "#1e1b4b", lineHeight: 1.35 }}>
                        {mat.title}
                      </h3>

                      {/* Description */}
                      {mat.description && (
                        <p style={{ color: "#64748b", fontSize: "0.85rem", margin: "0 0 0.75rem 0", lineHeight: 1.4 }}>
                          {mat.description}
                        </p>
                      )}

                      {/* Metadata row */}
                      <div style={{ fontSize: "0.8rem", color: "#94a3b8", display: "flex", flexDirection: "column", gap: "0.25rem", marginBottom: "1rem" }}>
                        <span title={mat.original_filename} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          📁 {mat.original_filename}
                        </span>
                        <span>
                          ⚖️ {formatBytes(mat.file_size)} • 📅 {uploadDate}
                        </span>
                        {mat.uploader_name && <span>👤 Uploaded by {mat.uploader_name}</span>}
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", borderTop: "1px solid #f1f5f9", paddingTop: "0.85rem", marginTop: "0.5rem" }}>
                      {/* Preview Button (PDF, TXT) */}
                      {isPreviewable ? (
                        <button
                          type="button"
                          onClick={() => setPreviewMaterial(mat)}
                          style={{
                            flex: 1,
                            background: "#ede9fe",
                            color: "#5b21b6",
                            border: "none",
                            padding: "0.45rem 0.75rem",
                            borderRadius: "6px",
                            cursor: "pointer",
                            fontWeight: 600,
                            fontSize: "0.82rem",
                          }}
                        >
                          👁️ Preview
                        </button>
                      ) : null}

                      {/* Download Button */}
                      <a
                        href={getMaterialDownloadUrl(mat.id)}
                        download={mat.original_filename}
                        style={{
                          flex: 1,
                          textAlign: "center",
                          background: "#f8fafc",
                          color: "#1e293b",
                          border: "1px solid #cbd5e1",
                          padding: "0.45rem 0.75rem",
                          borderRadius: "6px",
                          textDecoration: "none",
                          fontWeight: 600,
                          fontSize: "0.82rem",
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: "0.25rem",
                        }}
                      >
                        ⬇️ Download
                      </a>

                      {/* Teacher Actions */}
                      {isTeacher && (
                        <>
                          <button
                            type="button"
                            onClick={() => handleStartEdit(mat)}
                            title="Edit details"
                            style={{
                              background: "transparent",
                              border: "1px solid #e2e8f0",
                              padding: "0.45rem 0.65rem",
                              borderRadius: "6px",
                              cursor: "pointer",
                              fontSize: "0.82rem",
                            }}
                          >
                            ✏️
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteMaterial(mat)}
                            title="Delete resource"
                            style={{
                              background: "transparent",
                              border: "1px solid #fee2e2",
                              color: "#b91c1c",
                              padding: "0.45rem 0.65rem",
                              borderRadius: "6px",
                              cursor: "pointer",
                              fontSize: "0.82rem",
                            }}
                          >
                            🗑️
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* VIEW 2: EXTERNAL / GOOGLE CLASSROOM / GMAIL ATTACHMENTS                  */}
      {/* ========================================================================= */}
      {activeTab === "external" && (
        <div>
          {/* Filter Tabs */}
          <div className="section-pill-group" role="tablist" aria-label="Materials source filters" style={{ marginBottom: "1.25rem" }}>
            {[
              { id: "ALL", label: "All Materials" },
              { id: "classroom_material", label: "Classroom Materials" },
              { id: "gmail_attachment", label: "Gmail Attachments" },
            ].map((btn) => (
              <button
                key={btn.id}
                type="button"
                className={`section-tab-btn ${externalSourceFilter === btn.id ? "active" : ""}`}
                onClick={() => setExternalSourceFilter(btn.id)}
              >
                {btn.label}
              </button>
            ))}
          </div>

          {filteredExternalMaterials.length === 0 ? (
            <div className="saas-card chart-empty-state" style={{ textAlign: "center", padding: "4rem 2rem", background: "#f8fafc", borderRadius: "12px", border: "2px dashed #e2e8f0" }}>
              <h4>No External Study Materials Yet</h4>
              <p style={{ color: "#64748b" }}>
                Sync your Gmail or Google Classroom to automatically index syllabus documents and course materials.
              </p>
            </div>
          ) : (
            <div className="materials-grid">
              {filteredExternalMaterials.map((mat) => (
                <div key={mat.id} className="saas-card material-card">
                  <div className="material-icon-box" aria-hidden="true">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                      <line x1="16" y1="13" x2="8" y2="13" />
                      <line x1="16" y1="17" x2="8" y2="17" />
                      <polyline points="10 9 9 9 8 9" />
                    </svg>
                  </div>
                  <div className="material-content">
                    <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
                      <span className={`source-pill source-pill-${mat.source_type === "classroom_material" ? "google_classroom" : "gmail"}`}>
                        {mat.source_type === "classroom_material" ? "Classroom Material" : "Email Attachment"}
                      </span>
                      {mat.is_demo === 1 && <span className="demo-data-badge">Demo</span>}
                    </div>
                    <h4 className="material-title">{mat.title}</h4>
                    <p className="material-meta">
                      {mat.course_name ? `${mat.course_name} • ` : ""}
                      {formatBytes(mat.file_size)}
                    </p>
                  </div>

                  {mat.file_url && (
                    <a
                      href={mat.file_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="saas-secondary-btn"
                      style={{ alignSelf: "center", whiteSpace: "nowrap" }}
                    >
                      Open File ↗
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: TEACHER UPLOAD MATERIAL                                            */}
      {/* ========================================================================= */}
      {showUploadModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.6)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: "1rem",
          }}
        >
          <div
            style={{
              background: "#fff",
              borderRadius: "14px",
              maxWidth: "520px",
              width: "100%",
              padding: "1.75rem",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1)",
              maxHeight: "90vh",
              overflowY: "auto",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, margin: 0, color: "#1e1b4b" }}>
                Upload Study Material
              </h2>
              <button
                type="button"
                onClick={() => setShowUploadModal(false)}
                style={{ background: "transparent", border: "none", fontSize: "1.4rem", cursor: "pointer", color: "#64748b" }}
              >
                ×
              </button>
            </div>

            {uploadError && (
              <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", padding: "0.65rem 0.85rem", borderRadius: "8px", marginBottom: "1rem", fontSize: "0.88rem" }}>
                {uploadError}
              </div>
            )}

            <form onSubmit={handleUploadSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {/* Course selection */}
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                  Course
                </label>
                <select
                  value={selectedCourseId || ""}
                  onChange={(e) => setSelectedCourseId(Number(e.target.value))}
                  style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem" }}
                >
                  {smartCourses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </select>
              </div>

              {/* Title */}
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                  Resource Title *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Unit 3 - Consensus & Raft Protocols"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  required
                  style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem", boxSizing: "border-box" }}
                />
              </div>

              {/* Category */}
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                  Category
                </label>
                <select
                  value={uploadCategory}
                  onChange={(e) => setUploadCategory(e.target.value)}
                  style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem" }}
                >
                  {CATEGORIES.filter((c) => c !== "All").map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </div>

              {/* Description */}
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                  Description (Optional)
                </label>
                <textarea
                  rows={3}
                  placeholder="Additional context, reading instructions, or syllabus references..."
                  value={uploadDescription}
                  onChange={(e) => setUploadDescription(e.target.value)}
                  style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem", boxSizing: "border-box" }}
                />
              </div>

              {/* File Dropzone */}
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                  File(s) (PDF, DOCX, PPTX, XLSX, TXT — Max 25 MB) *
                </label>
                <input
                  type="file"
                  multiple
                  accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.txt"
                  onChange={handleFileChange}
                  style={{ display: "block", width: "100%", fontSize: "0.88rem", color: "#475569" }}
                />
                {uploadFiles.length > 0 && (
                  <div style={{ marginTop: "0.5rem", fontSize: "0.82rem", color: "#166534", background: "#f0fdf4", padding: "0.4rem 0.6rem", borderRadius: "6px" }}>
                    Selected {uploadFiles.length} file(s): {uploadFiles.map((f) => `${f.name} (${formatBytes(f.size)})`).join(", ")}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1rem" }}>
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  style={{ padding: "0.55rem 1rem", borderRadius: "8px", border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer", fontWeight: 600 }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploading || uploadFiles.length === 0}
                  style={{
                    padding: "0.55rem 1.25rem",
                    borderRadius: "8px",
                    border: "none",
                    background: "#6366f1",
                    color: "#fff",
                    fontWeight: 600,
                    cursor: uploading ? "not-allowed" : "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                >
                  {uploading ? "Uploading..." : "Publish Material"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: TEACHER EDIT METADATA                                              */}
      {/* ========================================================================= */}
      {editingMaterial && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.6)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: "1rem",
          }}
        >
          <div
            style={{
              background: "#fff",
              borderRadius: "14px",
              maxWidth: "480px",
              width: "100%",
              padding: "1.75rem",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "#1e1b4b" }}>
                Edit Material Details
              </h2>
              <button
                type="button"
                onClick={() => setEditingMaterial(null)}
                style={{ background: "transparent", border: "none", fontSize: "1.4rem", cursor: "pointer", color: "#64748b" }}
              >
                ×
              </button>
            </div>

            <form onSubmit={handleSaveEdit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                  Title *
                </label>
                <input
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  required
                  style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem", boxSizing: "border-box" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                  Category
                </label>
                <select
                  value={editCategory}
                  onChange={(e) => setEditCategory(e.target.value)}
                  style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem" }}
                >
                  {CATEGORIES.filter((c) => c !== "All").map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>
                  Description
                </label>
                <textarea
                  rows={3}
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  style={{ width: "100%", padding: "0.55rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem", boxSizing: "border-box" }}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1rem" }}>
                <button
                  type="button"
                  onClick={() => setEditingMaterial(null)}
                  style={{ padding: "0.55rem 1rem", borderRadius: "8px", border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer", fontWeight: 600 }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingEdit}
                  style={{
                    padding: "0.55rem 1.25rem",
                    borderRadius: "8px",
                    border: "none",
                    background: "#6366f1",
                    color: "#fff",
                    fontWeight: 600,
                    cursor: savingEdit ? "not-allowed" : "pointer",
                  }}
                >
                  {savingEdit ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: INLINE DOCUMENT PREVIEW (PDF & TEXT)                               */}
      {/* ========================================================================= */}
      {previewMaterial && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.75)",
            backdropFilter: "blur(4px)",
            display: "flex",
            flexDirection: "column",
            zIndex: 1100,
            padding: "1rem",
            boxSizing: "border-box",
          }}
        >
          {/* Header Bar */}
          <div
            style={{
              background: "#1e1b4b",
              color: "#fff",
              padding: "0.75rem 1.25rem",
              borderRadius: "10px 10px 0 0",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div>
              <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 600 }}>{previewMaterial.title}</h3>
              <span style={{ fontSize: "0.8rem", color: "#a5b4fc" }}>
                {previewMaterial.original_filename} • {formatBytes(previewMaterial.file_size)}
              </span>
            </div>

            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
              <a
                href={getMaterialDownloadUrl(previewMaterial.id)}
                download={previewMaterial.original_filename}
                style={{
                  background: "#4f46e5",
                  color: "#fff",
                  padding: "0.4rem 0.85rem",
                  borderRadius: "6px",
                  fontSize: "0.85rem",
                  fontWeight: 600,
                  textDecoration: "none",
                }}
              >
                ⬇️ Download Original
              </a>
              <button
                type="button"
                onClick={() => setPreviewMaterial(null)}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "#fff",
                  fontSize: "1.6rem",
                  cursor: "pointer",
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>
          </div>

          {/* Iframe View */}
          <div style={{ flex: 1, background: "#fff", borderRadius: "0 0 10px 10px", overflow: "hidden" }}>
            <iframe
              src={getMaterialPreviewUrl(previewMaterial.id)}
              title={previewMaterial.title}
              style={{ width: "100%", height: "100%", border: "none" }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
