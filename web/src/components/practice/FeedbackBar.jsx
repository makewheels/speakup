import { useState } from "react";
import { api } from "../../api/client.js";
import { useT } from "../../i18n/useI18n.js";

// 与后端 routes/feedbacks.py PRACTICE_TAGS 对应
const PRACTICE_TAGS = [
  "score_too_strict",
  "score_too_loose",
  "gap_wrong",
  "native_unnatural",
  "transcript_wrong",
  "summary_bad",
];

export default function FeedbackBar({ practiceId, attemptIndex, snapshot }) {
  const t = useT();
  const [status, setStatus] = useState("thumbs"); // thumbs | expanded_bad | submitted | error
  const [tags, setTags] = useState([]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  if (!practiceId) return null;

  const toggleTag = (key) =>
    setTags((ts) => (ts.includes(key) ? ts.filter((x) => x !== key) : [...ts, key]));

  const submit = async (rating) => {
    setBusy(true);
    try {
      await api.submitFeedback({
        type: "practice",
        rating,
        tags: rating === "bad" ? tags : [],
        comment,
        practiceId,
        attemptIndex,
        snapshot,
      });
      setStatus("submitted");
    } catch {
      setStatus("error");
    } finally {
      setBusy(false);
    }
  };

  if (status === "submitted") {
    return <div className="fb-bar fb-bar-done">{t("feedback.thanks")}</div>;
  }

  return (
    <div className="fb-bar">
      <div className="fb-bar-q">{t("feedback.practiceQ")}</div>
      <div className="fb-bar-thumbs">
        <button className="fb-thumb" onClick={() => submit("good")} disabled={busy} aria-label={t("feedback.good")}>
          👍
        </button>
        <button
          className="fb-thumb"
          onClick={() => setStatus((s) => (s === "expanded_bad" ? "thumbs" : "expanded_bad"))}
          disabled={busy}
          aria-label={t("feedback.bad")}
        >
          👎
        </button>
      </div>
      {status === "expanded_bad" && (
        <div className="fb-bar-expand">
          <div className="fb-bar-tags">
            {PRACTICE_TAGS.map((key) => (
              <button
                key={key}
                className={"fb-tag" + (tags.includes(key) ? " active" : "")}
                onClick={() => toggleTag(key)}
              >
                {t(`feedback.tag.${key}`)}
              </button>
            ))}
          </div>
          <textarea
            className="fb-bar-input"
            rows={2}
            value={comment}
            placeholder={t("feedback.commentPh")}
            onChange={(e) => setComment(e.target.value)}
          />
          <button className="su-btn su-btn-primary" onClick={() => submit("bad")} disabled={busy}>
            {t("feedback.submit")}
          </button>
        </div>
      )}
      {status === "error" && <p className="fb-bar-err">{t("feedback.failed")}</p>}
    </div>
  );
}
