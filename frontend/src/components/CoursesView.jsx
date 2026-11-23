import { useState, useEffect } from "react";
import {
  getSmartCourses,
  createSmartCourse,
  joinSmartCourse,
  getCourseMembers,
  removeCourseMember,
  inviteStudentToCourse,
  getPendingInvitations,
  acceptCourseInvitation,
  regenerateCourseJoinCode,
} from "../api";

export default function CoursesView({ user, onSelectCourseChat }) {
  const isTeacher = user?.role === "teacher";
  const [courses, setCourses] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Modal / form states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newCode, setNewCode] = useState("");
  const [newSection, setNewSection] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newColor, setNewColor] = useState("#6366f1");
  const [creatingCourse, setCreatingCourse] = useState(false);

  const [joinCodeInput, setJoinCodeInput] = useState("");
  const [joining, setJoining] = useState(false);

  // Members modal
  const [selectedCourse, setSelectedCourse] = useState(null);
  const [members, setMembers] = useState([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [regeneratingCode, setRegeneratingCode] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      setError("");
      const [coursesData, invData] = await Promise.all([
        getSmartCourses(),
        !isTeacher ? getPendingInvitations().catch(() => ({ invitations: [] })) : Promise.resolve({ invitations: [] }),
      ]);
      setCourses(coursesData.courses || []);
      setInvitations(invData.invitations || []);
    } catch (err) {
      setError(err.message || "Failed to load courses");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [user]);

  const handleCreateCourse = async (e) => {
    e.preventDefault();
    if (!newTitle.trim() || !newCode.trim()) {
      setError("Course title and code are required.");
      return;
    }
    try {
      setCreatingCourse(true);
      setError("");
      await createSmartCourse({
        name: newTitle.trim(),
        title: newTitle.trim(),
        code: newCode.trim(),
        section: newSection.trim() || null,
        description: newDescription.trim() || null,
        theme_color: newColor,
      });
      setSuccess("Course created successfully!");
      setShowCreateModal(false);
      setNewTitle("");
      setNewCode("");
      setNewSection("");
      setNewDescription("");
      await loadData();
    } catch (err) {
      setError(err.message || "Failed to create course");
    } finally {
      setCreatingCourse(false);
    }
  };

  const handleRegenerateCode = async () => {
    if (!selectedCourse) return;
    try {
      setRegeneratingCode(true);
      setError("");
      const res = await regenerateCourseJoinCode(selectedCourse.id);
      if (res && res.join_code) {
        setSelectedCourse((prev) => ({ ...prev, join_code: res.join_code }));
        setCourses((prev) =>
          prev.map((c) => (c.id === selectedCourse.id ? { ...c, join_code: res.join_code } : c))
        );
        setSuccess(`New join code generated: ${res.join_code}`);
      }
    } catch (err) {
      setError(err.message || "Failed to regenerate join code");
    } finally {
      setRegeneratingCode(false);
    }
  };

  const handleJoinCourse = async (e) => {
    e.preventDefault();
    if (!joinCodeInput.trim()) return;
    try {
      setJoining(true);
      setError("");
      await joinSmartCourse(joinCodeInput.trim());
      setSuccess("Successfully joined course!");
      setJoinCodeInput("");
      loadData();
    } catch (err) {
      setError(err.message || "Failed to join course. Check code.");
    } finally {
      setJoining(false);
    }
  };

  const handleAcceptInvite = async (invitationId) => {
    try {
      setError("");
      await acceptCourseInvitation(invitationId);
      setSuccess("Invitation accepted!");
      loadData();
    } catch (err) {
      setError(err.message || "Failed to accept invitation");
    }
  };

  const openMembersModal = async (course) => {
    setSelectedCourse(course);
    setLoadingMembers(true);
    try {
      const data = await getCourseMembers(course.id);
      setMembers(data.members || []);
    } catch (err) {
      setError(err.message || "Failed to load members");
    } finally {
      setLoadingMembers(false);
    }
  };

  const handleRemoveMember = async (studentId) => {
    if (!confirm("Remove this student from the course?")) return;
    try {
      await removeCourseMember(selectedCourse.id, studentId);
      setMembers((prev) => prev.filter((m) => m.id !== studentId));
      setSuccess("Student removed.");
    } catch (err) {
      setError(err.message || "Failed to remove student");
    }
  };

  const handleInviteStudent = async (e) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    try {
      await inviteStudentToCourse(selectedCourse.id, inviteEmail.trim());
      setSuccess(`Invitation sent to ${inviteEmail.trim()}`);
      setInviteEmail("");
    } catch (err) {
      setError(err.message || "Failed to send invitation");
    }
  };

  return (
    <div className="courses-workspace" style={{ padding: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0, color: "#1e1b4b" }}>
            {isTeacher ? "Manage SMART Courses" : "My Enrolled Courses"}
          </h1>
          <p style={{ color: "#64748b", margin: "0.25rem 0 0 0" }}>
            {isTeacher
              ? "Create collaboration spaces, distribute join codes, manage rosters, and broadcast to students."
              : "Access real-time course channels, study resources, announcements, and interactive polls."}
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          {isTeacher ? (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setShowCreateModal(true)}
              style={{ background: "#6366f1", color: "#fff", padding: "0.6rem 1.25rem", borderRadius: "8px", fontWeight: 600, border: "none", cursor: "pointer" }}
            >
              + Create Course
            </button>
          ) : (
            <form onSubmit={handleJoinCourse} style={{ display: "flex", gap: "0.5rem" }}>
              <input
                type="text"
                placeholder="Enter Join Code (e.g. SMART-XYZ123)"
                value={joinCodeInput}
                onChange={(e) => setJoinCodeInput(e.target.value)}
                style={{ padding: "0.55rem 0.85rem", borderRadius: "8px", border: "1px solid #cbd5e1", fontSize: "0.9rem" }}
              />
              <button
                type="submit"
                disabled={joining || !joinCodeInput.trim()}
                style={{ background: "#6366f1", color: "#fff", border: "none", padding: "0.55rem 1.1rem", borderRadius: "8px", cursor: "pointer", fontWeight: 600 }}
              >
                {joining ? "Joining..." : "Join Course"}
              </button>
            </form>
          )}
        </div>
      </div>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", padding: "0.75rem 1rem", borderRadius: "8px", marginBottom: "1.25rem" }}>
          {error}
        </div>
      )}
      {success && (
        <div style={{ background: "#f0fdf4", color: "#15803d", border: "1px solid #bbf7d0", padding: "0.75rem 1rem", borderRadius: "8px", marginBottom: "1.25rem" }}>
          {success}
        </div>
      )}

      {/* Pending Invitations Banner for Students */}
      {!isTeacher && invitations.length > 0 && (
        <div style={{ background: "#ede9fe", border: "1px solid #c4b5fd", padding: "1rem", borderRadius: "8px", marginBottom: "1.5rem" }}>
          <h3 style={{ margin: "0 0 0.5rem 0", color: "#5b21b6", fontSize: "1rem" }}>Pending Course Invitations</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {invitations.map((inv) => (
              <div key={inv.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#fff", padding: "0.6rem 1rem", borderRadius: "6px" }}>
                <div>
                  <strong>{inv.course_title || inv.course_name}</strong> ({inv.course_code})
                </div>
                <button
                  type="button"
                  onClick={() => handleAcceptInvite(inv.id)}
                  style={{ background: "#7c3aed", color: "#fff", border: "none", padding: "0.4rem 0.85rem", borderRadius: "6px", cursor: "pointer", fontWeight: 600 }}
                >
                  Accept Invitation
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Course Cards Grid */}
      {loading ? (
        <div style={{ textAlign: "center", padding: "3rem", color: "#64748b" }}>Loading courses...</div>
      ) : courses.length === 0 ? (
        <div style={{ textAlign: "center", padding: "4rem 2rem", background: "#f8fafc", borderRadius: "12px", border: "2px dashed #e2e8f0" }}>
          <h3 style={{ color: "#334155", margin: "0 0 0.5rem 0" }}>No Courses Found</h3>
          <p style={{ color: "#64748b", margin: 0 }}>
            {isTeacher ? "Create your first SMART course above to invite students." : "Join a course using an invite code from your teacher."}
          </p>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1.25rem" }}>
          {courses.map((course) => (
            <div
              key={course.id}
              style={{
                background: "#fff",
                borderRadius: "12px",
                border: "1px solid #e2e8f0",
                boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                display: "flex",
                flexDirection: "column",
                overflow: "hidden",
              }}
            >
              <div style={{ height: "6px", background: course.theme_color || "#6366f1" }} />
              <div style={{ padding: "1.25rem", flex: 1, display: "flex", flexDirection: "column" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.5rem" }}>
                  <span style={{ fontSize: "0.75rem", fontWeight: 700, padding: "0.2rem 0.5rem", borderRadius: "4px", background: "#f1f5f9", color: "#475569" }}>
                    {course.code} {course.section ? `· ${course.section}` : ""}
                  </span>
                  {isTeacher && (
                    <span style={{ fontSize: "0.75rem", fontFamily: "monospace", color: "#4f46e5", background: "#eef2ff", padding: "0.2rem 0.5rem", borderRadius: "4px", fontWeight: 600 }}>
                      Code: {course.join_code}
                    </span>
                  )}
                </div>

                <h3 style={{ margin: "0 0 0.5rem 0", fontSize: "1.15rem", color: "#0f172a" }}>{course.title || course.name}</h3>
                <p style={{ color: "#64748b", fontSize: "0.875rem", margin: "0 0 1rem 0", flex: 1 }}>
                  {course.description || "Course collaboration space."}
                </p>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.8rem", color: "#64748b", borderTop: "1px solid #f1f5f9", paddingTop: "0.75rem", marginBottom: "1rem" }}>
                  <span>Instructor: {course.teacher_name || "Faculty"}</span>
                  <span>{course.enrolled_count !== undefined ? course.enrolled_count : (course.student_count || 0)} Students</span>
                </div>

                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    type="button"
                    onClick={() => onSelectCourseChat && onSelectCourseChat(course.id)}
                    style={{ flex: 1, background: "#eef2ff", color: "#4f46e5", border: "1px solid #c7d2fe", padding: "0.5rem", borderRadius: "6px", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem" }}
                  >
                    Open Chat
                  </button>
                  {isTeacher && (
                    <button
                      type="button"
                      onClick={() => openMembersModal(course)}
                      style={{ background: "#f8fafc", color: "#334155", border: "1px solid #cbd5e1", padding: "0.5rem 0.75rem", borderRadius: "6px", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem" }}
                    >
                      Roster &amp; Invites
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Course Modal */}
      {showCreateModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div style={{ background: "#fff", width: "100%", maxWidth: "480px", borderRadius: "12px", padding: "1.5rem", boxShadow: "0 20px 25px -5px rgba(0,0,0,0.1)" }}>
            <h2 style={{ margin: "0 0 1rem 0", fontSize: "1.25rem", color: "#1e1b4b" }}>Create New SMART Course</h2>
            <form onSubmit={handleCreateCourse}>
              <div style={{ marginBottom: "1rem" }}>
                <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>Course Name / Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Distributed Systems & Cloud Computing"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  style={{ width: "100%", padding: "0.6rem", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                  disabled={creatingCourse}
                />
              </div>

              <div style={{ display: "flex", gap: "1rem", marginBottom: "1rem" }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>Course Code *</label>
                  <input
                    type="text"
                    required
                    placeholder="CS-401"
                    value={newCode}
                    onChange={(e) => setNewCode(e.target.value)}
                    style={{ width: "100%", padding: "0.6rem", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                    disabled={creatingCourse}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>Section</label>
                  <input
                    type="text"
                    placeholder="e.g. Section A"
                    value={newSection}
                    onChange={(e) => setNewSection(e.target.value)}
                    style={{ width: "100%", padding: "0.6rem", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                    disabled={creatingCourse}
                  />
                </div>
                <div style={{ width: "80px" }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>Theme</label>
                  <input
                    type="color"
                    value={newColor}
                    onChange={(e) => setNewColor(e.target.value)}
                    style={{ width: "100%", height: "38px", padding: "0.2rem", borderRadius: "6px", border: "1px solid #cbd5e1", cursor: "pointer" }}
                    disabled={creatingCourse}
                  />
                </div>
              </div>

              <div style={{ marginBottom: "1.5rem" }}>
                <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>Description</label>
                <textarea
                  rows={3}
                  placeholder="Course goals, prerequisites, and syllabus summary..."
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  style={{ width: "100%", padding: "0.6rem", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                  disabled={creatingCourse}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  disabled={creatingCourse}
                  style={{ padding: "0.6rem 1rem", borderRadius: "6px", border: "1px solid #cbd5e1", background: "#f8fafc", cursor: "pointer" }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingCourse || !newTitle.trim() || !newCode.trim()}
                  style={{ padding: "0.6rem 1.25rem", borderRadius: "6px", border: "none", background: "#6366f1", color: "#fff", fontWeight: 600, cursor: "pointer" }}
                >
                  {creatingCourse ? "Creating..." : "Create Course"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Roster & Invites Modal */}
      {selectedCourse && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div style={{ background: "#fff", width: "100%", maxWidth: "600px", maxHeight: "85vh", borderRadius: "12px", padding: "1.5rem", display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h2 style={{ margin: 0, fontSize: "1.25rem", color: "#1e1b4b" }}>{selectedCourse.title || selectedCourse.name} Roster &amp; Access</h2>
              <button
                type="button"
                onClick={() => setSelectedCourse(null)}
                style={{ background: "none", border: "none", fontSize: "1.25rem", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>

            <div style={{ background: "#f8fafc", padding: "0.75rem 1rem", borderRadius: "8px", marginBottom: "1rem", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
              <div>
                <span style={{ fontSize: "0.8rem", color: "#64748b" }}>Course Join Code:</span>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, fontFamily: "monospace", color: "#4f46e5" }}>{selectedCourse.join_code}</div>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(selectedCourse.join_code);
                    setSuccess("Join code copied to clipboard!");
                  }}
                  style={{ padding: "0.4rem 0.8rem", background: "#eef2ff", color: "#4f46e5", border: "1px solid #c7d2fe", borderRadius: "6px", cursor: "pointer", fontSize: "0.8rem", fontWeight: 600 }}
                >
                  Copy Code
                </button>
                <button
                  type="button"
                  onClick={handleRegenerateCode}
                  disabled={regeneratingCode}
                  style={{ padding: "0.4rem 0.8rem", background: "#f1f5f9", color: "#475569", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer", fontSize: "0.8rem", fontWeight: 600 }}
                >
                  {regeneratingCode ? "Regenerating..." : "Regenerate Code"}
                </button>
              </div>
            </div>

            {/* Invite Form */}
            <form onSubmit={handleInviteStudent} style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
              <input
                type="email"
                required
                placeholder="Student email (e.g. student@university.edu)"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                style={{ flex: 1, padding: "0.55rem 0.75rem", borderRadius: "6px", border: "1px solid #cbd5e1" }}
              />
              <button
                type="submit"
                style={{ background: "#6366f1", color: "#fff", border: "none", padding: "0.55rem 1rem", borderRadius: "6px", cursor: "pointer", fontWeight: 600 }}
              >
                Invite Student
              </button>
            </form>

            {/* Members List */}
            <h4 style={{ margin: "0 0 0.5rem 0", color: "#334155" }}>Enrolled Students ({members.length})</h4>
            <div style={{ flex: 1, overflowY: "auto", border: "1px solid #e2e8f0", borderRadius: "8px" }}>
              {loadingMembers ? (
                <div style={{ padding: "2rem", textAlign: "center", color: "#64748b" }}>Loading roster...</div>
              ) : members.length === 0 ? (
                <div style={{ padding: "2rem", textAlign: "center", color: "#64748b" }}>No students enrolled yet.</div>
              ) : (
                <div style={{ divideY: "1px solid #e2e8f0" }}>
                  {members.map((m) => (
                    <div key={m.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.75rem 1rem", borderBottom: "1px solid #f1f5f9" }}>
                      <div>
                        <div style={{ fontWeight: 600, color: "#1e293b" }}>{m.full_name || m.name || m.email}</div>
                        <div style={{ fontSize: "0.8rem", color: "#64748b" }}>{m.email} &bull; Joined {m.enrolled_at ? new Date(m.enrolled_at).toLocaleDateString() : "Recently"} &bull; Status: <span style={{ textTransform: "capitalize", color: "#059669", fontWeight: 600 }}>{m.status || "Enrolled"}</span></div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleRemoveMember(m.id)}
                        style={{ color: "#ef4444", background: "none", border: "none", cursor: "pointer", fontSize: "0.85rem", fontWeight: 600 }}
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
