import Icon from "../Icon.jsx";
import SpeakBtn from "../SpeakBtn.jsx";
import PracticeMedia from "./PracticeMedia.jsx";
import PracticeScenarioCard from "./PracticeScenarioCard.jsx";
import PracticeFreeCard from "./PracticeFreeCard.jsx";

function preferenceNoticeKey(match) {
  if (match === "relaxedDifficulty") return "practicePrefs.matchRelaxedDifficulty";
  if (match === "relaxedPurpose") return "practicePrefs.matchRelaxedPurpose";
  if (match === "fallback") return "practicePrefs.matchFallback";
  return "";
}

function SpeakBtns({ text, practiceId }) {
  return <SpeakBtn text={text} practiceId={practiceId} />;
}

// 阶段提示文案 —— 跟随语言切换，所以在组件内构造
function buildPrompts(mode, t) {
  return {
    loading:      mode === "free" ? t("practice.freeLoading") : t("practice.loading"),
    ready:        "",
    recording:    t("practice.listening"),
    transcribing: t("practice.transcribing"),
    review:       t("practice.review"),
    evaluating:   t("practice.evaluating"),
    feedback:     "",
  };
}

export default function PracticeActiveView({
  discardRecording,
  elapsed,
  evalAnchorRef,
  evalElapsed,
  evaluate,
  freeTopic,
  handleRecordClick,
  handleRecordPressEnd,
  handleRecordPressStart,
  hintGaps,
  mode,
  modeSwitch,
  onChangeTopic,
  onNoTopic,
  paused,
  pauseResumeRecording,
  pauseSupported,
  phase,
  round,
  scenario,
  session,
  startNewRound,
  startRecording,
  stopRecording,
  streamingLen,
  t,
  transcriptionError,
  transcript,
  setTranscript,
}) {
  const isFree = mode === "free";
  const prompts = buildPrompts(mode, t);
  // 话题展示：优先当前抽到的话题；刷新后从会话快照还原（zh 不在快照里，可空）
  const freeInfo = freeTopic
    || (isFree && session?.freeTopic
      ? { _id: session.freeTopicId || "", text: session.freeTopic, zh: "" }
      : null);
  return (
    <div className="practice-page">
      {modeSwitch}
      {phase !== "loading" && (
        <div className="attempt-badge-row">
          <span className="attempt-badge">{t("practice.attemptBadge", { n: round ?? 1 })}</span>
        </div>
      )}
      <PracticeMedia
        className={"su-img" + (phase === "loading" ? " loading" : "")}
        imageUrl={phase !== "loading" && !isFree ? session?.imageUrl : ""}
        videoUrl={phase !== "loading" && !isFree ? session?.videoUrl : ""}
      />

      {phase !== "loading" && (isFree
        ? <PracticeFreeCard freeTopic={freeInfo?.text || ""} zh={freeInfo?.zh || ""} t={t} />
        : <PracticeScenarioCard scenario={scenario} topic={session?.topic} t={t} />)}

      {phase !== "loading" && preferenceNoticeKey(session?.preferenceMatch) && (
        <div className="pref-match-note">
          {t(preferenceNoticeKey(session.preferenceMatch))}
        </div>
      )}

      {hintGaps.length > 0 && phase !== "loading" && (
        <div className="sc-hintbar">
          💡 {t("practice.tryToUse")}
          {hintGaps.map((g, i) => (
            <span key={i} className="sc-hint-item">
              <b>{g.better}</b>
              <SpeakBtns text={g.better} practiceId={session?._id} />
            </span>
          ))}
        </div>
      )}

      <p className="su-prompt">{prompts[phase]}</p>

      {(phase === "recording" || phase === "transcribing" || phase === "evaluating") && (
        <div className={"su-transcript" + (!transcript ? " empty" : "")}>
          {transcript ||
            (phase === "recording"
              ? t("practice.willTranscribe")
              : phase === "transcribing"
              ? t("practice.transcribingDots")
              : t("practice.yourWordsHere"))}
          {phase === "recording" && <span className="live-dot" />}
        </div>
      )}

      {phase === "review" && (
        <>
          <textarea
            aria-label={t("practice.transcriptInputLabel")}
            className="su-transcript su-transcript-input"
            onChange={(event) => setTranscript(event.target.value)}
            placeholder={t("practice.transcriptPlaceholder")}
            rows={4}
            value={transcript}
          />
          {transcriptionError && (
            <p className="su-transcript-fallback" role="status">
              {t("practice.manualTranscriptHint")}
            </p>
          )}
        </>
      )}

      {phase === "recording" && (
        <div className="su-rec-meta">
          <span className={"rec-dot" + (paused ? " paused" : "")}>{paused ? t("practice.paused") : t("practice.rec")}</span>
          <span className="elapsed">{elapsed}</span>
        </div>
      )}

      <div style={{ height: phase === "review" || phase === "evaluating" ? 18 : 30 }} />

      {(phase === "loading" || phase === "ready") && (
        <div className="su-rec-wrap">
          <button
            className="su-rec"
            onPointerDown={() => handleRecordPressStart(startRecording)}
            onPointerUp={handleRecordPressEnd}
            onPointerLeave={handleRecordPressEnd}
            onContextMenu={(e) => e.preventDefault()}
            onClick={() => handleRecordClick(startRecording)}
            disabled={phase === "loading"}
          >
            <Icon name="mic" size={32} color="#fff" />
          </button>
          <div className="su-rec-label">{t("practice.tapToStart")}</div>
          {phase === "ready" && !isFree && session?.scenarioId && (
            <button
              className="su-skip"
              title={t("practice.tryAnother")}
              onClick={() => startNewRound(session.scenarioId)}
            >
              <Icon name="refresh" size={16} />
              <span>{t("practice.tryAnother")}</span>
            </button>
          )}
          {phase === "ready" && isFree && (
            <div className="free-actions">
              {freeInfo && (
                <button className="su-skip" title={t("practice.freeChangeTopic")} onClick={onChangeTopic}>
                  <Icon name="refresh" size={16} />
                  <span>{t("practice.freeChangeTopic")}</span>
                </button>
              )}
              <button className="su-btn su-btn-secondary free-no-topic" onClick={onNoTopic}>
                {t("practice.freeNoTopic")}
              </button>
            </div>
          )}
        </div>
      )}

      {phase === "recording" && (
        <div className="su-rec-wrap">
          <div className="su-rec-row">
            {pauseSupported && (
              <button
                className="su-rec-side"
                title={paused ? t("practice.resume") : t("practice.pause")}
                onClick={pauseResumeRecording}
              >
                <Icon name={paused ? "play" : "pause"} size={20} />
              </button>
            )}
            <button
              className={"su-rec recording" + (paused ? " paused" : "")}
              onPointerDown={() => handleRecordPressStart(stopRecording)}
              onPointerUp={handleRecordPressEnd}
              onPointerLeave={handleRecordPressEnd}
              onContextMenu={(e) => e.preventDefault()}
              onClick={() => handleRecordClick(stopRecording)}
            >
              <Icon name="stop" size={28} color="#fff" />
            </button>
            <button
              className="su-rec-side"
              title={t("practice.discard")}
              onClick={discardRecording}
            >
              <Icon name="trash" size={20} />
            </button>
          </div>
          <div className="su-rec-label">{paused ? t("practice.tapToResume") : t("practice.tapToStop")}</div>
          <div className="su-rec-hint">{t("practice.stopHint")}</div>
        </div>
      )}

      {phase === "transcribing" && (
        <div className="su-rec-wrap">
          <button className="su-rec recording" disabled style={{ opacity: 0.6 }}>
            <span className="spin" />
          </button>
          <div className="su-rec-label">{t("practice.transcribingShort")}</div>
        </div>
      )}

      {phase === "review" && (
        <div className="actions-row">
          <button className="su-btn su-btn-secondary" style={{ flex: 1 }} onClick={startRecording}>
            <Icon name="refresh" size={16} />&nbsp;{t("practice.redo")}
          </button>
          <button className="su-btn su-btn-primary" style={{ flex: 2 }} onClick={() => evaluate()} disabled={!transcript.trim()}>
            {t("practice.getFeedback")}
          </button>
        </div>
      )}

      {phase === "evaluating" && (
        <>
          <div className="actions-row">
            <button className="su-btn su-btn-secondary" disabled style={{ flex: 1, opacity: 0.5 }}>
              <Icon name="refresh" size={16} />&nbsp;{t("practice.redo")}
            </button>
            <button className="su-btn su-btn-primary disabled" style={{ flex: 2 }}>
              <span className="spin" />&nbsp;{t("practice.aiReviewing")} {evalElapsed > 0 && <span style={{ marginLeft: 4, opacity: 0.8 }}>({evalElapsed}s)</span>}
            </button>
          </div>
          <p ref={evalAnchorRef} style={{
            fontFamily: "var(--ff-cn)", fontSize: 12, color: "var(--ink-3)",
            textAlign: "center", marginTop: 14, lineHeight: 1.6,
          }}>
            {streamingLen > 0
              ? t("practice.writingChars", { n: streamingLen })
              : evalElapsed < 15
              ? t("practice.checkingTask")
              : evalElapsed < 40
              ? t("practice.comparingNative")
              : t("practice.takingLonger")}
          </p>
        </>
      )}
    </div>
  );
}
