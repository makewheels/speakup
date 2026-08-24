import { useLayoutEffect } from "react";
import Icon from "../Icon.jsx";
import PracticeMedia from "./PracticeMedia.jsx";
import PracticeScenarioCard from "./PracticeScenarioCard.jsx";
import PracticeFreeCard from "./PracticeFreeCard.jsx";
import FeedbackBar from "./FeedbackBar.jsx";
import FeedbackGapList from "./FeedbackGapList.jsx";
import SelectableNoteText from "./SelectableNoteText.jsx";
import PronunciationFeedback from "./PronunciationFeedback.jsx";
import StandardAnswerCard from "./StandardAnswerCard.jsx";
import { useT } from "../../i18n/useI18n.js";

function ScoreBadge({ loading, score }) {
  const t = useT();
  const displayedScore = score == null ? "–" : Number(score).toFixed(1);
  return (
    <div className={`fb-score${loading ? " is-loading" : ""}`} aria-busy={loading || undefined}>
      <span className="fb-score-num">{loading ? "–" : displayedScore}</span>
      <span className="fb-score-unit">/ 9.0</span>
      <span className="fb-score-cap">{t("practice.ieltsBand")}</span>
    </div>
  );
}

export default function PracticeFeedbackView({
  actionsDisabled = false,
  chat,
  chatBusy,
  chatInput,
  modeSwitch,
  onShare,
  loading = false,
  streamingLen = 0,
  pronunciation,
  pronunciationLoading = false,
  result,
  retrySame,
  round,
  savedMap,
  scenario,
  sendChat,
  session,
  setChatInput,
  shareBusy = false,
  shareStatus = "",
  startNewRound,
  t,
  toggleGap,
  transcript,
  userId,
}) {
  const gaps = result.gaps ?? [];
  const progress = result.progress;
  const passed = progress?.verdict === "passed";
  const hasProgressDetails = Boolean(
    progress?.comment || progress?.fixed?.length || progress?.remaining?.length,
  );
  const isFree = session?.mode === "free";
  const hasAnswer = Boolean((result.standardAnswer || "").trim());

  // 只在结果页首帧绘制前回到顶部；流式结束、媒体加载和发音结果到达时都不再滚动。
  useLayoutEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, []);

  return (
    <div className="practice-page fb-page fade-in">
      <div className="fb-score-anchor">
        <ScoreBadge loading={loading} score={result.score} />
        <div>
          <span className="attempt-badge">{t("practice.attemptBadge", { n: round ?? 1 })}</span>
        </div>
      </div>

      {loading && (
        <section className="result-section result-loading" aria-live="polite">
          <h2 className="result-section-title">{t("practice.expressionSuggestions")}</h2>
          <div className="result-loading-transcript">
            <span>{t("practice.youSaid")}</span>
            <p>{transcript}</p>
          </div>
          <p className="result-loading-status">
            <i className="fb-generating-dot" aria-hidden="true" />
            {streamingLen > 0
              ? t("practice.writingChars", { n: streamingLen })
              : t("practice.aiReviewing")}
          </p>
        </section>
      )}

      {!loading && result.summary && <p className="fb-summary-line">{result.summary}</p>}

      {modeSwitch}
      {!isFree && (session?.videoUrl || session?.imageUrl) && (
        <PracticeMedia
          className="fb-img"
          imageUrl={session.imageUrl}
          videoUrl={session.videoUrl}
        />
      )}
      {isFree
        ? <PracticeFreeCard freeTopic={scenario?.freeTopic || session?.freeTopic || ""} t={t} />
        : <PracticeScenarioCard scenario={scenario} topic={session?.topic} t={t} />}

      {!loading && passed && <div className="fb-passed">{t("practice.soundedNative")}</div>}

      {!loading && hasProgressDetails && (
        <div className="fb-progress">
          {progress.comment && <p className="fb-progress-comment">{progress.comment}</p>}
          {progress.fixed?.length > 0 && (
            <div className="fb-progress-list fixed">
              <span className="label">{t("practice.usedThisTime")}</span>
              {progress.fixed.map((x, i) => <span key={i} className="chip">{x}</span>)}
            </div>
          )}
          {progress.remaining?.length > 0 && (
            <div className="fb-progress-list remaining">
              <span className="label">{t("practice.stillMissing")}</span>
              {progress.remaining.map((x, i) => <span key={i} className="chip">{x}</span>)}
            </div>
          )}
        </div>
      )}

      <SelectableNoteText practiceId={session?._id} userId={userId}>
        {!loading && gaps.length > 0 && (
          <section className="result-section result-expression">
            <div className="result-section-head">
              <h2 className="result-section-title">{t("practice.expressionSuggestions")}</h2>
              <span className="result-section-meta">{t("practice.suggestionCount", { n: gaps.length })}</span>
            </div>
            <FeedbackGapList
              gaps={gaps}
              onToggleGap={toggleGap}
              practiceId={session?._id}
              savedMap={savedMap}
              showTitle={false}
            />
          </section>
        )}

        {!loading && <PronunciationFeedback
          attemptIndex={Math.max(0, round - 1)}
          loading={pronunciationLoading}
          practiceId={session?._id}
          pronunciation={pronunciation}
          t={t}
        />}

        {!loading && <StandardAnswerCard
          answer={result.standardAnswer}
          practiceId={session?._id}
          t={t}
        />}
      </SelectableNoteText>
      {!loading && gaps.length === 0 && (
        <div className="fb-empty-feedback">
          {hasAnswer
            ? t("practice.noGaps")
            : t("practice.noUsableFeedback")}
        </div>
      )}

      {!loading && <div className="fb-chat">
        <h2 className="result-section-title">{t("practice.askTheCoach")}</h2>
        {chat.map((m, i) => (
          <div key={i} className={"fb-chat-msg " + m.role}>
            {m.content || (chatBusy && i === chat.length - 1 ? <span className="fb-chat-typing">{t("practice.thinking")}</span> : "")}
          </div>
        ))}
        <div className="fb-chat-input">
          <textarea
            rows={1}
            value={chatInput}
            placeholder={t("practice.chatPlaceholder")}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
            disabled={chatBusy}
          />
          <button className="su-btn su-btn-primary" onClick={sendChat} disabled={chatBusy || !chatInput.trim()}>
            <Icon name="next" size={16} />
          </button>
        </div>
      </div>}

      {!loading && <FeedbackBar
        practiceId={session?._id}
        attemptIndex={Math.max(0, (round ?? 1) - 1)}
        snapshot={{
          score: result.score,
          summary: result.summary,
          gaps: result.gaps,
          transcript,
          round,
        }}
      />}

      {/* 重说不封顶：重试按钮常驻；当前轮次由页面顶部徽章统一表达。 */}
      {!loading && <div className="actions-row" style={{ marginTop: 8 }}>
        <button className="su-btn su-btn-primary" onClick={retrySame} disabled={actionsDisabled} style={{ flex: 2, height: 48 }}>
          <Icon name="refresh" size={16} />&nbsp;{t("practice.sayItAgain")}
        </button>
        <button className="su-btn su-btn-secondary" onClick={() => startNewRound(session?.scenarioId)} disabled={actionsDisabled} style={{ flex: 1, height: 48 }}>
          {t(isFree ? "practice.nextTopic" : passed ? "practice.nextScenario" : "practice.next")}&nbsp;<Icon name="next" size={16} />
        </button>
      </div>}

      {!loading && <div className="fb-result-share-row">
        <button className="su-btn su-btn-tertiary share-btn" type="button" onClick={onShare} disabled={shareBusy}>
          <Icon name="share" size={16} />
          {shareBusy ? t("practice.sharingResult") : t("practice.shareResult")}
        </button>
        {shareStatus && <span className="fb-result-share-status" role="status">{shareStatus}</span>}
      </div>}
    </div>
  );
}
