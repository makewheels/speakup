import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client.js";
import { speak } from "../utils/tts.js";
import Icon from "../components/Icon.jsx";

const CAT_ZH = { grammar: "语法", naturalness: "自然度", vocabulary: "用词", register: "语体" };

const stripEmoji = (s = "") =>
  s
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE00}-\u{FE0F}\u{200D}]/gu, "")
    .replace(/^[\s·•・]+/, "")
    .replace(/\s{2,}/g, " ")
    .trim();

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

function SpeakBtn({ text }) {
  if (!text) return null;
  return (
    <button className="spk-btn" title="朗读" aria-label="朗读" onClick={() => speak(text)}>
      <Icon name="volume" size={16} />
    </button>
  );
}

export default function SessionDetailPage() {
  const { practiceId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getPractice(practiceId)
      .then(setSession)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [practiceId]);

  if (loading) return <div className="page-msg">加载中…</div>;
  if (!session) return <div className="page-msg">练习不存在</div>;

  const thumb = session.imageUrl || "";
  const rawAttempts = session.attempts || [];
  const recordings = session.recordings || [];
  const attempts = [...rawAttempts].reverse();

  return (
    <div className="session-detail-page fade-in">
      <button className="detail-back" onClick={() => navigate(-1)}>
        <Icon name="back" size={20} /> 返回
      </button>

      <div className="detail-hero">
        {thumb ? (
          <img src={thumb} alt={session.topic} className="detail-hero-img" onError={(e) => { e.target.style.display = "none"; }} />
        ) : (
          <div className="detail-hero-placeholder" />
        )}
        <div className="detail-hero-info">
          <div className="detail-topic">{stripEmoji(session.title || session.topic || "练习")}</div>
          <div className="detail-when">{formatDateTime(session.createdAt)}</div>
        </div>
      </div>

      {attempts.length === 0 ? (
        <div className="page-msg" style={{ paddingTop: 40 }}>这次练习还没有 AI 评估</div>
      ) : (
        attempts.map((attempt, i) => {
          const origIdx = rawAttempts.length - 1 - i;
          const recording = recordings[origIdx];
          return (
            <div key={i} className="attempt-block">
              <div className="attempt-header">
                <span className="attempt-idx">第 {attempts.length - i} 次</span>
                {attempt.createdAt && <span className="attempt-time">{formatDateTime(attempt.createdAt)}</span>}
              </div>
              {recording?.url && <audio controls src={recording.url} className="recording-player" />}

              {attempt.transcript && (
                <div className="fb-transcript-card">
                  <div className="fb-card-label">你说的</div>
                  <p className="fb-transcript-text">{attempt.transcript}</p>
                </div>
              )}

              {attempt.nativeVersion && (
                <div className="fb-native-card">
                  <div className="fb-card-label native">Native 会这么说</div>
                  <p className="fb-native-text">{attempt.nativeVersion}<SpeakBtn text={attempt.nativeVersion} /></p>
                </div>
              )}

              {attempt.summary && <p className="fb-summary-line">{attempt.summary}</p>}

              {attempt.gaps?.length > 0 && (
                <div className="fb-gaps-section">
                  <div className="fb-section-label">差距点 · {attempt.gaps.length} 处</div>
                  {attempt.gaps.map((g, j) => (
                    <div key={j} className="fb-gap-card">
                      <div className="fb-gap-head">
                        <span className="fb-gap-num">{j + 1}</span>
                        {g.category && <span className="fb-gap-cat">{CAT_ZH[g.category] ?? g.category}</span>}
                      </div>
                      <div className="fb-gap-table">
                        <div className="fb-gap-line">
                          <span className="fb-gap-tag">我说的</span>
                          <span className="fb-gap-said">{g.original}</span>
                        </div>
                        <div className="fb-gap-line">
                          <span className="fb-gap-tag">应该说</span>
                          <span className="fb-gap-fix">{g.better}</span>
                          <SpeakBtn text={g.better} />
                        </div>
                        {g.why && (
                          <div className="fb-gap-line">
                            <span className="fb-gap-tag">为什么</span>
                            <span className="fb-gap-whytext">{g.why}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {i < attempts.length - 1 && <hr className="hr" />}
            </div>
          );
        })
      )}
    </div>
  );
}
