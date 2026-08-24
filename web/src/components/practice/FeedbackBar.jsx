import { useEffect, useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../../api/client.js";
import { useT } from "../../i18n/useI18n.js";
import { useUser } from "../../context/useUser.js";

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
  const { user } = useUser();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("loading");
  const [tags, setTags] = useState([]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [existing, setExisting] = useState(null);

  useEffect(() => {
    if (!practiceId || !user?.userId) return;
    let cancelled = false;
    (async () => {
      try {
        const list = await api.listMyFeedbacks(user.userId, { practiceId, attemptIndex });
        if (cancelled) return;
        if (list.length > 0) {
          const feedback = list[0];
          setExisting(feedback);
          setTags(feedback.tags || []);
          setComment(feedback.comment || "");
          setStatus("submitted");
        } else {
          setStatus("thumbs");
        }
      } catch {
        if (!cancelled) setStatus("thumbs");
      }
    })();
    return () => { cancelled = true; };
  }, [practiceId, attemptIndex, user?.userId]);

  if (!practiceId) return null;

  const toggleTag = (key) =>
    setTags((current) => (
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key]
    ));

  const submit = async (rating) => {
    setBusy(true);
    try {
      const response = await api.submitFeedback({
        type: "practice",
        rating,
        tags: rating === "bad" ? tags : [],
        comment: comment.trim(),
        practiceId,
        attemptIndex,
        snapshot,
      });
      setExisting(response);
      setTags(response.tags || []);
      setComment(response.comment || "");
      setStatus("submitted");
      setOpen(false);
    } catch {
      setStatus("error");
    } finally {
      setBusy(false);
    }
  };

  const triggerLabel = status === "submitted"
    ? t("feedback.reviewPractice")
    : open ? t("feedback.closePractice") : t("feedback.openPractice");

  return (
    <section className="fb-feedback">
      <button
        className="fb-feedback-trigger"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span>{triggerLabel}</span>
        <Icon name="next" size={15} />
      </button>

      {open && (
        <div className="fb-bar">
          {status === "loading" ? (
            <p className="fb-bar-q">{t("common.loadingDots")}</p>
          ) : status === "submitted" && existing ? (
            <>
              <div className="fb-bar-q">{t("feedback.practiceQ")}</div>
              <div className="fb-existing">
                <span className="fb-existing-rating">{existing.rating === "good" ? "👍" : "👎"}</span>
                {existing.tags?.length > 0 && (
                  <div className="fb-existing-tags">
                    {existing.tags.map((key) => (
                      <span key={key} className="fb-tag active">{t(`feedback.tag.${key}`)}</span>
                    ))}
                  </div>
                )}
                {existing.comment && <p className="fb-existing-comment">{existing.comment}</p>}
              </div>
              <button className="fb-edit-btn" onClick={() => setStatus("thumbs")} disabled={busy}>
                {t("feedback.edit")}
              </button>
            </>
          ) : (
            <>
              <div className="fb-bar-q">{t("feedback.practiceQ")}</div>
              <textarea
                className="fb-bar-input"
                rows={2}
                value={comment}
                placeholder={t("feedback.commentPh")}
                onChange={(event) => setComment(event.target.value)}
                disabled={busy}
              />
              <div className="fb-bar-thumbs">
                <button className="fb-thumb" onClick={() => submit("good")} disabled={busy} aria-label={t("feedback.good")}>
                  👍
                </button>
                <button
                  className="fb-thumb"
                  onClick={() => setStatus((value) => (
                    value === "expanded_bad" ? "thumbs" : "expanded_bad"
                  ))}
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
                  <button className="su-btn su-btn-primary" onClick={() => submit("bad")} disabled={busy}>
                    {t("feedback.submit")}
                  </button>
                </div>
              )}
              {status === "error" && <p className="fb-bar-err">{t("feedback.failed")}</p>}
            </>
          )}
        </div>
      )}
    </section>
  );
}
