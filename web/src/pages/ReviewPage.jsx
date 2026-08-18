import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/useUser.js";
import { useT } from "../i18n/useI18n.js";
import { api } from "../api/client.js";
import Icon from "../components/Icon.jsx";
import SpeakBtn from "../components/SpeakBtn.jsx";

const kindOf = (w) => (w.kind === "note" ? "note" : "mistake"); // 历史数据无 kind 按错题

export default function ReviewPage() {
  const { user } = useUser();
  const navigate = useNavigate();
  const t = useT();
  const [items, setItems] = useState([]);      // active 复习项
  const [retired, setRetired] = useState([]);  // 已收纳（会说即移除，可查看/恢复）
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState("cards");     // cards 逐词复习（默认首屏）| list 全部列表
  const [kindFilter, setKindFilter] = useState("all"); // all | mistake | note（错题本拆分两类）
  const [idx, setIdx] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [quiz, setQuiz] = useState(null);        // 词卡出题 {options, picked, correct}；null=直接看答案（选项池不足时兜底）
  const [genWord, setGenWord] = useState(null);  // 正在「练这个词」出题的 item id
  const [pendingDeleteId, setPendingDeleteId] = useState(null);
  const [retiredOpen, setRetiredOpen] = useState(false);
  const [retiredNow, setRetiredNow] = useState(0);   // 本轮收纳条数
  const [translateFailed, setTranslateFailed] = useState({});
  const deleteTimerRef = useRef(null);
  const translatingIds = useRef(new Set());

  const fetchItems = useCallback(() => {
    api.listReviewItems(user.userId, false, true)
      .then((all) => {
        setItems(all.filter((w) => w.status !== "retired"));
        setRetired(all.filter((w) => w.status === "retired"));
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [user.userId]);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  const isMastered = (w) => (w.reviewCount || 0) >= 3 && (w.interval || 0) >= 7;
  const isDue = (w) => new Date(w.nextReviewAt) <= new Date() && !isMastered(w);

  // 卡片队列：按 kind 过滤后，待复习优先 → 复习中 → 已掌握（历史数据兼容）
  const rank = (w) => (isDue(w) ? 0 : isMastered(w) ? 2 : 1);
  const queue = [...items]
    .filter((w) => kindFilter === "all" || kindOf(w) === kindFilter)
    .sort((a, b) => rank(a) - rank(b) || new Date(a.nextReviewAt) - new Date(b.nextReviewAt));
  const current = queue[idx];

  // 历史数据可能缺 chinese（中文提示词）：首次出现时惰性翻译补齐
  useEffect(() => {
    if (!current || current.chinese || translatingIds.current.has(current._id)) return;
    translatingIds.current.add(current._id);
    api.translateReviewItem(current._id, user.userId)
      .then(({ chinese }) => {
        if (!chinese) {
          setTranslateFailed((m) => ({ ...m, [current._id]: true }));
          return;
        }
        setItems((prev) => prev.map((w) => (w._id === current._id ? { ...w, chinese } : w)));
      })
      .catch(() => setTranslateFailed((m) => ({ ...m, [current._id]: true })));
  }, [current, user.userId]);

  const resetCardState = () => {
    setIdx(0);
    setShowAnswer(false);
    setQuiz(null);
  };

  // 温故而知新：点开卡片先出四选一词卡（干扰项取自用户自己的其它复习项，含已收纳）
  const buildQuiz = (w) => {
    const pool = [...new Set(
      [...items, ...retired]
        .filter((x) => x._id !== w._id && x.expression)
        .map((x) => x.expression.trim()),
    )];
    const distractors = [...pool].sort(() => Math.random() - 0.5).slice(0, 3);
    if (distractors.length < 3) return null; // 选项池不足 → 兜底直接看答案自查
    const options = [...distractors, w.expression].sort(() => Math.random() - 0.5);
    return { options, picked: null, correct: w.expression };
  };

  const revealCard = () => {
    if (showAnswer) return;
    const w = queue[idx];
    if (w) setQuiz(buildQuiz(w));
    setShowAnswer(true);
  };

  const pickOption = async (opt) => {
    const w = queue[idx];
    if (!quiz || quiz.picked || !w) return;
    setQuiz({ ...quiz, picked: opt });
    await api.reviewItem(w._id, user.userId, opt === quiz.correct).catch(console.error);
  };

  // 答对收纳 / 答错留本，都在点「下一题」时落状态，保证答题结果先稳定展示
  const closeQuiz = () => {
    const w = queue[idx];
    const correct = quiz && quiz.picked === quiz.correct;
    setQuiz(null);
    setShowAnswer(false);
    if (!w) return;
    if (correct) {
      setItems((prev) => prev.filter((x) => x._id !== w._id));
      setRetired((prev) => [{ ...w, status: "retired" }, ...prev]);
      setRetiredNow((n) => n + 1);
    } else {
      setIdx((i) => i + 1);
    }
  };

  const handleReview = async (remembered) => {
    const w = queue[idx];
    if (!w) return;
    const updated = await api.reviewItem(w._id, user.userId, remembered).catch(console.error);
    setShowAnswer(false);
    if (remembered) {
      // 会说即收纳：移出复习队列，进已收纳区
      setItems((prev) => prev.filter((x) => x._id !== w._id));
      setRetired((prev) => [{ ...w, ...(updated || { status: "retired" }) }, ...prev]);
      setRetiredNow((n) => n + 1);
    } else {
      setIdx((i) => i + 1);
    }
  };

  // 针对这个词即时出一道场景题去练（用上新学的表达，含出图，稍慢）
  const practiceThisWord = async (w) => {
    if (genWord) return;
    setGenWord(w._id);
    try {
      const { scenarioId } = await api.practiceWord(user.userId, w.expression, w.original || "");
      const sess = await api.createPractice({ userId: user.userId, scenarioId });
      navigate(`/practice/${sess._id}`);
    } catch (e) {
      alert(t("review.createScenarioFailed", { msg: e.message }));
      setGenWord(null);
    }
  };

  const deleteItem = async (id) => {
    await api.deleteReviewItem(id, user.userId);
    setItems((prev) => prev.filter((w) => w._id !== id));
    setPendingDeleteId(null);
  };

  const requestDelete = (e, id) => {
    e.stopPropagation();
    if (pendingDeleteId === id) {
      clearTimeout(deleteTimerRef.current);
      deleteItem(id);
    } else {
      clearTimeout(deleteTimerRef.current);
      setPendingDeleteId(id);
      deleteTimerRef.current = setTimeout(() => setPendingDeleteId(null), 3000);
    }
  };

  const restoreItem = async (id) => {
    const w = retired.find((x) => x._id === id);
    await api.restoreReviewItem(id, user.userId).catch(console.error);
    setRetired((prev) => prev.filter((x) => x._id !== id));
    if (w) setItems((prev) => [...prev, { ...w, status: "active" }]);
  };

  if (loading) return <div className="page-msg">{t("common.loading")}</div>;

  if (items.length === 0 && retired.length === 0) {
    return (
      <div className="empty-state">
        <div className="icon-box">
          <Icon name="book" size={28} color="var(--ink-3)" stroke={1.4} />
        </div>
        <p className="title">{t("review.emptyTitle")}</p>
        <p className="sub">{t("review.emptySub")}</p>
      </div>
    );
  }

  const dueCount = items.filter(isDue).length;
  const kindCounts = {
    all: items.length,
    mistake: items.filter((w) => kindOf(w) === "mistake").length,
    note: items.filter((w) => kindOf(w) === "note").length,
  };

  // ── 默认首屏：逐词卡片复习 ──────────────────────────────
  if (view === "cards") {
    const done = idx >= queue.length;
    const w = queue[idx];
    const quizPickedCorrect = quiz && quiz.picked === quiz.correct;
    return (
      <div className="review-cards-page fade-in">
        <div className="rv-head">
          <h2>{t("review.title")}</h2>
          <button className="rv-list-toggle" onClick={() => setView("list")}>
            {t("review.allCount", { n: items.length })} <Icon name="next" size={14} />
          </button>
        </div>

        <div className="rv-kind-filter">
          {[["all", t("review.kindAll")], ["mistake", t("review.kindMistake")], ["note", t("review.kindNote")]].map(([k, label]) => (
            <button
              key={k}
              className={`rv-kind-chip${kindFilter === k ? " active" : ""}`}
              onClick={() => { setKindFilter(k); resetCardState(); }}
            >
              {label} {kindCounts[k]}
            </button>
          ))}
        </div>

        {done ? (
          queue.length === 0 && items.length > 0 ? (
            <div className="rv-done">
              <p className="rv-done-title">{t("review.emptyKind")}</p>
            </div>
          ) : (
            <div className="rv-done">
              <div className="rv-done-check"><Icon name="check" size={30} color="var(--ok)" /></div>
              <p className="rv-done-title">{t("review.doneTitle")}</p>
              <p className="rv-done-sub">{t("review.doneSub", { n: dueCount })}</p>
              {retiredNow > 0 && (
                <p className="rv-done-sub rv-done-retired">{t("review.doneRetired", { n: retiredNow })}</p>
              )}
              <button
                className="su-btn su-btn-secondary"
                style={{ maxWidth: 220 }}
                onClick={() => { resetCardState(); setRetiredNow(0); fetchItems(); }}
              >
                <Icon name="refresh" size={15} />&nbsp;{t("review.goAgain")}
              </button>
            </div>
          )
        ) : (
          <>
            <div className="rv-progress">{t("review.progress", { cur: idx + 1, total: queue.length })}</div>
            <div className="rv-card" onClick={revealCard}>
              {!showAnswer ? (
                <>
                  <div className="rv-card-label">
                    <span className={`rv-kind-tag ${kindOf(w)}`}>
                      {kindOf(w) === "note" ? t("review.kindNote") : t("review.kindMistake")}
                    </span>
                    {t("review.chinesePrompt")}
                  </div>
                  {w.chinese ? (
                    <p className="rv-card-q rv-card-zh">{w.chinese}</p>
                  ) : translateFailed[w._id] ? (
                    <p className="rv-card-q rv-card-fallback">{t("review.translateFailed")}</p>
                  ) : (
                    <p className="rv-card-q rv-card-loading"><span className="spin" />&nbsp;{t("review.translating")}</p>
                  )}
                  <span className="rv-tap-hint">{t("review.tapToReveal")}</span>
                </>
              ) : quiz ? (
                <>
                  <div className="rv-card-label answer">{t("review.quizTitle")}</div>
                  <div className="rv-quiz-options">
                    {quiz.options.map((opt) => {
                      const state = !quiz.picked ? "" : opt === quiz.correct ? " correct" : opt === quiz.picked ? " wrong" : " dim";
                      return (
                        <button
                          key={opt}
                          className={`rv-quiz-opt${state}`}
                          disabled={!!quiz.picked}
                          onClick={(e) => { e.stopPropagation(); pickOption(opt); }}
                        >
                          {opt}
                        </button>
                      );
                    })}
                  </div>
                  {quiz.picked && (
                    <>
                      <p className={`rv-quiz-verdict${quizPickedCorrect ? " ok" : ""}`}>
                        {quizPickedCorrect ? t("review.quizCorrect") : t("review.quizWrong")}
                      </p>
                      <p className="rv-card-a">{w.expression}<SpeakBtn text={w.expression} practiceId={w.practiceId} /></p>
                      {w.note && <p className="rv-card-note">{w.note}</p>}
                      {w.contextSentence && (
                        <p className="rv-card-ctx">{w.contextSentence}<SpeakBtn text={w.contextSentence} practiceId={w.practiceId} /></p>
                      )}
                      <button
                        className="su-btn su-btn-primary rv-practice-btn"
                        onClick={(e) => { e.stopPropagation(); practiceThisWord(w); }}
                        disabled={!!genWord}
                      >
                        {genWord === w._id
                          ? <><span className="spin" />&nbsp;{t("review.creating")}</>
                          : <><Icon name="spark" size={15} />&nbsp;{t("review.practiceThisWord")}</>}
                      </button>
                      <button
                        className="su-btn su-btn-secondary rv-next-btn"
                        onClick={(e) => { e.stopPropagation(); closeQuiz(); }}
                      >
                        {t("review.nextCard")}&nbsp;<Icon name="next" size={15} />
                      </button>
                    </>
                  )}
                </>
              ) : (
                <>
                  <div className="rv-card-label answer">{t("review.nativeVersion")}</div>
                  <p className="rv-card-a">{w.expression}<SpeakBtn text={w.expression} practiceId={w.practiceId} /></p>
                  {w.note && <p className="rv-card-note">{w.note}</p>}
                  {w.contextSentence && (
                    <p className="rv-card-ctx">{w.contextSentence}<SpeakBtn text={w.contextSentence} practiceId={w.practiceId} /></p>
                  )}
                  <button
                    className="su-btn su-btn-primary rv-practice-btn"
                    onClick={(e) => { e.stopPropagation(); practiceThisWord(w); }}
                    disabled={!!genWord}
                  >
                    {genWord === w._id
                      ? <><span className="spin" />&nbsp;{t("review.creating")}</>
                      : <><Icon name="spark" size={15} />&nbsp;{t("review.practiceThisWord")}</>}
                  </button>
                  <div className="rv-verdict-row">
                    <button
                      className="su-btn su-btn-secondary"
                      style={{ flex: 1, height: 46 }}
                      onClick={(e) => { e.stopPropagation(); handleReview(false); }}
                    >
                      {t("review.forgot")}
                    </button>
                    <button
                      className="su-btn su-btn-primary"
                      style={{ flex: 1, height: 46 }}
                      onClick={(e) => { e.stopPropagation(); handleReview(true); }}
                    >
                      {t("review.gotIt")}
                    </button>
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </div>
    );
  }

  // ── 全部列表（次要视图，错题 / 笔记分组）─────────────────
  const renderRow = (w) => {
    const mastered = isMastered(w);
    const due = isDue(w);
    const confirmingDelete = pendingDeleteId === w._id;
    return (
      <div key={w._id} className="review-card">
        <div className="review-card-body">
          {w.chinese && <div className="review-zh">{w.chinese}</div>}
          <div className="review-better">
            {w.expression}<SpeakBtn text={w.expression} practiceId={w.practiceId} />
          </div>
          {w.note && <div className="review-why">{w.note}</div>}
          <div className="review-foot">
            <button className="review-cta-btn" onClick={() => practiceThisWord(w)} disabled={!!genWord}>
              {genWord === w._id
                ? <><span className="spin" />&nbsp;{t("review.creating")}</>
                : <><Icon name="spark" size={12} /> {t("review.practiceThis")}</>}
            </button>
            <span className={`review-status${due ? " due" : mastered ? " mastered" : ""}`}>
              {mastered ? t("review.mastered") : due ? t("review.due") : t("review.learning")}
            </span>
          </div>
        </div>
        <button
          className={`review-del${confirmingDelete ? " confirming" : ""}`}
          onClick={(e) => requestDelete(e, w._id)}
          aria-label={t("common.delete")}
        >
          {confirmingDelete ? t("common.confirm") : <Icon name="trash" size={15} />}
        </button>
      </div>
    );
  };

  const mistakeRows = queue.filter((w) => kindOf(w) === "mistake");
  const noteRows = queue.filter((w) => kindOf(w) === "note");

  return (
    <div className="review-page">
      <div className="rv-head">
        <h2>{t("review.allItemsTitle")}</h2>
        <button className="rv-list-toggle" onClick={() => setView("cards")}>
          <Icon name="back" size={14} /> {t("review.flashcards")}
        </button>
      </div>
      {mistakeRows.length > 0 && (
        <>
          <div className="rv-list-section-label">{t("review.kindMistake")} · {mistakeRows.length}</div>
          {mistakeRows.map(renderRow)}
        </>
      )}
      {noteRows.length > 0 && (
        <>
          <div className="rv-list-section-label note">{t("review.kindNote")} · {noteRows.length}</div>
          {noteRows.map(renderRow)}
        </>
      )}
      {retired.length > 0 && (
        <div className="rv-retired-section">
          <button className="rv-retired-toggle" onClick={() => setRetiredOpen(!retiredOpen)}>
            {t("review.archivedCount", { n: retired.length })}
            <span className={`rv-retired-arrow${retiredOpen ? " open" : ""}`}>
              <Icon name="next" size={14} />
            </span>
          </button>
          {retiredOpen && retired.map((w) => (
            <div key={w._id} className="review-card rv-retired-card">
              <div className="review-card-body">
                {w.chinese && <div className="review-zh">{w.chinese}</div>}
                <div className="review-better">
                  {w.expression}<SpeakBtn text={w.expression} practiceId={w.practiceId} />
                </div>
                <div className="review-foot">
                  <button className="review-cta-btn" onClick={() => restoreItem(w._id)}>
                    <Icon name="refresh" size={12} /> {t("review.restore")}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="list-end">{t("common.endOfList")}</p>
    </div>
  );
}
