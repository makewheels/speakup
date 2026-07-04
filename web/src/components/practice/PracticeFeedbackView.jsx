import Icon from "../Icon.jsx";
import RecordingPlayer from "../RecordingPlayer.jsx";
import SpeakBtn from "../SpeakBtn.jsx";
import PracticeMedia from "./PracticeMedia.jsx";
import PracticeScenarioCard from "./PracticeScenarioCard.jsx";
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
  maxRounds,
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
  transcript,
}) {
  const gaps = result.gaps ?? [];
  const progress = result.progress;
  const passed = progress?.verdict === "passed";
  const lastRound = round >= maxRounds;

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

      {recordingUrl && <RecordingPlayer src={recordingUrl} />}

      <ScoreBadge score={result.score} />

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
          <div className="fb-card-label">{t("practice.youSaid")}</div>
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

      <div className="actions-row" style={{ marginTop: 8 }}>
        {passed || lastRound ? (
          <button className="su-btn su-btn-primary" onClick={() => startNewRound(session?.scenarioId)} disabled={actionsDisabled} style={{ flex: 1, height: 48 }}>
            {t("practice.nextScenario")}&nbsp;<Icon name="next" size={16} />
          </button>
        ) : (
          <>
            <button className="su-btn su-btn-primary" onClick={retrySame} disabled={actionsDisabled} style={{ flex: 2, height: 48 }}>
              <Icon name="refresh" size={16} />&nbsp;{t("practice.sayItAgain")}
            </button>
            <button className="su-btn su-btn-secondary" onClick={() => startNewRound(session?.scenarioId)} disabled={actionsDisabled} style={{ flex: 1, height: 48 }}>
              {t("practice.next")}&nbsp;<Icon name="next" size={16} />
            </button>
          </>
        )}
      </div>
      {!passed && lastRound && (
        <p className="fb-rounds-out">{t("practice.roundsOut")}</p>
      )}
    </div>
  );
}
