import { useState } from "react";
import Icon from "./Icon.jsx";
import RecordingPlayer from "./RecordingPlayer.jsx";
import PracticeMedia from "./practice/PracticeMedia.jsx";
import PracticeScenarioCard from "./practice/PracticeScenarioCard.jsx";
import PracticeFreeCard from "./practice/PracticeFreeCard.jsx";
import FeedbackGapList from "./practice/FeedbackGapList.jsx";
import SelectableNoteText from "./practice/SelectableNoteText.jsx";
import PronunciationFeedback from "./practice/PronunciationFeedback.jsx";
import ResultFooterActions from "./practice/ResultFooterActions.jsx";
import StandardAnswerCard from "./practice/StandardAnswerCard.jsx";
import { formatDateTime } from "../lib/formatDateTime.js";
import { useT } from "../i18n/useI18n.js";

const EMOJI_BLOCK_RE = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}]/gu;
const EMOJI_JOINER_RE = new RegExp("[\\uFE00-\\uFE0F\\u200D]", "gu");

const stripEmoji = (s = "") =>
  s
    .replace(EMOJI_BLOCK_RE, "")
    .replace(EMOJI_JOINER_RE, "")
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
 *  - 追问（仅 owner 模式）：chat / chatInput / setChatInput / onSend / chatBusy
 */
export default function SessionView({
  session,
  readOnly = false,
  subtitle = null,
  headerAction = null,
  chat = [],
  chatInput = "",
  setChatInput = () => {},
  onSend = () => {},
  chatBusy = false,
  noteUserId = "",
  onShare = null,
  onUnshare = null,
  shareBusy = false,
  shareStatus = "",
  shareToken = "",
}) {
  const t = useT();
  const practiceId = session?._id;
  const rawAttempts = session?.attempts || [];
  const recordings = session?.recordings || [];
  const hasMedia = session?.videoUrl || session?.imageUrl;
  const showAttemptVideo = Boolean(session?.videoUrl && rawAttempts.length > 0);
  const showHeaderImage = Boolean(session?.imageUrl && !showAttemptVideo && rawAttempts.length > 0);
  const scenario = session?.scenario || session;

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
        {showHeaderImage ? (
          <PracticeMedia
            className="detail-hero-media"
            imageUrl={session.imageUrl}
          />
        ) : rawAttempts.length > 0 && !showAttemptVideo ? (
          <div className="detail-hero-placeholder" />
        ) : null}
        <div className="detail-hero-info">
          <div className="detail-topic">
            {stripEmoji(session.title || session.topic || t("history.defaultTitle"))}
            {/* 自由说会话（mode=free）打徽章；旧数据无 mode 按场景题，不显示 */}
            {session.mode === "free" && <span className="chip free free-badge">{t("history.freeBadge")}</span>}
          </div>
          <div className="detail-when">{formatDateTime(session.createdAt)}</div>
          {subtitle && <div className="detail-subtitle">{subtitle}</div>}
        </div>
        {headerAction && <div className="detail-hero-action">{headerAction}</div>}
      </div>

      {showAttemptVideo && (
        <PracticeMedia
          className="session-practice-media session-detail-video"
          imageUrl={session.imageUrl}
          videoUrl={session.videoUrl}
        />
      )}

      {rawAttempts.length === 0 ? (
        <div className="session-practice-preview">
          {hasMedia && (
            <PracticeMedia
              className="session-practice-media"
              imageUrl={session.imageUrl}
              videoUrl={session.videoUrl}
            />
          )}
          {scenario?.kind === "free"
            ? <PracticeFreeCard freeTopic={scenario.freeTopic || ""} t={t} />
            : <PracticeScenarioCard scenario={scenario} topic={session?.topic} t={t} />}
          {!readOnly && <div className="page-msg">{t("session.noFeedback")}</div>}
        </div>
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
                  {t("session.attempt", { n: i + 1 })}
                </button>
              ))}
            </div>
          )}

          <div className="attempt-block">
            <div className="attempt-header">
              <span className="attempt-idx">{t("session.attempt", { n: idx + 1 })}</span>
              {attempt.createdAt && <span className="attempt-time">{formatDateTime(attempt.createdAt)}</span>}
            </div>
            {recording?.url && <RecordingPlayer src={recording.url} />}

            {attempt.score != null && (
              <div className="fb-score">
                <span className="fb-score-num">{Number(attempt.score).toFixed(1)}</span>
                <span className="fb-score-unit">/ 9.0</span>
                <span className="fb-score-cap">{t("practice.ieltsBand")}</span>
              </div>
            )}

            {attempt.summary && <p className="fb-summary-line">{attempt.summary}</p>}

            <SelectableNoteText practiceId={practiceId} userId={readOnly ? "" : noteUserId}>
              {(attempt.gaps || []).length > 0 && (
                <section className="result-section result-expression">
                  <div className="result-section-head">
                    <h2 className="result-section-title">{t("practice.expressionSuggestions")}</h2>
                    <span className="result-section-meta">{t("practice.suggestionCount", { n: attempt.gaps.length })}</span>
                  </div>
                  <FeedbackGapList
                    canSpeak={canSpeak}
                    gaps={attempt.gaps}
                    practiceId={practiceId}
                    showTitle={false}
                  />
                </section>
              )}

              <PronunciationFeedback
                attemptIndex={idx}
                canSpeak={canSpeak}
                practiceId={practiceId}
                pronunciation={attempt.pronunciation}
                shareToken={shareToken}
                t={t}
              />

              <StandardAnswerCard
                answer={attempt.standardAnswer}
                canSpeak={canSpeak}
                practiceId={practiceId}
                t={t}
              />
            </SelectableNoteText>

            {!readOnly && isLatest ? (
              <div className="fb-chat">
                <h2 className="result-section-title">{t("practice.askTheCoach")}</h2>
                {chat.map((m, k) => (
                  <div key={k} className={"fb-chat-msg " + m.role}>
                    {m.content || (chatBusy && k === chat.length - 1 ? <span className="fb-chat-typing">{t("practice.thinking")}</span> : "")}
                  </div>
                ))}
                <div className="fb-chat-input">
                  <textarea
                    rows={1}
                    value={chatInput}
                    placeholder={t("practice.chatPlaceholder")}
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
                  <h2 className="result-section-title">{t("practice.askTheCoach")}</h2>
                  {attempt.chat.map((m, k) => (
                    <div key={k} className={"fb-chat-msg " + m.role}>{m.content}</div>
                  ))}
                </div>
              )
            )}

            {!readOnly && (
              <ResultFooterActions
                key={idx}
                attemptIndex={idx}
                onShare={onShare}
                onUnshare={onUnshare}
                practiceId={practiceId}
                shareAriaLabel={t("practice.shareResult")}
                shareBusy={shareBusy}
                shareBusyLabel={t("practice.sharingResult")}
                shareLabel={t("session.share")}
                shareStatus={shareStatus}
                snapshot={{
                  score: attempt.score,
                  summary: attempt.summary,
                  gaps: attempt.gaps,
                  transcript: attempt.transcript,
                  round: idx + 1,
                }}
                stopSharingLabel={t("session.stopSharing")}
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}
