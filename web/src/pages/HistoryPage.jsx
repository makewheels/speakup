import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { api } from "../api/client.js";
import Icon from "../components/Icon.jsx";

function formatDateTime(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const sameYear = d.getFullYear() === new Date().getFullYear();
  const date = d.toLocaleDateString(
    "zh-CN",
    sameYear ? { month: "long", day: "numeric" } : { year: "numeric", month: "long", day: "numeric" }
  );
  const time = d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${date} ${time}`;
}

export default function HistoryPage() {
  const { user } = useUser();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const [expanded, setExpanded] = useState(() => new Set());

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

  const toggle = (key) =>
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key); else n.add(key);
      return n;
    });

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

  // 按题目(scenarioId)分组：同一场景练多次 = 一个题目，点开看每次
  const map = new Map();
  for (const s of shown) {
    const key = s.scenarioId || s._id;
    if (!map.has(key)) {
      map.set(key, { key, title: s.title || s.topic || "练习", thumb: s.imageUrl || "", sessions: [] });
    }
    map.get(key).sessions.push(s);
  }
  const groups = [...map.values()].sort(
    (a, b) => new Date(b.sessions[0].createdAt) - new Date(a.sessions[0].createdAt)
  );

  return (
    <div className="history-page">
      <div className="page-head">
        <h2>历史</h2>
        <span className="count-label">{groups.length} 个场景</span>
      </div>

      <div className="history-list">
        {groups.map((g) => {
          const latest = g.sessions[0];
          const multi = g.sessions.length > 1;
          const open = expanded.has(g.key);
          const lastAttempt = latest.attempts?.[latest.attempts.length - 1];
          const gapCount = lastAttempt?.gaps?.length ?? 0;

          return (
            <div key={g.key} className="history-group">
              <div
                className="history-row"
                onClick={() => (multi ? toggle(g.key) : navigate(`/history/${latest._id}`))}
              >
                <div className="history-thumb">
                  {g.thumb ? (
                    <img src={g.thumb} alt={g.title} onError={(e) => { e.target.style.display = "none"; }} />
                  ) : (
                    <Icon name="home" size={22} color="var(--ink-4)" stroke={1.4} />
                  )}
                </div>
                <div className="history-body">
                  <p className="history-headline">{g.title}</p>
                  <div className="history-sub">
                    <span className="history-date">{formatDateTime(latest.createdAt)}</span>
                    {multi && <span className="chip">练了 {g.sessions.length} 次</span>}
                    {!multi && gapCount > 0 && <span className="chip warn">{gapCount} 处差距</span>}
                  </div>
                </div>
                <div className={"history-arrow" + (multi && open ? " open" : "")}>
                  <Icon name="next" size={16} color="var(--ink-4)" />
                </div>
              </div>

              {multi && open && (
                <div className="history-sessions">
                  {g.sessions.map((s, k) => {
                    const a = s.attempts?.[s.attempts.length - 1];
                    const gc = a?.gaps?.length ?? 0;
                    return (
                      <div key={s._id} className="history-subrow" onClick={() => navigate(`/history/${s._id}`)}>
                        <span className="history-subidx">第 {g.sessions.length - k} 次</span>
                        <span className="history-subtime">{formatDateTime(s.createdAt)}</span>
                        {gc > 0 && <span className="chip warn">{gc} 处</span>}
                        <Icon name="next" size={14} color="var(--ink-4)" />
                      </div>
                    );
                  })}
                </div>
              )}
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
