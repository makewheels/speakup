import { useState, useRef } from "react";
import Icon from "./Icon.jsx";
import { useT } from "../i18n/index.jsx";

// 自定义录音回放：蓝色播放/暂停键 + 进度条 + 时间，结果页和 history 共用，
// 替换浏览器原生 <audio controls>（各浏览器样式不一、跟朗读按钮风格也对不上）。
const fmt = (s) => {
  if (!s || !isFinite(s)) return "0:00";
  const m = Math.floor(s / 60);
  const ss = Math.floor(s % 60).toString().padStart(2, "0");
  return `${m}:${ss}`;
};

export default function RecordingPlayer({ src }) {
  const t = useT();
  const [playing, setPlaying] = useState(false);
  const [cur, setCur] = useState(0);
  const [dur, setDur] = useState(0);
  const audioRef = useRef(null);
  if (!src) return null;

  const toggle = () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) a.play().catch(() => {});
    else a.pause();
  };
  const seek = (e) => {
    const a = audioRef.current;
    if (!a || !dur) return;
    const rect = e.currentTarget.getBoundingClientRect();
    a.currentTime = Math.min(dur, Math.max(0, ((e.clientX - rect.left) / rect.width) * dur));
  };
  const pct = dur > 0 ? (cur / dur) * 100 : 0;

  return (
    <div className="rec-player">
      <button className="rec-player-btn" onClick={toggle} aria-label={playing ? t("player.pause") : t("player.play")}>
        <Icon name={playing ? "pause" : "play"} size={16} color="#fff" />
      </button>
      <div className="rec-player-bar" onClick={seek}>
        <div className="rec-player-fill" style={{ width: pct + "%" }} />
      </div>
      <span className="rec-player-time">{fmt(cur)} / {fmt(dur)}</span>
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(e) => setCur(e.target.currentTime)}
        onLoadedMetadata={(e) => setDur(e.target.duration)}
      />
    </div>
  );
}
