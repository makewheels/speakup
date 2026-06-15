import { useState, useRef } from "react";
import Icon from "./Icon.jsx";
import { speak, stop, isCached } from "../utils/tts.js";

// 点击 → 没缓存就先合成（显示 spin），合成完播放；缓存命中直接播放。
// 三态：idle(喇叭) / loading(转圈) / playing(停止键+实心高亮)，播放中再点即停。
// stopPropagation 让按钮可以嵌进可点击行里不连带触发。
export default function SpeakBtn({ text, size = 22, className = "spk-btn" }) {
  const [state, setState] = useState("idle"); // idle | loading | playing
  const audioRef = useRef(null);
  if (!text) return null;

  const reset = () => { audioRef.current = null; setState("idle"); };

  const onClick = async (e) => {
    e.stopPropagation();
    if (state === "playing") { stop(); reset(); return; }
    if (state === "loading") return;
    try {
      if (!isCached(text)) setState("loading");
      const audio = await speak(text);
      if (!audio) { reset(); return; }
      audioRef.current = audio;
      setState("playing");
      audio.addEventListener("ended", reset, { once: true });
      audio.addEventListener("pause", reset, { once: true });
    } catch (err) {
      console.warn("TTS failed:", err);
      reset();
    }
  };

  return (
    <button
      className={className + (state === "playing" ? " playing" : "")}
      title={state === "playing" ? "Stop" : "Play"}
      aria-label={state === "loading" ? "Synthesizing" : state === "playing" ? "Stop" : "Play"}
      onClick={onClick}
      disabled={state === "loading"}
    >
      {state === "loading"
        ? <span className="spin" />
        : state === "playing"
        ? <Icon name="stop" size={size} />
        : <Icon name="volume" size={size} />}
    </button>
  );
}
