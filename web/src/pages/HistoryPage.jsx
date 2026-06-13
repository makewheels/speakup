import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { api } from "../api/client.js";
import Icon from "../components/Icon.jsx";

function relativeDate(iso) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`;
  return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

export default function HistoryPage() {
  const { user } = useUser();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false);

  const PAGE = 20;

  useEffect(() => {
    api.listPractices(user.userId, 0)
      .then((data) => {
        setSessions(data);
        setHasMore(data.length === PAGE);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [user.userId]);

  const loadMore = () => {
    api.listPractices(user.userId, sessions.length)
      .then((data) => {
        setSessions((prev) => [...prev, ...data]);
        setHasMore(data.length === PAGE);
      })
      .catch(console.error);
  };

  if (loading) return <div className="page-msg">加载中…</div>;

  // 只展示真正开口评估过的练习（看了图没说的空记录不进历史）
  const shown = sessions.filter((s) => (s.attempts?.length ?? 0) > 0);

  if (shown.length === 0) {
    return (
      <div className="empty-state">
        <div className="icon-box">
          <Icon name="clock" size={28} color="var(--ink-3)" stroke={1.4} />
        </div>
        <p className="title">还没有练习记录</p>
        <p className="sub">去练习页说一段试试</p>
        <button className="su-btn su-btn-primary" style={{ maxWidth: 200 }} onClick={() => navigate("/practice")}>
          去练习
        </button>
      </div>
    );
  }

  return (
    <div className="history-page">
      <div className="page-head">
        <h2>历史</h2>
        <span className="count-label">{shown.length} 次</span>
      </div>

      <div className="history-list">
        {shown.map((s) => {
          const thumb = s.imageUrl || "";
          const lastAttempt = s.attempts?.[s.attempts.length - 1];
          const gapCount = lastAttempt?.gaps?.length ?? 0;
          const summary = lastAttempt?.summary || "";

          return (
            <div key={s._id} className="history-row" onClick={() => navigate(`/history/${s._id}`)}>
              <div className="history-thumb">
                {thumb
                  ? <img
                      src={thumb}
                      alt={s.topic}
                      onError={(e) => { e.target.style.display = "none"; }}
                    />
                  : <Icon name="home" size={22} color="var(--ink-4)" stroke={1.4} />
                }
              </div>
              <div className="history-body">
                {summary ? (
                  <p className="history-headline">{summary}</p>
                ) : (
                  <p className="history-headline muted">未评估 · 看了图没开口</p>
                )}
                <div className="history-sub">
                  <span className="history-date">{relativeDate(s.createdAt)}</span>
                  {s.topic && <span className="history-tag">{s.topic}</span>}
                  {gapCount > 0 && <span className="chip warn">{gapCount} 处差距</span>}
                </div>
              </div>
              <div className="history-arrow">
                <Icon name="next" size={16} color="var(--ink-4)" />
              </div>
            </div>
          );
        })}
      </div>

      {hasMore && (
        <button className="su-btn su-btn-tertiary" style={{ width: "100%", marginTop: 12 }} onClick={loadMore}>
          加载更多
        </button>
      )}

      <p className="list-end">· end of list ·</p>
    </div>
  );
}
