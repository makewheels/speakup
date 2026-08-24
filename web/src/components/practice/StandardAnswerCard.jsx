import Icon from "../Icon.jsx";
import SpeakBtn from "../SpeakBtn.jsx";

const splitSentences = (text = "") =>
  text.match(/[^.!?]+[.!?]*/g)?.map((sentence) => sentence.trim()).filter(Boolean) ?? [text];

export default function StandardAnswerCard({
  answer,
  canSpeak = true,
  practiceId,
  t,
}) {
  if (!answer) return null;

  return (
    <section className="result-disclosure result-standard" data-note-context={answer}>
      <details className="result-disclosure-details">
        <summary>
          <span className="result-section-title">{t("practice.standardAnswer")}</span>
          <Icon name="next" size={15} />
        </summary>
        <div className="result-disclosure-body">
          {splitSentences(answer).map((sentence, index) => (
            <p key={index} className="fb-native-text">{sentence}</p>
          ))}
        </div>
      </details>
      {canSpeak && (
        <div className="result-disclosure-action">
          <SpeakBtn text={answer} practiceId={practiceId} />
        </div>
      )}
    </section>
  );
}

