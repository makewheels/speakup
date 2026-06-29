import Icon from "../Icon.jsx";
import SpeakBtn from "../SpeakBtn.jsx";
import PracticeMedia from "./PracticeMedia.jsx";
import PracticeScenarioCard from "./PracticeScenarioCard.jsx";

function preferenceNoticeKey(match) {
  if (match === "relaxedDifficulty") return "practicePrefs.matchRelaxedDifficulty";
  if (match === "relaxedPurpose") return "practicePrefs.matchRelaxedPurpose";
  if (match === "fallback") return "practicePrefs.matchFallback";
  return "";
}

function SpeakBtns({ text, practiceId }) {
  return <SpeakBtn text={text} practiceId={practiceId} />;
}

export default function PracticeActiveView({
  elapsed,
  evalAnchorRef,
  evalElapsed,
  evaluate,
  handleRecordClick,
  handleRecordPressEnd,
  handleRecordPressStart,
  hintGaps,
  phase,
  prompts,
  scenario,
  session,
  startNewRound,
  startRecording,
  stopRecording,
  streamingLen,
  t,
  transcript,
}) {
  return (
    <div className="practice-page">
      <PracticeMedia
        className={"su-img" + (phase === "loading" ? " loading" : "")}
        imageUrl={phase !== "loading" ? session?.imageUrl : ""}
        videoUrl={phase !== "loading" ? session?.videoUrl : ""}
      />

      {phase !== "loading" && <PracticeScenarioCard scenario={scenario} topic={session?.topic} t={t} />}

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

      {(phase === "recording" || phase === "transcribing" || phase === "review" || phase === "evaluating") && (
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

      {phase === "recording" && (
        <div className="su-rec-meta">
          <span className="rec-dot">{t("practice.rec")}</span>
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
          <div className="su-rec-hint">{t("practice.tapHint")}</div>
          {phase === "ready" && session?.scenarioId && (
            <button
              className="su-skip"
              title={t("practice.tryAnother")}
              onClick={() => startNewRound(session.scenarioId)}
            >
              <Icon name="refresh" size={16} />
              <span>{t("practice.tryAnother")}</span>
            </button>
          )}
        </div>
      )}

      {phase === "recording" && (
        <div className="su-rec-wrap">
          <button
            className="su-rec recording"
            onPointerDown={() => handleRecordPressStart(stopRecording)}
            onPointerUp={handleRecordPressEnd}
            onPointerLeave={handleRecordPressEnd}
            onContextMenu={(e) => e.preventDefault()}
            onClick={() => handleRecordClick(stopRecording)}
          >
            <Icon name="stop" size={28} color="#fff" />
          </button>
          <div className="su-rec-label">{t("practice.tapToStop")}</div>
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
