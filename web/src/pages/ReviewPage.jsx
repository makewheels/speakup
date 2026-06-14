import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { api } from "../api/client.js";
import { speak } from "../utils/tts.js";
import Icon from "../components/Icon.jsx";

function SpeakBtn({ text }) {
  if (!text) return null;
  return (
    <button
      className="spk-btn"
      title="朗读"
      aria-label="朗读"
      onClick={(e) => { e.stopPropagation(); speak(text); }}
    >
      <Icon name="volume" size={16} />
    </button>
  );
}

export default function ReviewPage() {
  const { user } = useUser();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState("cards");     // cards 逐词复习（默认首屏）| list 全部列表
  const [idx, setIdx] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [genWord, setGenWord] = useState(null);  // 正在「练这个词」出题的 item id
  const [pendingDeleteId, setPendingDeleteId] = useState(null);
  const deleteTimerRef = useRef(null);

  const fetchItems = () => {
    api.listReviewItems(user.userId)
      .then(setItems)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchItems(); }, [user.userId]);

  const isMastered = (w) => (w.reviewCount || 0) >= 3 && (w.interval || 0) >= 7;
  const isDue = (w) => new Date(w.nextReviewAt) <= new Date() && !isMastered(w);

  // 卡片队列：待复习优先 → 复习中 → 已掌握
  const rank = (w) => (isDue(w) ? 0 : isMastered(w) ? 2 : 1);
  const queue = [...items].sort(
    (a, b) => rank(a) - rank(b) || new Date(a.nextReviewAt) - new Date(b.nextReviewAt)
  );

  const handleReview = async (remembered) => {
    const w = queue[idx];
    if (w) await api.reviewItem(w._id, user.userId, remembered).catch(console.error);
    setShowAnswer(false);
    setIdx((i) => i + 1);
  };

  // 针对这个词即时出一道场景题去练（含出图，稍慢）
  const practiceThisWord = async (w) => {
    if (genWord) return;
    setGenWord(w._id);
    try {
      const { scenarioId } = await api.practiceWord(user.userId, w.expression, w.original || "");
      const sess = await api.createPractice({ userId: user.userId, scenarioId });
      navigate(`/practice/${sess._id}`);
    } catch (e) {
      alert("出题失败：" + e.message);
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

  if (loading) return <div className="page-msg">加载中…</div>;

  if (items.length === 0) {
    return (
      <div className="empty-state">
        <div className="icon-box">
          <Icon name="book" size={28} color="var(--ink-3)" stroke={1.4} />
        </div>
        <p className="title">还没有复习项</p>
        <p className="sub">去练习里说一段试试</p>
      </div>
    );
  }

  const dueCount = items.filter(isDue).length;

  // ── 默认首屏：逐词卡片复习 ──────────────────────────────
  if (view === "cards") {
    const done = idx >= queue.length;
    const w = queue[idx];
    return (
      <div className="review-cards-page fade-in">
        <div className="rv-head">
          <h2>复习</h2>
          <button className="rv-list-toggle" onClick={() => setView("list")}>
            全部 {items.length} 项 <Icon name="next" size={14} />
          </button>
        </div>

        {done ? (
          <div className="rv-done">
            <div className="rv-done-check"><Icon name="check" size={30} color="var(--ok)" /></div>
            <p className="rv-done-title">这轮过完了</p>
            <p className="rv-done-sub">待复习 {dueCount} 项</p>
            <button
              className="su-btn su-btn-secondary"
              style={{ maxWidth: 220 }}
              onClick={() => { setIdx(0); setShowAnswer(false); fetchItems(); }}
            >
              <Icon name="refresh" size={15} />&nbsp;再过一遍
            </button>
          </div>
        ) : (
          <>
            <div className="rv-progress">{idx + 1} / {queue.length}</div>
            <div className="rv-card" onClick={() => setShowAnswer(true)}>
              {!showAnswer ? (
                <>
                  <div className="rv-card-label">我当时说的</div>
                  <p className="rv-card-q">{w.original || w.contextSentence || w.expression}</p>
                  <span className="rv-tap-hint">点这里看地道说法</span>
                </>
              ) : (
                <>
                  <div className="rv-card-label answer">地道说法</div>
                  <p className="rv-card-a">{w.expression}<SpeakBtn text={w.expression} /></p>
                  {w.note && <p className="rv-card-note">{w.note}</p>}
                  {w.contextSentence && (
                    <p className="rv-card-ctx">{w.contextSentence}<SpeakBtn text={w.contextSentence} /></p>
                  )}
                  <button
                    className="su-btn su-btn-primary rv-practice-btn"
                    onClick={(e) => { e.stopPropagation(); practiceThisWord(w); }}
                    disabled={!!genWord}
                  >
                    {genWord === w._id
                      ? <><span className="spin" />&nbsp;正在出题…</>
                      : <><Icon name="spark" size={15} />&nbsp;用这个词练一道题</>}
                  </button>
                  <div className="rv-verdict-row">
                    <button
                      className="su-btn su-btn-secondary"
                      style={{ flex: 1, height: 46 }}
                      onClick={(e) => { e.stopPropagation(); handleReview(false); }}
                    >
                      没想起来
                    </button>
                    <button
                      className="su-btn su-btn-primary"
                      style={{ flex: 1, height: 46 }}
                      onClick={(e) => { e.stopPropagation(); handleReview(true); }}
                    >
                      想起来了
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

  // ── 全部列表（次要视图）─────────────────────────────────
  return (
    <div className="review-page">
      <div className="rv-head">
        <h2>全部复习项</h2>
        <button className="rv-list-toggle" onClick={() => setView("cards")}>
          <Icon name="back" size={14} /> 逐词复习
        </button>
      </div>
      {queue.map((w) => {
        const mastered = isMastered(w);
        const due = isDue(w);
        const confirmingDelete = pendingDeleteId === w._id;
        return (
          <div key={w._id} className="review-card">
            <div className="review-card-body">
              {w.original && <div className="review-said">{w.original}</div>}
              <div className="review-better">
                <span className="arrow">→</span> {w.expression}<SpeakBtn text={w.expression} />
              </div>
              {w.note && <div className="review-why">{w.note}</div>}
              <div className="review-foot">
                <button className="review-cta-btn" onClick={() => practiceThisWord(w)} disabled={!!genWord}>
                  {genWord === w._id
                    ? <><span className="spin" />&nbsp;出题中…</>
                    : <><Icon name="spark" size={12} /> 练这个词</>}
                </button>
                <span className={`review-status${due ? " due" : mastered ? " mastered" : ""}`}>
                  {mastered ? "已掌握" : due ? "待复习" : "复习中"}
                </span>
              </div>
            </div>
            <button
              className={`review-del${confirmingDelete ? " confirming" : ""}`}
              onClick={(e) => requestDelete(e, w._id)}
              aria-label="删除"
            >
              {confirmingDelete ? "确认" : <Icon name="trash" size={15} />}
            </button>
          </div>
        );
      })}
      <p className="list-end">· end of list ·</p>
    </div>
  );
}
