import { useState, useRef } from "react";
import Icon from "./Icon.jsx";
import { useT } from "../i18n/useI18n.js";

// 录音回放小按钮：跟 SpeakBtn 同款样式（spk-btn），嵌在「You said」标签行。
// 两态：idle(play) / playing(stop)，播放完自动复位。区别于 SpeakBtn 的 TTS 合成，这里直接播录音文件。
export default function RecordingPlayBtn({ src, size = 22, className = "spk-btn" }) {
  const t = useT();
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef(null);
  if (!src) return null;

  const onClick = (e) => {
    e.stopPropagation();
    const a = audioRef.current;
    if (!a) return;
    if (playing) { a.pause(); return; }
    a.play().catch(() => setPlaying(false));
  };

  return (
    <button
      className={className + (playing ? " playing" : "")}
      title={playing ? t("player.stop") : t("player.play")}
      aria-label={playing ? t("player.stop") : t("player.play")}
      onClick={onClick}
    >
      <Icon name={playing ? "stop" : "play"} size={size} />
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
    </button>
  );
}
