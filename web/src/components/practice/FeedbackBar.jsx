import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { useT } from "../../i18n/useI18n.js";
import { useUser } from "../../context/useUser.js";

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
  const { user } = useUser();
  // status: loading | thumbs | expanded_bad | submitted | error
  const [status, setStatus] = useState("loading");
  const [tags, setTags] = useState([]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [existing, setExisting] = useState(null);

  // 挂载时取这一轮已存的反馈：有则进"已反馈"态（可修改），无则进 thumbs
  useEffect(() => {
    if (!practiceId || !user?.userId) return;
    let cancelled = false;
    (async () => {
      try {
        const list = await api.listMyFeedbacks(user.userId, { practiceId, attemptIndex });
        if (cancelled) return;
        if (list.length > 0) {
          const f = list[0];
          setExisting(f);
          setTags(f.tags || []);
          setComment(f.comment || "");
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

  if (!practiceId || status === "loading") return null;

  const toggleTag = (key) =>
    setTags((ts) => (ts.includes(key) ? ts.filter((x) => x !== key) : [...ts, key]));

  const submit = async (rating) => {
    setBusy(true);
    // good 反馈不带原因标签和评论
    const submitTags = rating === "bad" ? tags : [];
    const submitComment = rating === "bad" ? comment : "";
    try {
      const res = await api.submitFeedback({
        type: "practice",
        rating,
        tags: submitTags,
        comment: submitComment,
        practiceId,
        attemptIndex,
        snapshot,
      });
      setExisting(res);
      setTags(res.tags || []);
      setComment(res.comment || "");
      setStatus("submitted");
    } catch {
      setStatus("error");
    } finally {
      setBusy(false);
    }
  };

  // 已反馈态：显示上次的选择 + 修改入口
  if (status === "submitted" && existing) {
    return (
      <div className="fb-bar">
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
      </div>
    );
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
