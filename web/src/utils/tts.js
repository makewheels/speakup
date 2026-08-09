// 朗读：点击时调后端 /api/tts（DashScope Qwen TTS，自然音）。
// 后端按 (practiceId, 文本) hash 把 wav 存到 practiceSessions/{practiceId}/tts/，
// 这样所有 session 资源都在 practiceSessions/ 下；session 内重听同一段命中 OSS 缓存不重花钱。
import { api } from "../api/client.js";

const urlCache = new Map(); // "{practiceId}:{text}" -> oss url
let current = null; // 当前播放的 Audio，切歌/停止时停掉

const _key = (text, practiceId) => `${practiceId || ""}:${(text || "").trim()}`;

export function isCached(text, practiceId) {
  return urlCache.has(_key(text, practiceId));
}

// 停止当前播放（会触发该 Audio 的 pause 事件，调用方据此复位 UI）
export function stop() {
  if (current) {
    current.pause();
    current = null;
  }
}

// 播放并返回 Audio 实例：调用方可监听 ended / pause 来同步「正在播放」状态。
// 关键：合成（api.tts）阶段是「generating」，拿到 URL 即返回；不 await audio.play()，
// 否则浏览器缓冲卡住会让调用方的 loading 态一直转圈（曾经的「一直在生成」bug）。
export async function speak(text, practiceId) {
  text = (text || "").trim();
  if (!text) return null;
  stop();
  const k = _key(text, practiceId);
  let url = urlCache.get(k);
  if (!url) {
    // 合成加 30s 超时兜底，网络挂死也不会让按钮永远 loading
    url = await Promise.race([
      api.tts(text, practiceId),
      new Promise((_, rej) => setTimeout(() => rej(new Error("TTS timeout")), 30000)),
    ]);
    urlCache.set(k, url);
  }
  const audio = new Audio(url);
  current = audio;
  audio.addEventListener("ended", () => { if (current === audio) current = null; });
  // 不 await：play() 在用户手势触发下通常立即开始；失败只记日志，不阻塞 UI
  audio.play().catch((e) => console.warn("audio.play failed:", e));
  return audio;
}
