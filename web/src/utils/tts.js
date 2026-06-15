// 朗读：点击时调后端 /api/tts（DashScope CosyVoice，自然音），结果按文本缓存。
// 后端按文本哈希缓存到 OSS，同一句话第二次不再花钱。
import { api } from "../api/client.js";

const urlCache = new Map(); // text -> oss url
let current = null; // 当前播放的 Audio，切歌/停止时停掉

export function isCached(text) {
  return urlCache.has((text || "").trim());
}

// 停止当前播放（会触发该 Audio 的 pause 事件，调用方据此复位 UI）
export function stop() {
  if (current) {
    current.pause();
    current = null;
  }
}

// 播放并返回 Audio 实例：调用方可监听 ended / pause 来同步「正在播放」状态。
export async function speak(text) {
  text = (text || "").trim();
  if (!text) return null;
  stop();
  let url = urlCache.get(text);
  if (!url) {
    url = await api.tts(text);
    urlCache.set(text, url);
  }
  const audio = new Audio(url);
  current = audio;
  audio.addEventListener("ended", () => { if (current === audio) current = null; });
  await audio.play();
  return audio;
}
