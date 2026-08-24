import RecordingPlayBtn from "../RecordingPlayBtn.jsx";
import SpeakBtn from "../SpeakBtn.jsx";

function sentenceCorrectionItems(result, transcript) {
  if ((result?.sentenceCorrections ?? []).length > 0) return result.sentenceCorrections;
  if ((transcript || "").trim() && (result?.nativeVersion || "").trim()) {
    return [{ sourceId: 0, original: transcript.trim(), corrected: result.nativeVersion.trim() }];
  }
  return [];
}

export default function SentenceCorrectionList({
  canSpeak = true, recordingUrl, result, transcript, practiceId, t,
}) {
  const items = sentenceCorrectionItems(result, transcript);
  if (items.length === 0) return null;
  const correctedText = items.map((item) => item.corrected).filter(Boolean).join(" ");

  return (
    <section className="fb-sentence-section">
      <div className="fb-card-label">
        {t("practice.sentenceComparison")}
        <span className="fb-sentence-actions">
          {recordingUrl && <RecordingPlayBtn src={recordingUrl} />}
          {canSpeak && correctedText && <SpeakBtn text={correctedText} practiceId={practiceId} />}
        </span>
      </div>
      <div className="fb-sentence-list">
        {items.map((item, index) => (
          <article className="fb-sentence-pair" key={item.sourceId ?? index}>
            <div className="fb-sentence-row is-original">
              <span>{t("practice.youSaid")}</span>
              <p>{item.original}</p>
            </div>
            <div className="fb-sentence-row is-corrected">
              <span>{t("practice.nativeVersion")}</span>
              <p>{item.corrected}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
