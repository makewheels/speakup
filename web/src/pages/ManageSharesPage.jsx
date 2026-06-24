import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { useT } from "../i18n/index.jsx";
import { api } from "../api/client.js";
import Icon from "../components/Icon.jsx";
import { copyShare } from "../lib/share.js";
import { formatDateTime } from "../lib/formatDateTime.js";

export default function ManageSharesPage() {
  const { user } = useUser();
  const navigate = useNavigate();
  const t = useT();
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
      flash(t("manageShares.linkCopied"));
    } catch (err) {
      flash(t("manageShares.copyFailed", { msg: err.message }));
    }
  };

  const cancel = async (s, e) => {
    e.stopPropagation();
    if (busy) return;
    setBusy(s._id);
    try {
      await api.unsharePractice(s._id, user.userId);
      setItems((prev) => prev.filter((x) => x._id !== s._id));
      flash(t("manageShares.sharingStopped"));
    } catch (err) {
      flash(t("manageShares.failed", { msg: err.message }));
    } finally {
      setBusy("");
    }
  };

  if (loading) return <div className="page-msg">{t("common.loading")}</div>;

  return (
    <div className="manage-shares-page">
      <div className="page-head">
        <h2>{t("manageShares.title")}</h2>
        <span className="count-label">{t("manageShares.count", { n: items.length })}</span>
      </div>

      {items.length === 0 ? (
        <div className="empty-state">
          <div className="icon-box">
            <Icon name="share" size={28} color="var(--ink-3)" stroke={1.4} />
          </div>
          <p className="title">{t("manageShares.emptyTitle")}</p>
          <p className="sub">{t("manageShares.emptySub")}</p>
          <button className="su-btn su-btn-primary" style={{ maxWidth: 200 }} onClick={() => navigate("/history")}>
            {t("manageShares.goToHistory")}
          </button>
        </div>
      ) : (
        <div className="share-list">
          {items.map((s) => {
            const title = s.title || s.topic || t("manageShares.defaultTitle");
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
                    <Icon name="link" size={15} /> {t("manageShares.copy")}
                  </button>
                  <button className="share-cancel" onClick={(e) => cancel(s, e)} disabled={busy === s._id}>
                    {t("manageShares.stop")}
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
