import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client.js";
import Icon from "../components/Icon.jsx";
import SpeakBtn from "../components/SpeakBtn.jsx";
import RecordingPlayer from "../components/RecordingPlayer.jsx";

const splitSentences = (s = "") =>
  s.match(/[^.!?]+[.!?]*/g)?.map((x) => x.trim()).filter(Boolean) ?? [s];

const stripEmoji = (s = "") =>
  s
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE00}-\u{FE0F}\u{200D}]/gu, "")
    .replace(/^[\s·•・]+/, "")
    .replace(/\s{2,}/g, " ")
    .trim();

function formatDateTime(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const pad = (n) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
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

  if (loading) return <div className="page-msg">Loading…</div>;
  if (!session) return <div className="page-msg">Practice not found</div>;

  const thumb = session.imageUrl || "";
  const rawAttempts = session.attempts || [];
  const recordings = session.recordings || [];
  const attempts = [...rawAttempts].reverse();

  return (
    <div className="session-detail-page fade-in">
      <button className="detail-back" onClick={() => navigate(-1)}>
        <Icon name="back" size={20} /> Back
      </button>

      <div className="detail-hero">
        {thumb ? (
          <img src={thumb} alt={session.topic} className="detail-hero-img" onError={(e) => { e.target.style.display = "none"; }} />
        ) : (
          <div className="detail-hero-placeholder" />
        )}
        <div className="detail-hero-info">
          <div className="detail-topic">{stripEmoji(session.title || session.topic || "Practice")}</div>
          <div className="detail-when">{formatDateTime(session.createdAt)}</div>
        </div>
      </div>

      {attempts.length === 0 ? (
        <div className="page-msg" style={{ paddingTop: 40 }}>No AI feedback for this practice yet</div>
      ) : (
        attempts.map((attempt, i) => {
          const origIdx = rawAttempts.length - 1 - i;
          const recording = recordings[origIdx];
          return (
            <div key={i} className="attempt-block">
              <div className="attempt-header">
                <span className="attempt-idx">Attempt {attempts.length - i}</span>
                {attempt.createdAt && <span className="attempt-time">{formatDateTime(attempt.createdAt)}</span>}
              </div>
              {recording?.url && <RecordingPlayer src={recording.url} />}

              {attempt.score != null && (
                <div className="fb-score">
                  <span className="fb-score-num">{Number(attempt.score).toFixed(1)}</span>
                  <span className="fb-score-unit">/ 9.0</span>
                  <span className="fb-score-cap">IELTS band</span>
                </div>
              )}

              {attempt.transcript && (
                <div className="fb-transcript-card">
                  <div className="fb-card-label">You said</div>
                  <p className="fb-transcript-text">{attempt.transcript}</p>
                </div>
              )}

              {attempt.nativeVersion && (
                <div className="fb-native-card">
                  <div className="fb-card-label native">Native version<SpeakBtn text={attempt.nativeVersion} practiceId={practiceId} /></div>
                  {splitSentences(attempt.nativeVersion).map((s, k) => (
                    <p key={k} className="fb-native-text">{s}</p>
                  ))}
                </div>
              )}

              {attempt.gaps?.length > 0 && (
                <div className="fb-gaps-section">
                  <div className="fb-section-label">Gaps · {attempt.gaps.length}</div>
                  {attempt.gaps.map((g, j) => (
                    <div key={j} className="fb-gap-card">
                      <div className="fb-gap-head">
                        <span className="fb-gap-num">{j + 1}</span>
                      </div>
                      <div className="fb-gap-table">
                        <div className="fb-gap-line is-said">
                          <span className="fb-gap-tag">You said</span>
                          <span className="fb-gap-said">{g.original}</span>
                        </div>
                        <div className="fb-gap-line is-fix">
                          <span className="fb-gap-tag">Say this</span>
                          <span className="fb-gap-fix">{g.better}</span>
                          <SpeakBtn text={g.better} practiceId={practiceId} />
                        </div>
                        {g.why && (
                          <div className="fb-gap-line">
                            <span className="fb-gap-tag">Why</span>
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
