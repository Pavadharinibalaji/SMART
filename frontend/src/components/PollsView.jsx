import { useState, useEffect } from "react";
import {
  getSmartCourses,
  getCoursePolls,
  createCoursePoll,
  submitPollVote,
  closeCoursePoll,
} from "../api";

export default function PollsView({ user }) {
  const isTeacher = user?.role === "teacher";
  const [courses, setCourses] = useState([]);
  const [selectedCourseId, setSelectedCourseId] = useState(null);
  const [polls, setPolls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Create poll modal state
  const [showModal, setShowModal] = useState(false);
  const [question, setQuestion] = useState("");
  const [pollType, setPollType] = useState("single_choice");
  const [options, setOptions] = useState(["", ""]);
  const [isAnonymous, setIsAnonymous] = useState(false);
  const [closesAt, setClosesAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [votingId, setVotingId] = useState(null);

  // Voting state: { [pollId]: optionId }
  const [votedMap, setVotedMap] = useState({});

  useEffect(() => {
    async function loadCourses() {
      try {
        setLoading(true);
        const data = await getSmartCourses();
        const list = data.courses || [];
        setCourses(list);
        if (list.length > 0) {
          setSelectedCourseId(list[0].id);
        }
      } catch (err) {
        setError(err.message || "Failed to load courses");
      } finally {
        setLoading(false);
      }
    }
    loadCourses();
  }, []);

  const loadPolls = async (cId) => {
    if (!cId) return;
    try {
      setLoading(true);
      setError("");
      const data = await getCoursePolls(cId);
      setPolls(data.polls || []);
    } catch (err) {
      setError(err.message || "Failed to load polls");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedCourseId) {
      loadPolls(selectedCourseId);
    }
  }, [selectedCourseId]);

  const handleCreatePoll = async (e) => {
    e.preventDefault();
    if (!question.trim() || !selectedCourseId) return;

    let finalOptions = [];
    if (pollType === "yes_no") {
      finalOptions = ["Yes", "No"];
    } else {
      finalOptions = options.map((o) => o.trim()).filter(Boolean);
      if (finalOptions.length < 2) {
        setError("At least two options are required.");
        return;
      }
    }

    try {
      setSubmitting(true);
      setError("");
      await createCoursePoll(selectedCourseId, {
        question: question.trim(),
        poll_type: pollType === "single_choice" ? "multiple_choice" : pollType,
        options: finalOptions,
        is_anonymous: isAnonymous,
        closes_at: closesAt ? new Date(closesAt).toISOString() : null,
      });
      setSuccess("Poll created successfully!");
      setShowModal(false);
      setQuestion("");
      setOptions(["", ""]);
      setClosesAt("");
      await loadPolls(selectedCourseId);
    } catch (err) {
      setError(err.message || "Failed to create poll");
    } finally {
      setSubmitting(false);
    }
  };

  const handleVote = async (pollId, optionId) => {
    try {
      setVotingId(optionId);
      setError("");
      await submitPollVote(selectedCourseId, pollId, optionId);
      setSuccess("Vote cast successfully!");
      setVotedMap((prev) => ({ ...prev, [pollId]: optionId }));
      await loadPolls(selectedCourseId);
    } catch (err) {
      setError(err.message || "Failed to submit vote");
    } finally {
      setVotingId(null);
    }
  };

  const handleClosePoll = async (pollId) => {
    try {
      setError("");
      await closeCoursePoll(selectedCourseId, pollId);
      setSuccess("Poll closed.");
      await loadPolls(selectedCourseId);
    } catch (err) {
      setError(err.message || "Failed to close poll");
    }
  };

  return (
    <div style={{ padding: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0, color: "#1e1b4b" }}>
            Interactive Course Polls
          </h1>
          <p style={{ color: "#64748b", margin: "0.25rem 0 0 0" }}>
            Real-time student feedback, concept checks, review preferences, and project selections.
          </p>
        </div>

        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          {courses.length > 0 && (
            <select
              value={selectedCourseId || ""}
              onChange={(e) => setSelectedCourseId(Number(e.target.value) || e.target.value)}
              style={{ padding: "0.55rem 0.9rem", borderRadius: "8px", border: "1px solid #cbd5e1", background: "#fff", fontWeight: 600, color: "#334155" }}
            >
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} - {c.title || c.name}
                </option>
              ))}
            </select>
          )}

          {isTeacher && selectedCourseId && (
            <button
              type="button"
              onClick={() => setShowModal(true)}
              style={{ background: "#6366f1", color: "#fff", border: "none", padding: "0.55rem 1.1rem", borderRadius: "8px", cursor: "pointer", fontWeight: 600 }}
            >
              + Create Poll
            </button>
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

      {loading ? (
        <div style={{ textAlign: "center", padding: "3rem", color: "#64748b" }}>Loading polls...</div>
      ) : polls.length === 0 ? (
        <div style={{ textAlign: "center", padding: "4rem 2rem", background: "#f8fafc", borderRadius: "12px", border: "2px dashed #e2e8f0" }}>
          <h3 style={{ color: "#334155", margin: "0 0 0.5rem 0" }}>No Polls Active</h3>
          <p style={{ color: "#64748b", margin: 0 }}>
            {isTeacher ? "Create a quick poll to gauge student understanding." : "No polls currently open for this course."}
          </p>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))", gap: "1.25rem" }}>
          {polls.map((poll) => {
            const isDeadlinePassed = poll.closes_at && new Date() > new Date(poll.closes_at);
            const isClosed = Boolean(poll.is_closed) || Boolean(isDeadlinePassed);
            const hasVoted = Boolean(poll.user_voted) || Boolean(votedMap[poll.id]);
            const userChoiceId = poll.user_option_id || votedMap[poll.id];

            return (
              <div
                key={poll.id}
                style={{
                  background: "#fff",
                  borderRadius: "12px",
                  border: isClosed ? "1px solid #e2e8f0" : "1px solid #c7d2fe",
                  padding: "1.25rem",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                  display: "flex",
                  flexDirection: "column",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                  <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                    <span style={{ fontSize: "0.75rem", background: isClosed ? "#f1f5f9" : "#ecfdf5", color: isClosed ? "#64748b" : "#047857", padding: "0.2rem 0.5rem", borderRadius: "4px", fontWeight: 700 }}>
                      {isClosed ? "CLOSED" : "ACTIVE"}
                    </span>
                    {poll.is_anonymous ? (
                      <span style={{ fontSize: "0.75rem", background: "#f8fafc", color: "#475569", padding: "0.2rem 0.5rem", borderRadius: "4px" }}>
                        🔒 Anonymous
                      </span>
                    ) : null}
                    {hasVoted && (
                      <span style={{ fontSize: "0.75rem", background: "#ede9fe", color: "#6d28d9", padding: "0.2rem 0.5rem", borderRadius: "4px", fontWeight: 600 }}>
                        ✓ Voted
                      </span>
                    )}
                  </div>
                  {isTeacher && !isClosed && (
                    <button
                      type="button"
                      onClick={() => handleClosePoll(poll.id)}
                      style={{ fontSize: "0.75rem", background: "#fee2e2", border: "1px solid #fca5a5", color: "#dc2626", padding: "0.2rem 0.6rem", borderRadius: "4px", cursor: "pointer", fontWeight: 600 }}
                    >
                      Close Poll
                    </button>
                  )}
                </div>

                <h3 style={{ margin: "0 0 1rem 0", fontSize: "1.1rem", color: "#0f172a" }}>{poll.question}</h3>

                {/* Options List */}
                <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", flex: 1, marginBottom: "1rem" }}>
                  {(poll.options || []).map((opt) => {
                    const isUserChoice = userChoiceId === opt.id;
                    const pct = poll.total_votes > 0 ? Math.round((opt.vote_count / poll.total_votes) * 100) : 0;
                    return (
                      <div
                        key={opt.id}
                        style={{
                          border: isUserChoice ? "2px solid #6366f1" : "1px solid #e2e8f0",
                          borderRadius: "8px",
                          overflow: "hidden",
                          position: "relative",
                          background: isUserChoice ? "#eef2ff" : "#f8fafc",
                        }}
                      >
                        {/* Vote bar fill */}
                        {(hasVoted || isClosed || isTeacher) && (
                          <div
                            style={{
                              position: "absolute",
                              left: 0,
                              top: 0,
                              bottom: 0,
                              width: `${pct}%`,
                              background: isUserChoice ? "#c7d2fe" : "#e0e7ff",
                              transition: "width 0.3s ease",
                              zIndex: 1,
                            }}
                          />
                        )}

                        <div
                          style={{
                            position: "relative",
                            zIndex: 2,
                            padding: "0.65rem 0.85rem",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            {isUserChoice && <span style={{ color: "#4f46e5", fontWeight: 700 }}>✓</span>}
                            <span style={{ fontWeight: isUserChoice ? 700 : 500, color: "#1e293b", fontSize: "0.9rem" }}>{opt.text}</span>
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                            {(hasVoted || isClosed || isTeacher) ? (
                              <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "#4f46e5" }}>
                                {pct}% ({opt.vote_count || 0})
                              </span>
                            ) : (
                              <button
                                type="button"
                                onClick={() => handleVote(poll.id, opt.id)}
                                disabled={votingId !== null}
                                style={{
                                  background: "#6366f1",
                                  color: "#fff",
                                  border: "none",
                                  padding: "0.35rem 0.85rem",
                                  borderRadius: "6px",
                                  cursor: votingId !== null ? "not-allowed" : "pointer",
                                  fontSize: "0.8rem",
                                  fontWeight: 600,
                                }}
                              >
                                {votingId === opt.id ? "Voting..." : "Vote"}
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div style={{ fontSize: "0.8rem", color: "#64748b", borderTop: "1px solid #f1f5f9", paddingTop: "0.5rem", display: "flex", justifyContent: "space-between" }}>
                  <span>Total votes: <strong>{poll.total_votes || 0}</strong></span>
                  <span>Created by {poll.creator_name || "Instructor"}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Poll Modal */}
      {showModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div style={{ background: "#fff", width: "100%", maxWidth: "500px", borderRadius: "12px", padding: "1.5rem", boxShadow: "0 20px 25px -5px rgba(0,0,0,0.1)" }}>
            <h2 style={{ margin: "0 0 1rem 0", fontSize: "1.25rem", color: "#1e1b4b" }}>Create Interactive Course Poll</h2>
            <form onSubmit={handleCreatePoll}>
              <div style={{ marginBottom: "1rem" }}>
                <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>Question *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Which date works best for the review session?"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  style={{ width: "100%", padding: "0.6rem", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                  disabled={submitting}
                />
              </div>

              <div style={{ display: "flex", gap: "1rem", marginBottom: "1rem" }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>Poll Type</label>
                  <select
                    value={pollType}
                    onChange={(e) => setPollType(e.target.value)}
                    style={{ width: "100%", padding: "0.6rem", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                    disabled={submitting}
                  >
                    <option value="single_choice">Single Choice</option>
                    <option value="multiple_choice">Multiple Choice</option>
                    <option value="yes_no">Yes / No</option>
                  </select>
                </div>

                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>Closing Deadline (Optional)</label>
                  <input
                    type="datetime-local"
                    value={closesAt}
                    onChange={(e) => setClosesAt(e.target.value)}
                    style={{ width: "100%", padding: "0.5rem", borderRadius: "6px", border: "1px solid #cbd5e1", fontSize: "0.85rem" }}
                    disabled={submitting}
                  />
                </div>
              </div>

              {pollType !== "yes_no" && (
                <div style={{ marginBottom: "1rem" }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, color: "#334155", marginBottom: "0.3rem" }}>Answer Options (At least 2)</label>
                  {options.map((opt, idx) => (
                    <div key={idx} style={{ display: "flex", gap: "0.5rem", marginBottom: "0.4rem" }}>
                      <input
                        type="text"
                        placeholder={`Option ${idx + 1}`}
                        value={opt}
                        onChange={(e) => {
                          const val = e.target.value;
                          setOptions((prev) => prev.map((o, i) => (i === idx ? val : o)));
                        }}
                        style={{ flex: 1, padding: "0.5rem", borderRadius: "6px", border: "1px solid #cbd5e1" }}
                        disabled={submitting}
                      />
                      {options.length > 2 && (
                        <button
                          type="button"
                          onClick={() => setOptions((prev) => prev.filter((_, i) => i !== idx))}
                          disabled={submitting}
                          style={{ color: "#ef4444", background: "none", border: "none", cursor: "pointer", fontSize: "1.1rem" }}
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  ))}
                  {options.length < 6 && (
                    <button
                      type="button"
                      onClick={() => setOptions((prev) => [...prev, ""])}
                      disabled={submitting}
                      style={{ fontSize: "0.8rem", color: "#6366f1", background: "none", border: "none", cursor: "pointer", fontWeight: 600, padding: 0 }}
                    >
                      + Add Option
                    </button>
                  )}
                </div>
              )}

              <div style={{ marginBottom: "1.5rem" }}>
                <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.9rem", color: "#334155", cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={isAnonymous}
                    onChange={(e) => setIsAnonymous(e.target.checked)}
                    disabled={submitting}
                  />
                  Anonymous voting (mask voter identities from classmates &amp; teacher)
                </label>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  disabled={submitting}
                  style={{ padding: "0.6rem 1rem", borderRadius: "6px", border: "1px solid #cbd5e1", background: "#f8fafc", cursor: "pointer" }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !question.trim()}
                  style={{ padding: "0.6rem 1.25rem", borderRadius: "6px", border: "none", background: "#6366f1", color: "#fff", fontWeight: 600, cursor: "pointer" }}
                >
                  {submitting ? "Creating..." : "Create Poll"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
