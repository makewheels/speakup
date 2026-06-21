import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { api } from "../api/client.js";
import Icon from "../components/Icon.jsx";
import { copyShare } from "../lib/share.js";

function formatDateTime(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const pad = (n) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export default function ManageSharesPage() {
  const { user } = useUser();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState("");

  useEffect(() => {
    api.listShared(user.userId)
      .then(setItems)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [user.userId]);

  const flash = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 2000);
  };

  const copy = async (s, e) => {
    e.stopPropagation();
    try {
      await copyShare(s, s.shareToken);
      flash("Link copied");
    } catch (err) {
      flash("Copy failed: " + err.message);
    }
  };

  const cancel = async (s, e) => {
    e.stopPropagation();
    if (busy) return;
    setBusy(s._id);
    try {
      await api.unsharePractice(s._id, user.userId);
      setItems((prev) => prev.filter((x) => x._id !== s._id));
      flash("Sharing stopped");
    } catch (err) {
      flash("Failed: " + err.message);
    } finally {
      setBusy("");
    }
  };

  if (loading) return <div className="page-msg">Loading…</div>;

  return (
    <div className="manage-shares-page">
      <div className="page-head">
        <h2>My shares</h2>
        <span className="count-label">{items.length} shared</span>
      </div>

      {items.length === 0 ? (
        <div className="empty-state">
          <div className="icon-box">
            <Icon name="share" size={28} color="var(--ink-3)" stroke={1.4} />
          </div>
          <p className="title">No shared practices yet</p>
          <p className="sub">Tap Share on any practice to get a link</p>
          <button className="su-btn su-btn-primary" style={{ maxWidth: 200 }} onClick={() => navigate("/history")}>
            Go to history
          </button>
        </div>
      ) : (
        <div className="share-list">
          {items.map((s) => {
            const title = s.title || s.topic || "Practice";
            return (
              <div key={s._id} className="share-item" onClick={() => navigate(`/history/${s._id}`)}>
                <div className="share-thumb">
                  {s.imageUrl ? (
                    <img src={s.imageUrl} alt={title} onError={(e) => { e.target.style.display = "none"; }} />
                  ) : (
                    <Icon name="home" size={22} color="var(--ink-4)" stroke={1.4} />
                  )}
                </div>
                <div className="share-body">
                  <p className="share-title">{title}</p>
                  <span className="share-date">{formatDateTime(s.sharedAt || s.createdAt)}</span>
                </div>
                <div className="share-ops">
                  <button className="su-btn su-btn-tertiary" onClick={(e) => copy(s, e)}>
                    <Icon name="link" size={15} /> Copy
                  </button>
                  <button className="share-cancel" onClick={(e) => cancel(s, e)} disabled={busy === s._id}>
                    Stop
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {toast && <div className="su-toast">{toast}</div>}
    </div>
  );
}
