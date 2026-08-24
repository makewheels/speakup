import { useState, useRef } from "react";
import Icon from "./Icon.jsx";
import { useT } from "../i18n/useI18n.js";
import { speak, stop, isCached } from "../utils/tts.js";

// 点击 → 没缓存就先合成（显示「生成中」动画文字），合成完播放；缓存命中直接播放。
// 三态：idle(喇叭) / loading(生成中动画点) / playing(停止键+实心高亮)，播放中再点即停。
// practiceId：传进来则朗读音频按 (practiceId, 文本) 挂在该 session 下；不传走全局兜底。
// stopPropagation 让按钮可以嵌进可点击行里不连带触发。
export default function SpeakBtn({
  text, practiceId, size = 22, className = "spk-btn", label = "",
}) {
  const t = useT();
  const [state, setState] = useState("idle"); // idle | loading | playing
  const audioRef = useRef(null);
  if (!text) return null;

  const reset = () => { audioRef.current = null; setState("idle"); };

  const onClick = async (e) => {
    e.stopPropagation();
    if (state === "playing") { stop(); reset(); return; }
    if (state === "loading") return;
    try {
      if (!isCached(text, practiceId)) setState("loading");
      const audio = await speak(text, practiceId);
      if (!audio) { reset(); return; }
      audioRef.current = audio;
      setState("playing");
      audio.addEventListener("ended", reset, { once: true });
      audio.addEventListener("pause", reset, { once: true });
      audio.addEventListener("error", reset, { once: true });   // 播放失败也复位，不卡在播放态
    } catch (err) {
      console.warn("TTS failed:", err);
      reset();
    }
  };

  return (
    <button
      className={
        className +
        (state === "playing" ? " playing" : "") +
        (state === "loading" ? " loading" : "")
      }
      title={state === "playing" ? t("player.stop") : t("player.play")}
      aria-label={state === "loading" ? t("player.synthesizing") : state === "playing" ? t("player.stop") : t("player.play")}
      onClick={onClick}
      disabled={state === "loading"}
    >
      {state === "loading" ? (
        <span className="spk-gen">
          <i>·</i><i>·</i><i>·</i>
        </span>
      ) : state === "playing" ? (
        <Icon name="stop" size={size} />
      ) : (
        <Icon name="volume" size={size} />
      )}
      {label && <span>{label}</span>}
    </button>
  );
}
