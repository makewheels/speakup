// 朗读：点击时调后端 /api/tts（DashScope CosyVoice，自然音），结果按文本缓存。
// 后端按文本哈希缓存到 OSS，同一句话第二次不再花钱。
import { api } from "../api/client.js";

const urlCache = new Map(); // text -> oss url
let current = null; // 当前播放的 Audio，切歌时停掉

export function isCached(text) {
  return urlCache.has((text || "").trim());
}

export async function speak(text) {
  text = (text || "").trim();
  if (!text) return;
  if (current) { current.pause(); current = null; }
  let url = urlCache.get(text);
  if (!url) {
    url = await api.tts(text);
    urlCache.set(text, url);
  }
  const audio = new Audio(url);
  current = audio;
  await audio.play();
}
