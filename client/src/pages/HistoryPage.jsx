import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { api } from "../api/client.js";

export default function HistoryPage() {
  const { user } = useUser();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listSessions(user.userId)
      .then(setSessions)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [user.userId]);

  if (loading) return <div className="page-msg">加载中...</div>;
  if (!sessions.length) return <div className="page-msg">还没有练习记录</div>;

  return (
    <div className="history-page">
      <h2>练习历史</h2>
      <div className="history-list">
        {sessions.map((s) => {
          const lastAttempt = s.attempts?.[s.attempts.length - 1];
          return (
            <Link key={s._id} to={`/practice/${s._id}`} className="history-item">
              {s.imageUrl && <img src={s.imageUrl} alt="" />}
              <div className="history-info">
                <span className="history-topic">{s.topic}</span>
                <span className="history-date">
                  {new Date(s.createdAt).toLocaleDateString("zh-CN")}
                </span>
                <span className="history-attempts">
                  尝试 {s.attempts?.length || 0} 次
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
