import { useState, useEffect, useRef } from "react";
import {
  getSmartCourses,
  getCourseMessages,
  sendCourseMessage,
  markCourseMessagesRead,
  getApiBaseUrl,
} from "../api";

export default function CommunicationView({ user, initialCourseId = null }) {
  const [courses, setCourses] = useState([]);
  const [selectedCourseId, setSelectedCourseId] = useState(initialCourseId);
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState("");
  const [attachmentUrl, setAttachmentUrl] = useState("");
  const [loadingCourses, setLoadingCourses] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [sending, setSending] = useState(false);

  const socketRef = useRef(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  // Load user courses
  useEffect(() => {
    async function load() {
      try {
        setLoadingCourses(true);
        const data = await getSmartCourses();
        const list = data.courses || [];
        setCourses(list);
        if (!selectedCourseId && list.length > 0) {
          setSelectedCourseId(list[0].id);
        }
      } catch (err) {
        console.error("Failed to load courses for communication", err);
      } finally {
        setLoadingCourses(false);
      }
    }
    load();
  }, []);

  // Connect WebSocket & load history when selectedCourseId changes
  useEffect(() => {
    if (!selectedCourseId) return;

    let isMounted = true;
    async function loadHistory() {
      try {
        setLoadingMessages(true);
        const data = await getCourseMessages(selectedCourseId);
        if (isMounted) {
          setMessages(data.messages || []);
          markCourseMessagesRead(selectedCourseId).catch(() => {});
        }
      } catch (err) {
        console.error("Failed to load messages", err);
      } finally {
        if (isMounted) setLoadingMessages(false);
      }
    }
    loadHistory();

    // Establish WebSocket connection
    const baseUrl = getApiBaseUrl().replace(/^http/, "ws");
    const wsUrl = `${baseUrl}/ws/courses/${encodeURIComponent(selectedCourseId)}/messages`;

    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      if (isMounted) setWsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const msg = payload.message || (payload.type === "new_message" ? payload.message : null);
        if (msg && msg.id) {
          setMessages((prev) => {
            // Avoid duplicate message appending
            if (prev.some((m) => m.id === msg.id)) return prev;
            return [...prev, msg];
          });
        }
      } catch (e) {
        console.error("WebSocket message parse error", e);
      }
    };

    ws.onclose = () => {
      if (isMounted) setWsConnected(false);
    };

    ws.onerror = (e) => {
      console.warn("WebSocket connection error:", e);
      if (isMounted) setWsConnected(false);
    };

    return () => {
      isMounted = false;
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  }, [selectedCourseId]);

  // Scroll to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    const content = newMessage.trim();
    if (!content || !selectedCourseId || sending) return;

    const att = attachmentUrl.trim() || null;
    setSending(true);

    let wsSent = false;
    // Try WebSocket send first if open
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      try {
        socketRef.current.send(
          JSON.stringify({
            content,
            attachment_url: att,
          })
        );
        wsSent = true;
        setNewMessage("");
        setAttachmentUrl("");
      } catch (wsErr) {
        console.warn("WebSocket send failed, attempting REST fallback:", wsErr);
      }
    }

    if (!wsSent) {
      // Fallback to REST API
      try {
        const res = await sendCourseMessage(selectedCourseId, content, att);
        const msg = res.message || res;
        if (msg && msg.id) {
          setMessages((prev) => {
            if (prev.some((m) => m.id === msg.id)) return prev;
            return [...prev, msg];
          });
        }
        setNewMessage("");
        setAttachmentUrl("");
      } catch (err) {
        console.error("Message send failed:", err);
      }
    }
    setSending(false);
    setTimeout(() => {
      textareaRef.current?.focus();
    }, 50);
  };

  const selectedCourse = courses.find((c) => c.id === selectedCourseId || c.id === Number(selectedCourseId));

  return (
    <div style={{ display: "flex", height: "calc(100vh - 120px)", background: "#fff", borderRadius: "12px", border: "1px solid #e2e8f0", overflow: "hidden", margin: "1.5rem" }}>
      {/* Course Sidebar */}
      <div style={{ width: "280px", borderRight: "1px solid #e2e8f0", display: "flex", flexDirection: "column", background: "#f8fafc" }}>
        <div style={{ padding: "1rem", borderBottom: "1px solid #e2e8f0" }}>
          <h2 style={{ fontSize: "1.1rem", margin: 0, color: "#1e1b4b" }}>Course Channels</h2>
          <span style={{ fontSize: "0.8rem", color: "#64748b" }}>Select a class to collaborate</span>
        </div>

        <div style={{ flex: 1, overflowY: "auto" }}>
          {loadingCourses ? (
            <div style={{ padding: "1rem", color: "#64748b", fontSize: "0.9rem" }}>Loading channels...</div>
          ) : courses.length === 0 ? (
            <div style={{ padding: "1rem", color: "#64748b", fontSize: "0.9rem" }}>No enrolled courses found.</div>
          ) : (
            courses.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setSelectedCourseId(c.id)}
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "0.85rem 1rem",
                  border: "none",
                  borderBottom: "1px solid #f1f5f9",
                  background: selectedCourseId === c.id ? "#ede9fe" : "transparent",
                  color: selectedCourseId === c.id ? "#5b21b6" : "#334155",
                  fontWeight: selectedCourseId === c.id ? 600 : 500,
                  cursor: "pointer",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.2rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "0.95rem" }}>{c.code}</span>
                  <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: c.theme_color || "#6366f1" }} />
                </div>
                <span style={{ fontSize: "0.8rem", color: "#64748b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.title}
                </span>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Chat Area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {selectedCourse ? (
          <>
            {/* Header */}
            <div style={{ padding: "0.85rem 1.25rem", borderBottom: "1px solid #e2e8f0", display: "flex", justifyContent: "space-between", alignItems: "center", background: "#fdfdfd" }}>
              <div>
                <h3 style={{ margin: 0, fontSize: "1.1rem", color: "#0f172a" }}>
                  {selectedCourse.title} ({selectedCourse.code})
                </h3>
                <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
                  Instructor: {selectedCourse.teacher_name || "Faculty"}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem" }}>
                <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: wsConnected ? "#10b981" : "#f59e0b" }} />
                <span style={{ color: wsConnected ? "#059669" : "#d97706", fontWeight: 600 }}>
                  {wsConnected ? "Live Connected" : "Connecting..."}
                </span>
              </div>
            </div>

            {/* Message Stream */}
            <div style={{ flex: 1, overflowY: "auto", padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
              {loadingMessages ? (
                <div style={{ textAlign: "center", padding: "2rem", color: "#64748b" }}>Loading message history...</div>
              ) : messages.length === 0 ? (
                <div style={{ textAlign: "center", padding: "3rem", color: "#94a3b8" }}>
                  No messages in this course yet. Be the first to start the discussion!
                </div>
              ) : (
                messages.map((msg) => {
                  const isOwn = msg.sender_id === user?.id;
                  const isTeacherSender = msg.sender_role === "teacher";
                  return (
                    <div
                      key={msg.id}
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: isOwn ? "flex-end" : "flex-start",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.25rem", fontSize: "0.75rem", color: "#64748b" }}>
                        <span style={{ fontWeight: 600, color: isTeacherSender ? "#7c3aed" : "#334155" }}>
                          {msg.sender_name} {isTeacherSender && "(Instructor)"}
                        </span>
                        <span>&bull;</span>
                        <span>{msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}</span>
                      </div>

                      <div
                        style={{
                          maxWidth: "70%",
                          padding: "0.75rem 1rem",
                          borderRadius: isOwn ? "12px 12px 2px 12px" : "12px 12px 12px 2px",
                          background: isOwn ? "#6366f1" : "#f1f5f9",
                          color: isOwn ? "#fff" : "#1e293b",
                          fontSize: "0.925rem",
                          lineHeight: "1.4",
                          wordBreak: "break-word",
                        }}
                      >
                        {msg.content}
                        {msg.attachment_url && (
                          <div style={{ marginTop: "0.5rem", paddingTop: "0.5rem", borderTop: isOwn ? "1px solid rgba(255,255,255,0.2)" : "1px solid #e2e8f0" }}>
                            <a
                              href={msg.attachment_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ color: isOwn ? "#fef08a" : "#2563eb", textDecoration: "underline", fontSize: "0.85rem", fontWeight: 600 }}
                            >
                              📎 View Attachment
                            </a>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Proper Multiline Chat Composer */}
            <form
              onSubmit={handleSendMessage}
              style={{
                padding: "0.85rem 1.25rem",
                borderTop: "1px solid #e2e8f0",
                background: "#fdfdfd",
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              <div style={{ display: "flex", gap: "0.6rem", alignItems: "flex-end" }}>
                <textarea
                  ref={textareaRef}
                  rows={2}
                  placeholder="Type your message..."
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage(e);
                    }
                  }}
                  disabled={sending}
                  style={{
                    flex: 1,
                    padding: "0.65rem 0.9rem",
                    borderRadius: "8px",
                    border: "1px solid #cbd5e1",
                    fontSize: "0.95rem",
                    resize: "none",
                    fontFamily: "inherit",
                    lineHeight: "1.4",
                    outline: "none",
                    boxShadow: "0 1px 2px rgba(0,0,0,0.02)",
                  }}
                />
                <button
                  type="submit"
                  disabled={sending || !newMessage.trim()}
                  style={{
                    background: "#6366f1",
                    color: "#fff",
                    border: "none",
                    padding: "0.65rem 1.35rem",
                    borderRadius: "8px",
                    fontWeight: 600,
                    fontSize: "0.95rem",
                    cursor: newMessage.trim() && !sending ? "pointer" : "not-allowed",
                    opacity: newMessage.trim() && !sending ? 1 : 0.5,
                    height: "44px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.4rem",
                    transition: "all 0.15s ease",
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                  <span>{sending ? "Sending..." : "Send"}</span>
                </button>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.75rem", color: "#64748b" }}>
                <span>Press <strong>Enter</strong> to send &bull; <strong>Shift + Enter</strong> for new line</span>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <span>Attach URL:</span>
                  <input
                    type="url"
                    placeholder="https://drive.google.com/... or resource link"
                    value={attachmentUrl}
                    onChange={(e) => setAttachmentUrl(e.target.value)}
                    style={{ padding: "0.25rem 0.5rem", borderRadius: "4px", border: "1px solid #e2e8f0", fontSize: "0.75rem", width: "220px" }}
                  />
                </div>
              </div>
            </form>
          </>
        ) : (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b" }}>
            Select a course channel on the left to start communicating.
          </div>
        )}
      </div>
    </div>
  );
}
