import { useEffect, useRef } from "react";
import Icon from "../Icon.jsx";
import RecordingPlayBtn from "../RecordingPlayBtn.jsx";
import SpeakBtn from "../SpeakBtn.jsx";
import PracticeMedia from "./PracticeMedia.jsx";
import PracticeScenarioCard from "./PracticeScenarioCard.jsx";
import FeedbackBar from "./FeedbackBar.jsx";
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
  noteSavedId,
  recordingUrl,
  result,
  retrySame,
  round,
  savedMap,
  scenario,
  sendChat,
  session,
  setChatInput,
  startNewRound,
  t,
  toggleGap,
  toggleNote,
  transcript,
}) {
  const gaps = result.gaps ?? [];
  const progress = result.progress;
  const passed = progress?.verdict === "passed";

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
  }, []);

  return (
    <div className="practice-page fb-page fade-in">
      {(session?.videoUrl || session?.imageUrl) && (
        <PracticeMedia
          className="fb-img"
          imageUrl={session.imageUrl}
          videoUrl={session.videoUrl}
        />
      )}
      <PracticeScenarioCard scenario={scenario} topic={session?.topic} t={t} />

      <div ref={scoreAnchorRef} className="fb-score-anchor">
        <div>
          <span className="attempt-badge">{t("practice.attemptBadge", { n: round ?? 1 })}</span>
        </div>
        <ScoreBadge score={result.score} />
      </div>

      {result.summary && <p className="fb-summary-line">{result.summary}</p>}

      {passed && <div className="fb-passed">{t("practice.soundedNative")}</div>}

      {progress && (
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

      {transcript && (
        <div className="fb-transcript-card">
          <div className="fb-card-label">
            {t("practice.youSaid")}
            {recordingUrl && <RecordingPlayBtn src={recordingUrl} />}
          </div>
          <p className="fb-transcript-text">{transcript}</p>
        </div>
      )}

      {result.nativeVersion && (
        <div className="fb-native-card">
          <div className="fb-card-label native">
            {t("practice.nativeVersion")}
            <SpeakBtns text={result.nativeVersion} practiceId={session?._id} />
          </div>
          {splitSentences(result.nativeVersion).map((s, i) => (
            <p key={i} className="fb-native-text">{s}</p>
          ))}
        </div>
      )}

      {result.standardAnswer && (
        <div className="fb-native-card fb-standard-card">
          <div className="fb-card-label standard">
            {t("practice.standardAnswer")}
            <SpeakBtns text={result.standardAnswer} practiceId={session?._id} />
            <button
              className={"fb-note-add" + (noteSavedId ? " added" : "")}
              onClick={toggleNote}
              title={noteSavedId ? t("practice.removeTitle") : t("practice.saveAsNote")}
            >
              {noteSavedId
                ? <><Icon name="check" size={13} />&nbsp;{t("practice.noteSaved")}</>
                : <><Icon name="save" size={13} />&nbsp;{t("practice.saveAsNote")}</>}
            </button>
          </div>
          {splitSentences(result.standardAnswer).map((s, i) => (
            <p key={i} className="fb-native-text">{s}</p>
          ))}
        </div>
      )}

      {gaps.length > 0 && (
        <div className="fb-gaps-section">
          <div className="fb-section-label">{t("practice.gapsTitle", { n: gaps.length })}</div>
          {gaps.map((g, i) => {
            const added = Boolean(savedMap[i]);
            return (
              <div key={i} className="fb-gap-card">
                <div className="fb-gap-head">
                  <span className="fb-gap-num">{i + 1}</span>
                  <button
                    className={"fb-gap-add" + (added ? " added" : "")}
                    onClick={() => toggleGap(g, i)}
                    title={added ? t("practice.removeTitle") : t("practice.addTitle")}
                  >
                    {added
                      ? <><Icon name="check" size={14} />&nbsp;{t("practice.inReview")}</>
                      : <><Icon name="plus" size={14} />&nbsp;{t("practice.addToReview")}</>}
                  </button>
                </div>
                <div className="fb-gap-table">
                  <div className="fb-gap-line is-said">
                    <span className="fb-gap-tag">{t("practice.gapYouSaid")}</span>
                    <span className="fb-gap-said">{g.original}</span>
                  </div>
                  <div className="fb-gap-line is-fix">
                    <span className="fb-gap-tag">{t("practice.gapSayThis")}</span>
                    <span className="fb-gap-fix">{g.better}</span>
                    <SpeakBtns text={g.better} practiceId={session?._id} />
                  </div>
                  {g.why && (
                    <div className="fb-gap-line">
                      <span className="fb-gap-tag">{t("practice.gapWhy")}</span>
                      <span className="fb-gap-whytext">{g.why}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {gaps.length === 0 && (
        <div className="fb-empty-feedback">
          {result.nativeVersion
            ? t("practice.noGaps")
            : t("practice.noUsableFeedback")}
        </div>
      )}

      {autoSaved > 0 && (
        <p className="fb-autosaved">{t("practice.autoSaved", { n: autoSaved })}</p>
      )}

      <div className="fb-chat">
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
      </div>

      <FeedbackBar
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
      />

      {/* 重说不封顶：重试按钮常驻，带上即将开始的第 N 次尝试；不想再说就点下一个 */}
      <div className="actions-row" style={{ marginTop: 8 }}>
        <button className="su-btn su-btn-primary" onClick={retrySame} disabled={actionsDisabled} style={{ flex: 2, height: 48 }}>
          <Icon name="refresh" size={16} />&nbsp;{t("practice.sayItAgain", { n: (round ?? 1) + 1 })}
        </button>
        <button className="su-btn su-btn-secondary" onClick={() => startNewRound(session?.scenarioId)} disabled={actionsDisabled} style={{ flex: 1, height: 48 }}>
          {t(passed ? "practice.nextScenario" : "practice.next")}&nbsp;<Icon name="next" size={16} />
        </button>
      </div>
    </div>
  );
}
