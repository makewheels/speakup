import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
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

export default function SessionDetailPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getSession(sessionId)
      .then(setSession)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) return <div className="page-msg">加载中…</div>;
  if (!session) return <div className="page-msg">会话不存在</div>;

  const thumb = session.ossImageUrl || session.imageUrl || "";
  const attempts = [...(session.attempts || [])].reverse();

  return (
    <div className="session-detail-page fade-in">
      <button className="detail-back" onClick={() => navigate(-1)}>
        <Icon name="back" size={20} /> 返回
      </button>

      <div className="detail-hero">
        {thumb ? (
          <img src={thumb} alt={session.topic} className="detail-hero-img" />
        ) : (
          <div className="detail-hero-placeholder" />
        )}
        <div className="detail-hero-info">
          <div className="eyebrow">scene</div>
          <div className="detail-topic">{session.topic || "练习"}</div>
          <div className="detail-when">{relativeDate(session.createdAt)}</div>
        </div>
      </div>

      {attempts.length === 0 ? (
        <div className="page-msg" style={{ paddingTop: 40 }}>这次练习还没有 AI 评估</div>
      ) : (
        attempts.map((attempt, i) => (
          <div key={i} className="attempt-block">
            <div className="attempt-header">
              <span className="eyebrow">第 {attempts.length - i} 次尝试</span>
              {attempt.createdAt && (
                <span className="attempt-time">{relativeDate(attempt.createdAt)}</span>
              )}
            </div>

            {attempt.transcript && (
              <section className="su-card you-card" style={{ marginBottom: 10 }}>
                <div className="card-eyebrow">
                  <span className="eyebrow">你说的</span>
                </div>
                <div className="en">{attempt.transcript}</div>
              </section>
            )}

            {attempt.summary && (
              <div className="attempt-summary">
                <div className="eyebrow" style={{ marginBottom: 6 }}>summary</div>
                <p className="attempt-summary-text">{attempt.summary}</p>
              </div>
            )}

            {attempt.nativeVersion && (
              <section className="su-card native-card" style={{ marginBottom: 10 }}>
                <div className="card-eyebrow">
                  <span className="eyebrow" style={{ color: "var(--accent)" }}>more native</span>
                  <span className="chip accent">改写</span>
                </div>
                <div className="en">{attempt.nativeVersion}</div>
              </section>
            )}

            {attempt.gaps?.length > 0 && (
              <>
                <h3 className="section-title" style={{ marginTop: 14 }}>
                  差距点<span className="count">· {attempt.gaps.length} 处</span>
                </h3>
                <div style={{ marginBottom: 18 }}>
                  {attempt.gaps.map((g, j) => (
                    <div key={j} className="su-corr">
                      <div className="from">{g.original}</div>
                      <div className="arrow">→</div>
                      <div className="to">{g.better}</div>
                      <div className="reason">
                        {g.category && <span className="cat">{g.category}</span>}
                        {g.why}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {i < attempts.length - 1 && <hr className="hr" />}
          </div>
        ))
      )}
    </div>
  );
}
