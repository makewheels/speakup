import { useState } from "react";
import { api } from "../api/client.js";
import { useT } from "../i18n/useI18n.js";
import FeedbackImagePicker from "../components/FeedbackImagePicker.jsx";

// 与后端 routes/feedbacks.py GENERAL_TAGS 对应
const GENERAL_TAGS = ["product", "scenario", "asr", "bug", "other"];

export default function FeedbackPage() {
  const t = useT();
  const [tags, setTags] = useState([]);
  const [comment, setComment] = useState("");
  const [status, setStatus] = useState("idle"); // idle | submitted | error
  const [busy, setBusy] = useState(false);
  const [images, setImages] = useState([]);

  const toggleTag = (key) =>
    setTags((ts) => (ts.includes(key) ? ts.filter((x) => x !== key) : [...ts, key]));

  const submit = async () => {
    setBusy(true);
    try {
      await api.submitFeedback({
        type: "general",
        tags,
        comment: comment.trim(),
      }, images);
      setStatus("submitted");
    } catch {
      setStatus("error");
    } finally {
      setBusy(false);
    }
  };

  if (status === "submitted") {
    return (
      <div className="feedback-page">
        <div className="fb-done-card">{t("feedback.submitted")}</div>
      </div>
    );
  }

  return (
    <div className="feedback-page">
      <h1 className="page-title">{t("feedback.title")}</h1>
      <p className="feedback-intro">{t("feedback.generalIntro")}</p>

      <div className="feedback-tags">
        {GENERAL_TAGS.map((key) => (
          <button
            key={key}
            className={"fb-tag" + (tags.includes(key) ? " active" : "")}
            onClick={() => toggleTag(key)}
          >
            {t(`feedback.tagGeneral.${key}`)}
          </button>
        ))}
      </div>

      <textarea
        className="feedback-textarea"
        rows={5}
        value={comment}
        placeholder={t("feedback.commentPhGeneral")}
        onChange={(e) => setComment(e.target.value)}
      />

      <FeedbackImagePicker disabled={busy} files={images} onChange={setImages} />

      {status === "error" && <p className="fb-bar-err">{t("feedback.failed")}</p>}

      <button
        className="su-btn su-btn-primary"
        onClick={submit}
        disabled={busy || (!tags.length && !comment.trim() && !images.length)}
      >
        {t("feedback.submitGeneral")}
      </button>
    </div>
  );
}
