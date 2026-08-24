import { useRef } from "react";
import Icon from "../Icon.jsx";
import SpeakBtn from "../SpeakBtn.jsx";

function SegmentPlayButton({ src, startMs = 0, endMs = 0, t }) {
  const audioRef = useRef(null);
  if (!src) return null;
  const play = () => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Math.max(0, startMs / 1000);
    audio.play().catch(() => {});
  };
  const stopAtEnd = () => {
    const audio = audioRef.current;
    if (audio && endMs > startMs && audio.currentTime >= endMs / 1000) audio.pause();
  };
  return (
    <>
      <audio ref={audioRef} src={src} preload="metadata" onTimeUpdate={stopAtEnd} />
      <button className="spk-btn" type="button" onClick={play} title={t("practice.playMyPronunciation")}>
        <Icon name="volume" size={15} />
      </button>
    </>
  );
}

function PhoneComparison({ phones, t }) {
  const differences = (phones ?? []).filter(
    (phone) => phone.detected && phone.reference && phone.detected !== phone.reference,
  );
  if (differences.length === 0) return null;
  return (
    <div className="pron-phone-list" aria-label={t("practice.soundComparison")}>
      {differences.map((phone, index) => (
        <span className="pron-phone" key={`${phone.reference}-${index}`}>
          /{phone.detected}/ <span aria-hidden="true">→</span> /{phone.reference}/
        </span>
      ))}
    </div>
  );
}

export default function PronunciationFeedback({
  canSpeak = true, loading, pronunciation, recordingUrl, practiceId, t,
}) {
  if (!loading && !pronunciation) return null;
  if (loading) {
    return (
      <section className="result-section pron-section is-loading" aria-live="polite">
        <h2 className="result-section-title">{t("practice.pronunciationSuggestions")}</h2>
        <p>{t("practice.pronunciationLoading")}</p>
      </section>
    );
  }
  if (pronunciation.status !== "completed") {
    return (
      <section className="result-section pron-section" role="status">
        <h2 className="result-section-title">{t("practice.pronunciationSuggestions")}</h2>
        <p>{t("practice.pronunciationUnavailable")}</p>
      </section>
    );
  }
  const issues = pronunciation.issues ?? [];
  return (
    <section className="result-section pron-section">
      <div className="pron-heading">
        <h2 className="result-section-title">{t("practice.pronunciationSuggestions")}</h2>
        {pronunciation.overallScore != null && (
          <span className="pron-overall">{Math.round(pronunciation.overallScore)} / 100</span>
        )}
      </div>
      {issues.length === 0 ? (
        <p className="pron-good">{t("practice.pronunciationGood")}</p>
      ) : (
        <div className="pron-issues">
          {issues.map((issue, index) => (
            <article className="pron-issue" key={`${issue.word}-${index}`}>
              <div className="pron-word-row">
                <strong>{issue.word}</strong>
                <span className="pron-score">{Math.round(issue.score ?? 0)}</span>
                <span className="pron-audio-actions">
                  <SegmentPlayButton
                    src={recordingUrl}
                    startMs={issue.startMs}
                    endMs={issue.endMs}
                    t={t}
                  />
                  {canSpeak && <SpeakBtn text={issue.word} practiceId={practiceId} />}
                </span>
              </div>
              {(issue.detectedIpa || issue.referenceIpa) && (
                <div className="pron-ipa">
                  <span>/{issue.detectedIpa || "–"}/</span>
                  <span aria-hidden="true">→</span>
                  <span>/{issue.referenceIpa || "–"}/</span>
                </div>
              )}
              <PhoneComparison phones={issue.phones} t={t} />
              {issue.coaching && <p>{issue.coaching}</p>}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
