// 朗读：点击时先调后端 /api/tts（云端自然语音），
// 云端不可用时在当前页面降级到浏览器 speechSynthesis。
// 后端按 session / attempt / purpose 归档，内容 hash 负责同类音频去重。
import { api } from "../api/client.js";

const urlCache = new Map();
const BROWSER_TTS = Symbol("browser-tts");
let current = null; // 当前播放的 Audio，切歌/停止时停掉
let backendUnavailable = false;

const _key = (text, practiceId, attemptIndex, purpose) => (
  `${practiceId || ""}:${attemptIndex}:${purpose}:${(text || "").trim()}`
);

export function isCached(text, practiceId, attemptIndex = -1, purpose = "other") {
  return backendUnavailable || urlCache.has(_key(text, practiceId, attemptIndex, purpose));
}

function browserSpeak(text) {
  const synth = globalThis.speechSynthesis;
  const Utterance = globalThis.SpeechSynthesisUtterance;
  if (!synth || !Utterance) throw new Error("Browser speech synthesis unavailable");

  const listeners = new Map();
  const emit = (event) => {
    for (const listener of listeners.get(event) || []) listener();
  };
  const utterance = new Utterance(text);
  utterance.lang = "en-US";
  utterance.rate = 0.95;
  utterance.onend = () => emit("ended");
  utterance.onerror = () => emit("error");

  const playback = {
    addEventListener(event, listener) {
      const entries = listeners.get(event) || [];
      entries.push(listener);
      listeners.set(event, entries);
    },
    pause() {
      synth.cancel();
      emit("pause");
    },
  };
  synth.cancel();
  synth.speak(utterance);
  return playback;
}

// 停止当前播放（会触发该 Audio 的 pause 事件，调用方据此复位 UI）
export function stop() {
  if (current) {
    const active = current;
    current = null;
    active.pause();
  }
}

// 播放并返回 Audio 实例：调用方可监听 ended / pause 来同步「正在播放」状态。
// 关键：合成（api.tts）阶段是「generating」，拿到 URL 即返回；不 await audio.play()，
// 否则浏览器缓冲卡住会让调用方的 loading 态一直转圈（曾经的「一直在生成」bug）。
export async function speak(text, practiceId, attemptIndex = -1, purpose = "other") {
  text = (text || "").trim();
  if (!text) return null;
  stop();
  const k = _key(text, practiceId, attemptIndex, purpose);
  let url = urlCache.get(k);
  if (url === BROWSER_TTS || (!url && backendUnavailable)) {
    const playback = browserSpeak(text);
    current = playback;
    return playback;
  }
  if (!url) {
    // 合成加 30s 超时兜底，网络挂死也不会让按钮永远 loading
    try {
      url = await Promise.race([
        api.tts(text, practiceId, attemptIndex, purpose),
        new Promise((_, rej) => setTimeout(() => rej(new Error("TTS timeout")), 30000)),
      ]);
      urlCache.set(k, url);
    } catch (error) {
      if (!globalThis.speechSynthesis || !globalThis.SpeechSynthesisUtterance) throw error;
      backendUnavailable = true;
      urlCache.set(k, BROWSER_TTS);
      const playback = browserSpeak(text);
      current = playback;
      return playback;
    }
  }
  const audio = new Audio(url);
  current = audio;
  audio.addEventListener("ended", () => { if (current === audio) current = null; });
  // 不 await：play() 在用户手势触发下通常立即开始；失败只记日志，不阻塞 UI
  audio.play().catch((e) => console.warn("audio.play failed:", e));
  return audio;
}
