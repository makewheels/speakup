import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client.js";
import Icon from "../Icon.jsx";
import SpeakBtn from "../SpeakBtn.jsx";

function SegmentPlayButton({ attemptIndex, issueIndex, practiceId, shareToken, t }) {
  const audioRef = useRef(null);
  const clipUrlRef = useRef("");
  const [state, setState] = useState("idle");

  useEffect(() => () => {
    if (clipUrlRef.current) URL.revokeObjectURL(clipUrlRef.current);
  }, []);

  if ((!practiceId && !shareToken) || attemptIndex == null) return null;
  const play = async () => {
    if (state === "loading") return;
    const audio = audioRef.current;
    if (!audio) return;
    if (state === "playing") {
      audio.pause();
      audio.currentTime = 0;
      setState("idle");
      return;
    }
    try {
      setState("loading");
      if (!clipUrlRef.current) {
        const blob = shareToken
          ? await api.getSharedPronunciationClip(shareToken, attemptIndex, issueIndex)
          : await api.getPronunciationClip(practiceId, attemptIndex, issueIndex);
        clipUrlRef.current = URL.createObjectURL(blob);
        audio.src = clipUrlRef.current;
      }
      audio.currentTime = 0;
      await audio.play();
      setState("playing");
    } catch {
      setState("idle");
    }
  };
  return (
    <>
      <audio
        ref={audioRef}
        preload="none"
        onEnded={() => setState("idle")}
        onPause={() => { if (state === "playing") setState("idle"); }}
      />
      <button
        className={`pron-listen-btn${state === "playing" ? " playing" : ""}`}
        type="button"
        onClick={play}
        title={t("practice.playMyPronunciation")}
        disabled={state === "loading"}
      >
        <Icon name={state === "playing" ? "stop" : "volume"} size={15} />
        <span>{state === "loading" ? t("player.synthesizing") : t("practice.listenMine")}</span>
      </button>
    </>
  );
}

function IpaComparison({ detected, reference, t }) {
  if (!detected && !reference) return null;
  return (
    <div className="pron-ipa" aria-label={t("practice.soundComparison")}>
      <div>
        <span className="pron-ipa-label">{t("practice.yourSound")}</span>
        <strong>/{detected || "–"}/</strong>
      </div>
      <span className="pron-ipa-arrow" aria-hidden="true">→</span>
      <div>
        <span className="pron-ipa-label">{t("practice.targetSound")}</span>
        <strong>/{reference || "–"}/</strong>
      </div>
    </div>
  );
}

function PronunciationTip({ issue, t }) {
  const phones = issue.phones ?? [];
  const differences = phones.filter(
    (phone) => phone.detected && phone.reference && phone.detected !== phone.reference,
  );
  const stressNeedsWork = phones.some(
    (phone) => phone.stressExpected !== phone.stressDetected,
  );
  if (differences.length > 0) {
    const actual = differences.slice(0, 2).map((phone) => `/${phone.detected}/`).join(", ");
    const target = differences.slice(0, 2).map((phone) => `/${phone.reference}/`).join(", ");
    return (
      <p>{t(stressNeedsWork ? "practice.pronunciationSoundStressTip" : "practice.pronunciationSoundTip", {
        actual, target,
      })}</p>
    );
  }
  if (stressNeedsWork) return <p>{t("practice.pronunciationStressTip")}</p>;
  return <p>{t("practice.pronunciationClarityTip")}</p>;
}

export default function PronunciationFeedback({
  attemptIndex, canSpeak = true, loading, pronunciation, practiceId, shareToken = "", t,
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
                <span className="pron-score">{Math.round(issue.score ?? 0)} / 100</span>
              </div>
              <IpaComparison detected={issue.detectedIpa} reference={issue.referenceIpa} t={t} />
              <PronunciationTip issue={issue} t={t} />
              <div className="pron-audio-actions">
                <SegmentPlayButton
                  attemptIndex={attemptIndex}
                  issueIndex={index}
                  key={`${practiceId}-${shareToken}-${attemptIndex}-${index}`}
                  practiceId={practiceId}
                  shareToken={shareToken}
                  t={t}
                />
                {canSpeak && (
                  <SpeakBtn
                    attemptIndex={attemptIndex}
                    className="pron-listen-btn"
                    label={t("practice.listenTarget")}
                    practiceId={practiceId}
                    purpose="pronunciation-target"
                    size={15}
                    text={issue.word}
                  />
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
