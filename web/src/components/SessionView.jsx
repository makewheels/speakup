import { useState } from "react";
import Icon from "./Icon.jsx";
import SpeakBtn from "./SpeakBtn.jsx";
import RecordingPlayer from "./RecordingPlayer.jsx";
import { formatDateTime } from "../lib/formatDateTime.js";

const splitSentences = (s = "") =>
  s.match(/[^.!?]+[.!?]*/g)?.map((x) => x.trim()).filter(Boolean) ?? [s];

const stripEmoji = (s = "") =>
  s
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE00}-\u{FE0F}\u{200D}]/gu, "")
    .replace(/^[\s·•・]+/, "")
    .replace(/\s{2,}/g, " ")
    .trim();

/**
 * 练习展示组件（详情页 + 分享页共用）。
 * 纯展示 + Attempt tab 切换。
 * Props:
 *  - session：练习数据
 *  - readOnly：true=分享页（隐藏付费朗读 SpeakBtn 和追问输入，chat 只读）
 *  - subtitle：标题下方副标题（如分享页「由 xxx 分享」）
 *  - headerAction：hero 右侧操作区（如详情页的分享按钮）
 *  - 追问（仅 owner 模式）：chat / chatInput / setChatInput / onSend / chatBusy
 */
export default function SessionView({
  session,
  readOnly = false,
  subtitle = null,
  headerAction = null,
  belowHero = null,
  chat = [],
  chatInput = "",
  setChatInput = () => {},
  onSend = () => {},
  chatBusy = false,
}) {
  const practiceId = session?._id;
  const rawAttempts = session?.attempts || [];
  const recordings = session?.recordings || [];
  const thumb = session?.imageUrl || "";

  // 默认选中最新一轮
  const [sel, setSel] = useState(Math.max(0, rawAttempts.length - 1));
  const idx = Math.min(sel, rawAttempts.length - 1);
  const attempt = rawAttempts[idx];
  const recording = recordings[idx];
  const isLatest = idx === rawAttempts.length - 1;
  const canSpeak = !readOnly; // 付费 TTS 朗读只对本人开放

  return (
    <div className="session-view">
      <div className="detail-hero">
        {thumb ? (
          <img src={thumb} alt={session.topic} className="detail-hero-img" onError={(e) => { e.target.style.display = "none"; }} />
        ) : (
          <div className="detail-hero-placeholder" />
        )}
        <div className="detail-hero-info">
          <div className="detail-topic">{stripEmoji(session.title || session.topic || "Practice")}</div>
          <div className="detail-when">{formatDateTime(session.createdAt)}</div>
          {subtitle && <div className="detail-subtitle">{subtitle}</div>}
        </div>
        {headerAction && <div className="detail-hero-action">{headerAction}</div>}
      </div>

      {belowHero}

      {rawAttempts.length === 0 ? (
        <div className="page-msg" style={{ paddingTop: 40 }}>No AI feedback for this practice yet</div>
      ) : (
        <>
          {rawAttempts.length > 1 && (
            <div className="attempt-tabs">
              {rawAttempts.map((_, i) => (
                <button
                  key={i}
                  className={"attempt-tab" + (i === idx ? " active" : "")}
                  onClick={() => setSel(i)}
                >
                  Attempt {i + 1}
                </button>
              ))}
            </div>
          )}

          <div className="attempt-block">
            <div className="attempt-header">
              <span className="attempt-idx">Attempt {idx + 1}</span>
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
                <div className="fb-card-label native">Native version{canSpeak && <SpeakBtn text={attempt.nativeVersion} practiceId={practiceId} />}</div>
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
                        {canSpeak && <SpeakBtn text={g.better} practiceId={practiceId} />}
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

            {!readOnly && isLatest ? (
              <div className="fb-chat">
                <div className="fb-section-label">Ask the coach</div>
                {chat.map((m, k) => (
                  <div key={k} className={"fb-chat-msg " + m.role}>
                    {m.content || (chatBusy && k === chat.length - 1 ? <span className="fb-chat-typing">Thinking…</span> : "")}
                  </div>
                ))}
                <div className="fb-chat-input">
                  <textarea
                    rows={1}
                    value={chatInput}
                    placeholder="Ask about this feedback — why a change, more examples, how to say it elsewhere…"
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
                    disabled={chatBusy}
                  />
                  <button className="su-btn su-btn-primary" onClick={onSend} disabled={chatBusy || !chatInput.trim()}>
                    <Icon name="next" size={16} />
                  </button>
                </div>
              </div>
            ) : (
              attempt.chat?.length > 0 && (
                <div className="fb-chat">
                  <div className="fb-section-label">Ask the coach</div>
                  {attempt.chat.map((m, k) => (
                    <div key={k} className={"fb-chat-msg " + m.role}>{m.content}</div>
                  ))}
                </div>
              )
            )}
          </div>
        </>
      )}
    </div>
  );
}
