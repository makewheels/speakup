import { useState, useEffect } from "react";
import { useUser } from "../context/UserContext.jsx";
import { api } from "../api/client.js";

export default function VocabularyPage() {
  const { user } = useUser();
  const [words, setWords] = useState([]);
  const [reviewMode, setReviewMode] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchWords = () => {
    api
      .listVocabulary(user.userId)
      .then(setWords)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchWords();
  }, [user.userId]);

  const handleReview = async (remembered) => {
    const word = words[currentIndex];
    await api.reviewWord(word._id, remembered);
    setShowAnswer(false);
    if (currentIndex < words.length - 1) {
      setCurrentIndex(currentIndex + 1);
    } else {
      setReviewMode(false);
      setCurrentIndex(0);
      fetchWords(); // refresh intervals
    }
  };

  const deleteWord = async (id) => {
    await api.deleteWord(id);
    setWords(words.filter((w) => w._id !== id));
  };

  if (loading) return <div className="page-msg">加载中...</div>;

  if (reviewMode && words.length > 0) {
    const word = words[currentIndex];
    return (
      <div className="review-page">
        <div className="review-header">
          <span>
            复习 {currentIndex + 1} / {words.length}
          </span>
          <button className="exit-review" onClick={() => setReviewMode(false)}>
            退出
          </button>
        </div>
        <div className="review-card" onClick={() => setShowAnswer(true)}>
          {!showAnswer ? (
            <div className="review-front">
              <p className="chinese-hint">{word.chinese || "点击查看英文"}</p>
              <span className="tap-hint">点击查看答案</span>
            </div>
          ) : (
            <div className="review-back">
              <p className="english-word">{word.word}</p>
              {word.contextSentence && (
                <p className="context-sentence">{word.contextSentence}</p>
              )}
              <div className="review-buttons">
                <button className="forgot-btn" onClick={() => handleReview(false)}>
                  没想起来
                </button>
                <button className="remembered-btn" onClick={() => handleReview(true)}>
                  想起来了
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  const dueWords = words.filter((w) => new Date(w.nextReviewAt) <= new Date());

  return (
    <div className="vocab-page">
      <h2>生词本</h2>

      {dueWords.length > 0 && (
        <button
          className="start-review-btn"
          onClick={() => {
            setWords(words.sort((a, b) => new Date(a.nextReviewAt) - new Date(b.nextReviewAt)));
            setCurrentIndex(0);
            setReviewMode(true);
          }}
        >
          开始复习 ({dueWords.length} 个待复习)
        </button>
      )}

      {words.length === 0 ? (
        <div className="page-msg">还没有生词，去练习吧！</div>
      ) : (
        <div className="word-list">
          {words.map((w) => (
            <div key={w._id} className="word-item">
              <div className="word-main">
                <span className="word-english">{w.word}</span>
                <span className="word-chinese">{w.chinese}</span>
              </div>
              {w.contextSentence && (
                <p className="word-context">{w.contextSentence}</p>
              )}
              <div className="word-meta">
                <span>已复习 {w.reviewCount} 次</span>
                <span>
                  {new Date(w.nextReviewAt) <= new Date()
                    ? "待复习"
                    : `下次 ${new Date(w.nextReviewAt).toLocaleDateString("zh-CN")}`}
                </span>
              </div>
              <button className="del-word" onClick={() => deleteWord(w._id)}>
                删除
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
