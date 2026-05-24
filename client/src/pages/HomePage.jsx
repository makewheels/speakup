import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { api } from "../api/client.js";

const TOPICS = [
  { key: "daily", label: "日常", emoji: "🛒" },
  { key: "travel", label: "旅行", emoji: "✈️" },
  { key: "nature", label: "自然", emoji: "🌳" },
  { key: "social", label: "社交", emoji: "🎉" },
  { key: "home", label: "居家", emoji: "🏠" },
  { key: "city", label: "城市", emoji: "🌆" },
];

export default function HomePage() {
  const { user } = useUser();
  const navigate = useNavigate();
  const [topic, setTopic] = useState("daily");
  const [loading, setLoading] = useState(false);

  const startPractice = async () => {
    setLoading(true);
    try {
      const imageResult = await api.generateImage(topic);
      const session = await api.createSession({
        userId: user.userId,
        topic: imageResult.topic,
        sceneDescription: imageResult.prompt,
        imageUrl: imageResult.imageUrl,
        imagePrompt: imageResult.prompt,
      });
      navigate(`/practice/${session._id}`);
    } catch (err) {
      alert("生成失败: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="home-page">
      <h2>你好，{user.nickname}</h2>
      <p className="subtitle">选择一个场景开始练习</p>

      <div className="topic-grid">
        {TOPICS.map((t) => (
          <button
            key={t.key}
            className={`topic-card ${topic === t.key ? "active" : ""}`}
            onClick={() => setTopic(t.key)}
          >
            <span className="topic-emoji">{t.emoji}</span>
            <span className="topic-label">{t.label}</span>
          </button>
        ))}
      </div>

      <button className="start-btn" onClick={startPractice} disabled={loading}>
        {loading ? "生成图片中..." : "开始练习"}
      </button>
    </div>
  );
}
