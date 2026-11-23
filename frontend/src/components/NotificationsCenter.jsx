import { useState, useEffect } from "react";
import {
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
} from "../api";

export default function NotificationsCenter({ onSelectTab, onNotificationUpdate }) {
  const [notifications, setNotifications] = useState([]);
  const [filterUnread, setFilterUnread] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadNotifications = async () => {
    try {
      setLoading(true);
      setError("");
      const data = await getNotifications(filterUnread);
      setNotifications(Array.isArray(data) ? data : (data.notifications || []));
    } catch (err) {
      setError(err.message || "Failed to load notifications");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadNotifications();
  }, [filterUnread]);

  const handleMarkRead = async (notifId) => {
    try {
      await markNotificationRead(notifId);
      setNotifications((prev) =>
        prev.map((n) => (n.id === notifId ? { ...n, is_read: 1 } : n))
      );
      if (onNotificationUpdate) {
        onNotificationUpdate();
      }
    } catch (err) {
      console.error("Mark read failed", err);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: 1 })));
      if (onNotificationUpdate) {
        onNotificationUpdate();
      }
    } catch (err) {
      console.error("Mark all read failed", err);
    }
  };

  const getIconForType = (type) => {
    switch (type) {
      case "announcement":
        return "📢";
      case "poll":
        return "📊";
      case "message":
        return "💬";
      case "task":
      case "deadline":
        return "⏰";
      case "invitation":
        return "✉️";
      default:
        return "🔔";
    }
  };

  return (
    <div style={{ padding: "1.5rem", maxWidth: "800px", margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0, color: "#1e1b4b" }}>
            Notification Center
          </h1>
          <p style={{ color: "#64748b", margin: "0.25rem 0 0 0" }}>
            Real-time updates, reminders, course invitations, and academic notices.
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem", color: "#475569", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={filterUnread}
              onChange={(e) => setFilterUnread(e.target.checked)}
            />
            Unread only
          </label>
          <button
            type="button"
            onClick={handleMarkAllRead}
            style={{ padding: "0.5rem 0.9rem", background: "#f8fafc", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: "pointer", fontSize: "0.85rem", fontWeight: 600, color: "#334155" }}
          >
            Mark All Read
          </button>
        </div>
      </div>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", padding: "0.75rem 1rem", borderRadius: "8px", marginBottom: "1.25rem" }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: "center", padding: "3rem", color: "#64748b" }}>Loading notifications...</div>
      ) : notifications.length === 0 ? (
        <div style={{ textAlign: "center", padding: "4rem 2rem", background: "#f8fafc", borderRadius: "12px", border: "2px dashed #e2e8f0" }}>
          <h3 style={{ color: "#334155", margin: "0 0 0.5rem 0" }}>No Notifications</h3>
          <p style={{ color: "#64748b", margin: 0 }}>You are all caught up!</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {notifications.map((n) => (
            <div
              key={n.id}
              style={{
                display: "flex",
                gap: "1rem",
                padding: "1rem",
                borderRadius: "10px",
                background: n.is_read ? "#fff" : "#f5f3ff",
                border: n.is_read ? "1px solid #e2e8f0" : "1px solid #c4b5fd",
                boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
                alignItems: "flex-start",
              }}
            >
              <div style={{ fontSize: "1.5rem", lineHeight: 1 }}>{getIconForType(n.type)}</div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <h4 style={{ margin: "0 0 0.25rem 0", fontSize: "1rem", color: "#0f172a" }}>{n.title}</h4>
                  <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>
                    {n.created_at ? new Date(n.created_at).toLocaleDateString() : ""}
                  </span>
                </div>
                <p style={{ margin: "0 0 0.5rem 0", color: "#475569", fontSize: "0.9rem" }}>{n.content}</p>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
                  {!n.is_read && (
                    <button
                      type="button"
                      onClick={() => handleMarkRead(n.id)}
                      style={{ background: "none", border: "none", color: "#6366f1", cursor: "pointer", fontSize: "0.8rem", fontWeight: 600, padding: 0 }}
                    >
                      Mark as read
                    </button>
                  )}
                  {n.action_url && (
                    <button
                      type="button"
                      onClick={() => {
                        handleMarkRead(n.id);
                        if (onSelectTab) {
                          if (n.type === "message") onSelectTab("communication");
                          else if (n.type === "announcement") onSelectTab("announcements");
                          else if (n.type === "poll") onSelectTab("polls");
                          else if (n.type === "invitation") onSelectTab("courses");
                        }
                      }}
                      style={{ background: "none", border: "none", color: "#2563eb", cursor: "pointer", fontSize: "0.8rem", textDecoration: "underline", padding: 0 }}
                    >
                      View details &rarr;
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
