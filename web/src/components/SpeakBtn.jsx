import { useState } from "react";
import Icon from "./Icon.jsx";
import { speak, isCached } from "../utils/tts.js";

// 点击 → 没缓存就先合成（显示 spin），合成完播放；缓存命中直接播放。
// stopPropagation 让按钮可以嵌进可点击行里不连带触发。
export default function SpeakBtn({ text, size = 22, className = "spk-btn" }) {
  const [loading, setLoading] = useState(false);
  if (!text) return null;
  const onClick = async (e) => {
    e.stopPropagation();
    if (loading) return;
    if (isCached(text)) {
      speak(text).catch((err) => console.warn("TTS failed:", err));
      return;
    }
    setLoading(true);
    try {
      await speak(text);
    } catch (err) {
      console.warn("TTS failed:", err);
    } finally {
      setLoading(false);
    }
  };
  return (
    <button
      className={className}
      title="Play"
      aria-label={loading ? "Synthesizing" : "Play"}
      onClick={onClick}
      disabled={loading}
    >
      {loading ? <span className="spin" /> : <Icon name="volume" size={size} />}
    </button>
  );
}
