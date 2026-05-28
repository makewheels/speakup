import { useState, useEffect, useRef } from "react";
import { useUser } from "../context/UserContext.jsx";
import { api } from "../api/client.js";
import Icon from "../components/Icon.jsx";

const FILTERS = [
  { key: "all",      label: "全部" },
  { key: "due",      label: "待复习" },
  { key: "mastered", label: "已掌握" },
];

export default function VocabularyPage() {
  const { user } = useUser();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [reviewMode, setReviewMode] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [pendingDeleteId, setPendingDeleteId] = useState(null);
  const deleteTimerRef = useRef(null);

  const fetchItems = () => {
    api.listVocabulary(user.userId)
      .then(setItems)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchItems();
  }, [user.userId]);

  const isMastered = (w) => (w.reviewCount || 0) >= 3 && (w.interval || 0) >= 7;
  const isDue = (w) => new Date(w.nextReviewAt) <= new Date() && !isMastered(w);

  const filtered = filter === "all" ? items
                 : filter === "due" ? items.filter(isDue)
                 : items.filter(isMastered);

  const dueCount = items.filter(isDue).length;

  const handleReview = async (remembered) => {
    const w = items[currentIndex];
    await api.reviewWord(w._id, user.userId, remembered);
    setShowAnswer(false);
    if (currentIndex < items.length - 1) {
      setCurrentIndex(currentIndex + 1);
    } else {
      setReviewMode(false);
      setCurrentIndex(0);
      fetchItems();
    }
  };

  const startReview = () => {
    const dueItems = items.filter(isDue).sort(
      (a, b) => new Date(a.nextReviewAt) - new Date(b.nextReviewAt)
    );
    if (!dueItems.length) return;
    setItems((prev) => {
      const dueIds = new Set(dueItems.map((d) => d._id));
      return [...dueItems, ...prev.filter((p) => !dueIds.has(p._id))];
    });
    setCurrentIndex(0);
    setShowAnswer(false);
    setReviewMode(true);
  };

  const deleteItem = async (id) => {
    await api.deleteWord(id, user.userId);
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

  if (reviewMode && items.length > 0) {
    const w = items[currentIndex];
    return (
      <div className="review-session-page fade-in">
        <div className="head">
          <span>复习 {currentIndex + 1} / {items.length}</span>
          <button className="exit" onClick={() => setReviewMode(false)}>退出</button>
        </div>
        <div className="flashcard" onClick={() => setShowAnswer(true)}>
          {!showAnswer ? (
            <>
              <p className="front-text">{w.original || w.contextSentence || "?"}</p>
              <span className="tap-hint">点击查看地道表达</span>
            </>
          ) : (
            <>
              <p className="back-target">{w.word}</p>
              {w.note && <p className="back-note">{w.note}</p>}
              {w.contextSentence && <p className="back-context">"{w.contextSentence}"</p>}
              <div className="verdict-row">
                <button
                  className="su-btn su-btn-secondary"
                  onClick={(e) => { e.stopPropagation(); handleReview(false); }}
                  style={{ flex: 1, height: 48 }}
                >
                  没想起来
                </button>
                <button
                  className="su-btn su-btn-primary"
                  onClick={(e) => { e.stopPropagation(); handleReview(true); }}
                  style={{ flex: 1, height: 48 }}
                >
                  想起来了
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="review-page">
      <div className="page-head">
        <h2>复习</h2>
      </div>

      {items.length > 0 && (
        <div className="su-summary">
          <div className="row">
            <div>
              <div className="eyebrow">in total</div>
              <div className="big">{items.length}<span className="unit">项</span></div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div className="eyebrow">due today</div>
              <div className="big">{dueCount}<span className="unit">项</span></div>
            </div>
          </div>
          {dueCount > 0 && (
            <button className="start-btn" onClick={startReview}>
              开始今天的复习 →
            </button>
          )}
        </div>
      )}

      {items.length > 0 && (
        <div className="filter-tabs">
          {FILTERS.map((f) => {
            const n = f.key === "all" ? items.length
                    : f.key === "due" ? items.filter(isDue).length
                    : items.filter(isMastered).length;
            return (
              <button
                key={f.key}
                className={`tab${filter === f.key ? " active" : ""}`}
                onClick={() => setFilter(f.key)}
              >
                {f.label}<span className="n">{n}</span>
              </button>
            );
          })}
        </div>
      )}

      {items.length === 0 ? (
        <div className="empty-state">
          <div className="icon-box">
            <Icon name="book" size={28} color="var(--ink-3)" stroke={1.4} />
          </div>
          <p className="title">还没有复习项</p>
          <p className="sub">去练习里说一段试试</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="page-msg">这里还没有内容</div>
      ) : (
        <>
          {[...filtered]
            .sort((a, b) => {
              const rank = (w) => isDue(w) ? 0 : isMastered(w) ? 2 : 1;
              return rank(a) - rank(b);
            })
            .map((w) => {
            const mastered = isMastered(w);
            const due = isDue(w);
            const expanded = expandedId === w._id;
            const confirmingDelete = pendingDeleteId === w._id;
            return (
              <div
                key={w._id}
                className={`vocab-row${expanded ? " expanded" : ""}`}
                onClick={() => setExpandedId(expanded ? null : w._id)}
              >
                {w.imageUrl
                  ? <img src={w.imageUrl} alt="" className="thumb" />
                  : <div className="thumb" />
                }
                <div className="vocab-body">
                  {w.title && <div className="vocab-title">{w.title}</div>}
                  <div className="vocab-word">{w.word}</div>
                  {w.original && <div className="vocab-original">你说的：{w.original}</div>}
                  {w.note && <div className="vocab-note">{w.note}</div>}
                  {expanded && w.contextSentence && (
                    <div className="vocab-example">"{w.contextSentence}"</div>
                  )}
                  <span className={`vocab-status${due ? " due" : mastered ? " mastered" : ""}`}>
                    {mastered ? "已掌握" : due ? "待复习" : "复习中"}
                  </span>
                </div>
                <button
                  className={`delete-btn${confirmingDelete ? " confirming" : ""}`}
                  onClick={(e) => requestDelete(e, w._id)}
                  aria-label="删除"
                >
                  {confirmingDelete ? "确认" : <Icon name="trash" size={16} />}
                </button>
              </div>
            );
          })}
          <p className="list-end">· end of list ·</p>
        </>
      )}
    </div>
  );
}
