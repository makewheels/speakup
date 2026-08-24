import { useEffect, useRef } from "react";
import Icon from "../Icon.jsx";
import SpeakBtn from "../SpeakBtn.jsx";
import PracticeMedia from "./PracticeMedia.jsx";
import PracticeScenarioCard from "./PracticeScenarioCard.jsx";
import PracticeFreeCard from "./PracticeFreeCard.jsx";
import FeedbackBar from "./FeedbackBar.jsx";
import FeedbackGapList from "./FeedbackGapList.jsx";
import SelectableNoteText from "./SelectableNoteText.jsx";
import SentenceCorrectionList from "./SentenceCorrectionList.jsx";
import PronunciationFeedback from "./PronunciationFeedback.jsx";
import { useT } from "../../i18n/useI18n.js";

const splitSentences = (s = "") =>
  s.match(/[^.!?]+[.!?]*/g)?.map((x) => x.trim()).filter(Boolean) ?? [s];

function SpeakBtns({ text, practiceId }) {
  return <SpeakBtn text={text} practiceId={practiceId} />;
}

function ScoreBadge({ score }) {
  const t = useT();
  if (score == null) return null;
  return (
    <div className="fb-score">
      <span className="fb-score-num">{Number(score).toFixed(1)}</span>
      <span className="fb-score-unit">/ 9.0</span>
      <span className="fb-score-cap">{t("practice.ieltsBand")}</span>
    </div>
  );
}

export default function PracticeFeedbackView({
  actionsDisabled = false,
  autoSaved,
  chat,
  chatBusy,
  chatInput,
  modeSwitch,
  onShare,
  loading = false,
  streamingLen = 0,
  pronunciation,
  pronunciationLoading = false,
  recordingUrl,
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
  const hasAnswer = Boolean(
    (result.nativeVersion || "").trim() || (result.standardAnswer || "").trim(),
  );

  // 结果页从雅思分数开始看起：题目卡片和大图在上方，向上滚可回看。
  // 挂载瞬间上方的大图/视频高度可能尚未定型（加载失败会塌缩、慢加载会位移），
  // scrollIntoView 一次性定位会被这些位移带偏（手机上常见：分数被顶到屏幕外）。
  // 改为按锚点当前几何位置显式 scrollTo，并在随后 1 秒多内复校几次，位移发生后自动归位。
  const scoreAnchorRef = useRef(null);
  useEffect(() => {
    const el = scoreAnchorRef.current;
    if (!el) return;
    let userScrolled = false;
    const markUserScroll = () => { userScrolled = true; };
    const scrollToScore = () => {
      if (userScrolled) return; // 用户已经开始自己滚了就别再拽回去
      const top = el.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({ top, behavior: "auto" });
    };
    scrollToScore();
    const raf = requestAnimationFrame(scrollToScore);
    const timers = [120, 350, 700, 1200].map((ms) => setTimeout(scrollToScore, ms));
    window.addEventListener("touchmove", markUserScroll);
    window.addEventListener("wheel", markUserScroll);
    return () => {
      cancelAnimationFrame(raf);
      timers.forEach(clearTimeout);
      window.removeEventListener("touchmove", markUserScroll);
      window.removeEventListener("wheel", markUserScroll);
    };
  }, [loading]);

  return (
    <div className="practice-page fb-page fade-in">
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

      <div ref={scoreAnchorRef} className="fb-score-anchor">
        <div>
          <span className="attempt-badge">{t("practice.attemptBadge", { n: round ?? 1 })}</span>
        </div>
        {!loading && <ScoreBadge score={result.score} />}
      </div>

      {loading && (
        <section className="fb-sentence-section" aria-live="polite">
          <div className="fb-card-label">{t("practice.sentenceComparison")}</div>
          <article className="fb-sentence-pair">
            <div className="fb-sentence-row is-original">
              <span>{t("practice.youSaid")}</span>
              <p>{transcript}</p>
            </div>
            <div className="fb-sentence-row is-corrected fb-generating-inline">
              <span>{t("practice.nativeVersion")}</span>
              <p><i className="fb-generating-dot" aria-hidden="true" /> {streamingLen > 0
                ? t("practice.writingChars", { n: streamingLen })
                : t("practice.aiReviewing")}</p>
            </div>
          </article>
        </section>
      )}

      {!loading && result.summary && <p className="fb-summary-line">{result.summary}</p>}

      {!loading && <div className="fb-result-share-row">
        <button className="su-btn su-btn-tertiary share-btn" type="button" onClick={onShare} disabled={shareBusy}>
          <Icon name="share" size={16} />
          {shareBusy ? t("practice.sharingResult") : t("practice.shareResult")}
        </button>
        {shareStatus && <span className="fb-result-share-status" role="status">{shareStatus}</span>}
      </div>}

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
        {!loading && <SentenceCorrectionList
          practiceId={session?._id}
          recordingUrl={recordingUrl}
          result={result}
          t={t}
          transcript={transcript}
        />}

        {!loading && <PronunciationFeedback
          loading={pronunciationLoading}
          practiceId={session?._id}
          pronunciation={pronunciation}
          recordingUrl={recordingUrl}
          t={t}
        />}

        {!loading && result.standardAnswer && (
          <details className="fb-native-card fb-standard-card" data-note-context={result.standardAnswer}>
            <summary className="fb-card-label standard">
              {t("practice.standardAnswer")}
              <SpeakBtns text={result.standardAnswer} practiceId={session?._id} />
            </summary>
            {splitSentences(result.standardAnswer).map((s, i) => (
              <p key={i} className="fb-native-text">{s}</p>
            ))}
          </details>
        )}

        {!loading && gaps.length > 0 && (
          <details className="fb-gap-details">
            <summary>{t("practice.gapsTitle", { n: gaps.length })}</summary>
            <FeedbackGapList
              gaps={gaps}
              onToggleGap={toggleGap}
              practiceId={session?._id}
              savedMap={savedMap}
              showTitle={false}
            />
          </details>
        )}
      </SelectableNoteText>
      {!loading && gaps.length === 0 && (
        <div className="fb-empty-feedback">
          {hasAnswer
            ? t("practice.noGaps")
            : t("practice.noUsableFeedback")}
        </div>
      )}

      {!loading && autoSaved > 0 && (
        <p className="fb-autosaved">{t("practice.autoSaved", { n: autoSaved })}</p>
      )}

      {!loading && <div className="fb-chat">
        <div className="fb-section-label">{t("practice.askTheCoach")}</div>
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
          nativeVersion: result.nativeVersion,
          gaps: result.gaps,
          transcript,
          round,
        }}
      />}

      {/* 重说不封顶：重试按钮常驻，带上即将开始的第 N 次尝试；不想再说就点下一个 */}
      {!loading && <div className="actions-row" style={{ marginTop: 8 }}>
        <button className="su-btn su-btn-primary" onClick={retrySame} disabled={actionsDisabled} style={{ flex: 2, height: 48 }}>
          <Icon name="refresh" size={16} />&nbsp;{t("practice.sayItAgain", { n: (round ?? 1) + 1 })}
        </button>
        <button className="su-btn su-btn-secondary" onClick={() => startNewRound(session?.scenarioId)} disabled={actionsDisabled} style={{ flex: 1, height: 48 }}>
          {t(isFree ? "practice.nextTopic" : passed ? "practice.nextScenario" : "practice.next")}&nbsp;<Icon name="next" size={16} />
        </button>
      </div>}
    </div>
  );
}
