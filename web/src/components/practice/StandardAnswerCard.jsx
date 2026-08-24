import Icon from "../Icon.jsx";
import SpeakBtn from "../SpeakBtn.jsx";

const splitSentences = (text = "") =>
  text.match(/[^.!?]+[.!?]*/g)?.map((sentence) => sentence.trim()).filter(Boolean) ?? [text];

export default function StandardAnswerCard({
  answer,
  attemptId = "",
  attemptIndex = -1,
  canSpeak = true,
  notes = [],
  practiceId,
  t,
}) {
  if (!answer) return null;

  return (
    <section className="result-section result-standard" data-note-context={answer}>
      <h2 className="result-section-title">{t("practice.standardAnswer")}</h2>
      <div className="result-disclosure">
        <details className="result-disclosure-details" open>
          <summary>
            <span>{t("practice.viewStandardAnswer")}</span>
            <Icon name="next" size={15} />
          </summary>
          <div className="result-disclosure-body">
            {splitSentences(answer).map((sentence, index) => (
              <p key={index} className="fb-native-text">{sentence}</p>
            ))}
            {notes.length > 0 && (
              <div className="standard-answer-notes">
                <h3>{t("practice.standardAnswerNotes")}</h3>
                {notes.map((note, index) => (
                  <div key={`${note.expression}-${index}`} className="standard-answer-note" data-note-context={note.expression}>
                    <div>
                      <strong>{note.expression}</strong>
                      {note.chinese && <span>{note.chinese}</span>}
                    </div>
                    {note.explanation && <p>{note.explanation}</p>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </details>
        {canSpeak && (
          <div className="result-disclosure-action">
            <SpeakBtn
              attemptId={attemptId}
              attemptIndex={attemptIndex}
              practiceId={practiceId}
              purpose="standard-answer"
              text={answer}
            />
          </div>
        )}
      </div>
    </section>
  );
}
