
import { useState } from "react";
import "./App.css";

const API_URL = "http://localhost:8000";

function App() {
  const [file, setFile] = useState(null);
  const [items, setItems] = useState([]);
  const [filename, setFilename] = useState("");
  const [totalMessages, setTotalMessages] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const handleFileChange = (event) => {
    const selectedFile = event.target.files?.[0] ?? null;

    setFile(selectedFile);
    setItems([]);
    setFilename("");
    setTotalMessages(0);
    setError("");
    setSuccess("");

    if (selectedFile && !selectedFile.name.toLowerCase().endsWith(".txt")) {
      setError("Please select a WhatsApp chat export in .txt format.");
      setFile(null);
      event.target.value = "";
      return;
    }

    if (selectedFile && selectedFile.size > 5 * 1024 * 1024) {
      setError("The file is too large. Maximum supported size is 5 MB.");
      setFile(null);
      event.target.value = "";
    }
  };

  const handleUpload = async (event) => {
    event.preventDefault();

    if (!file) {
      setError("Please choose a WhatsApp .txt file first.");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");
    setItems([]);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${API_URL}/api/extract-academic`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data.detail || "Unable to process the chat. Please try again."
        );
      }

      setFilename(data.filename || file.name);
      setTotalMessages(data.total_messages ?? 0);
      setItems(Array.isArray(data.items) ? data.items : []);
      setSuccess("Chat processed successfully.");
    } catch (err) {
      if (err instanceof TypeError) {
        setError(
          "Could not connect to the SMART backend. Make sure FastAPI is running at http://localhost:8000."
        );
      } else {
        setError(err.message || "Something went wrong while processing the file.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setItems([]);
    setFilename("");
    setTotalMessages(0);
    setError("");
    setSuccess("");

    const input = document.getElementById("chat-file");
    if (input) input.value = "";
  };

  const reviewCount = items.filter((item) => item.review_required).length;

  return (
    <main className="app-container">
      <header className="app-header">
        <div className="brand">
          <div className="brand-icon" aria-hidden="true">
            S
          </div>

          <div>
            <h1>SMART</h1>
            <p>Academic Intelligence Dashboard</p>
          </div>
        </div>

        <span className="status-indicator">
          <span className="status-dot" />
          Prototype
        </span>
      </header>

      <section className="hero">
        <p className="eyebrow">YOUR ACADEMIC INFORMATION, ORGANIZED</p>

        <h2>
          Don't miss what
          <br />
          matters in your chats.
        </h2>

        <p className="hero-description">
          Upload a WhatsApp chat export to identify potential assignments,
          exams, announcements, events, and opportunities. Review the original
          message before acting on any extracted information.
        </p>
      </section>

      <section className="upload-panel">
        <div className="section-heading">
          <div>
            <h2>Import a conversation</h2>
            <p>Start with a WhatsApp exported text file.</p>
          </div>

          <span className="step-label">STEP 01</span>
        </div>

        <form onSubmit={handleUpload}>
          <label className="file-dropzone" htmlFor="chat-file">
            <span className="upload-icon" aria-hidden="true">
              ↑
            </span>

            <span className="file-title">
              {file ? file.name : "Choose your WhatsApp chat file"}
            </span>

            <span className="file-description">
              {file
                ? `${(file.size / 1024).toFixed(1)} KB · Ready to process`
                : "Select a .txt file exported from WhatsApp"}
            </span>

            <span className="browse-label">
              {file ? "Choose another file" : "Browse files"}
            </span>

            <input
              id="chat-file"
              type="file"
              accept=".txt,text/plain"
              onChange={handleFileChange}
              disabled={loading}
            />
          </label>

          <div className="upload-actions">
            <p className="privacy-note">
              <span aria-hidden="true">ⓘ</span> Upload only chats you have
              permission to process. This prototype does not require a live
              WhatsApp connection.
            </p>

            <button
              className="primary-button"
              type="submit"
              disabled={!file || loading}
            >
              {loading ? (
                <>
                  <span className="spinner" />
                  Processing...
                </>
              ) : (
                "Analyze conversation →"
              )}
            </button>
          </div>
        </form>

        {error && (
          <div className="alert alert-error" role="alert">
            <strong>Something went wrong</strong>
            <p>{error}</p>
          </div>
        )}

        {success && (
          <div className="alert alert-success" role="status">
            {success}
          </div>
        )}
      </section>

      {items.length > 0 && (
        <section className="results">
          <div className="section-heading results-heading">
            <div>
              <p className="eyebrow">EXTRACTION RESULTS</p>
              <h2>Academic information</h2>
              <p className="results-filename">{filename}</p>
            </div>

            <button
              className="secondary-button"
              type="button"
              onClick={handleReset}
              disabled={loading}
            >
              Clear results
            </button>
          </div>

          <div className="stats-grid">
            <article className="stat-card">
              <span className="stat-label">Messages parsed</span>
              <strong>{totalMessages}</strong>
              <span className="stat-caption">From the uploaded chat</span>
            </article>

            <article className="stat-card">
              <span className="stat-label">Candidate items</span>
              <strong>{items.length}</strong>
              <span className="stat-caption">Potentially relevant messages</span>
            </article>

            <article className="stat-card">
              <span className="stat-label">Need review</span>
              <strong>{reviewCount}</strong>
              <span className="stat-caption">Check dates and context</span>
            </article>
          </div>

          <div className="items-heading">
            <h3>Detected items</h3>
            <span>Rule-based extraction</span>
          </div>

          <div className="items-list">
            {items.map((item, index) => (
              <article
                className="academic-item"
                key={`${item.item_id ?? "item"}-${index}`}
              >
                <div className="item-top">
                  <span className="category">
                    {item.category || "Uncategorized"}
                  </span>

                  {item.review_required && (
                    <span className="review">Needs review</span>
                  )}
                </div>

                <h3>{item.title || "Untitled message"}</h3>

                <div className="item-metadata">
                  <p className="item-date">
                    <strong>Date:</strong>{" "}
                    {item.due_date
                      ? item.due_date
                      : item.date_text
                        ? `${item.date_text} (unconfirmed)`
                        : "No explicit date detected"}
                  </p>

                  {item.date_status && (
                    <p className="date-status">
                      <strong>Date status:</strong>{" "}
                      {item.date_status.replaceAll("_", " ")}
                    </p>
                  )}
                </div>

                {Array.isArray(item.urls) && item.urls.length > 0 && (
                  <div className="item-links">
                    <strong>Links mentioned</strong>

                    {item.urls.map((url) => (
                      <p key={url}>
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {url}
                        </a>
                      </p>
                    ))}
                  </div>
                )}

                <details className="source-details">
                  <summary>View original source evidence</summary>

                  <div className="source-content">
                    <p>
                      <strong>Sender:</strong>{" "}
                      {item.source_sender || "Unknown"}
                    </p>

                    <p>
                      <strong>Timestamp:</strong>{" "}
                      {item.source_timestamp || "Not available"}
                    </p>

                    <blockquote>
                      {item.source_text || "Original message unavailable."}
                    </blockquote>
                  </div>
                </details>
              </article>
            ))}
          </div>

          <p className="results-disclaimer">
            These are rule-based candidate detections, not verified deadlines
            or confirmed events. Always check the original message and clarify
            ambiguous dates before relying on them.
          </p>
        </section>
      )}

      {!loading && success && items.length === 0 && (
        <section className="empty-state">
          <div className="empty-icon" aria-hidden="true">
            ✓
          </div>
          <h3>No candidate items detected</h3>
          <p>
            SMART parsed {totalMessages} messages but did not identify any
            messages matching its current academic keywords. Try a different
            chat export or inspect the parser and extraction rules.
          </p>
        </section>
      )}

      <footer className="app-footer">
        <span>SMART · Academic Intelligence</span>
        <span>Early-stage prototype</span>
      </footer>
    </main>
  );
}

export default App;
