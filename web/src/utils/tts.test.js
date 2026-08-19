/**
 * tts.js 行为测试。重点回归两个真 bug：
 * 1. await audio.play() 卡住 → speak() 永远不返回 → SpeakBtn 一直 loading
 * 2. urlCache 跨 session 撞键（之前 key 只是 text，挪到 session 下后必须 (practiceId, text)）
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// 用 hoisted 让 mock 内部能引用变量
const ttsMock = vi.hoisted(() => vi.fn());
vi.mock("../api/client.js", () => ({ api: { tts: ttsMock } }));

// Audio 在 jsdom 下不能真播；mock 一个最小可观测对象
const audioInstances = [];
class FakeAudio {
  constructor(src) {
    this.src = src;
    this.paused = false;
    this._listeners = {};
    this.play = vi.fn(() => Promise.resolve());
    audioInstances.push(this);
  }
  pause() {
    this.paused = true;
    (this._listeners["pause"] || []).forEach((fn) => fn());
  }
  addEventListener(ev, fn) {
    (this._listeners[ev] ||= []).push(fn);
  }
}
globalThis.Audio = FakeAudio;

describe("utils/tts", () => {
  beforeEach(async () => {
    vi.useRealTimers();
    audioInstances.length = 0;
    ttsMock.mockReset();
    globalThis.speechSynthesis = undefined;
    globalThis.SpeechSynthesisUtterance = undefined;
    // 模块级 urlCache 是 module singleton，重置 modules 让每个 test 重新加载
    vi.resetModules();
  });

  it("不 await audio.play()——浏览器缓冲卡死时 speak() 仍能返回，不让调用方永远 loading", async () => {
    const { speak } = await import("./tts.js");
    ttsMock.mockResolvedValue("https://oss/clip.mp3");
    // 让 play() 永远不 resolve，模拟浏览器缓冲卡住
    const origAudio = globalThis.Audio;
    globalThis.Audio = class extends origAudio {
      constructor(src) {
        super(src);
        this.play = vi.fn(() => new Promise(() => {})); // 永不 resolve
      }
    };
    const audio = await speak("hello", "sess_a");
    expect(audio).not.toBeNull();
    globalThis.Audio = origAudio;
  });

  it("urlCache 按 (practiceId, text) 分键——同 text 跨 session 不互相命中", async () => {
    const { speak } = await import("./tts.js");
    ttsMock
      .mockResolvedValueOnce("https://oss/sess_a.mp3")
      .mockResolvedValueOnce("https://oss/sess_b.mp3");
    await speak("Same text", "sess_a");
    await speak("Same text", "sess_b");
    expect(ttsMock).toHaveBeenCalledTimes(2);
    expect(ttsMock).toHaveBeenNthCalledWith(1, "Same text", "sess_a");
    expect(ttsMock).toHaveBeenNthCalledWith(2, "Same text", "sess_b");
  });

  it("同 (practiceId, text) 重复调用走本地 url 缓存，不再请求后端", async () => {
    const { speak } = await import("./tts.js");
    ttsMock.mockResolvedValue("https://oss/clip.mp3");
    await speak("Replay this", "sess_a");
    await speak("Replay this", "sess_a");
    expect(ttsMock).toHaveBeenCalledTimes(1);
  });

  it("isCached 也按 practiceId 分键", async () => {
    const { speak, isCached } = await import("./tts.js");
    ttsMock.mockResolvedValue("https://oss/clip.mp3");
    await speak("Cached now", "sess_a");
    expect(isCached("Cached now", "sess_a")).toBe(true);
    expect(isCached("Cached now", "sess_b")).toBe(false);
  });

  it("合成 30s 超时兜底，避免按钮永远 loading", async () => {
    vi.useFakeTimers();
    const { speak } = await import("./tts.js");
    ttsMock.mockImplementation(() => new Promise(() => {})); // api.tts 永不返回
    const promise = speak("Slow text", "sess_a");
    vi.advanceTimersByTime(31000);
    await expect(promise).rejects.toThrow(/timeout/i);
  });

  it("空文本 / 空白返回 null，不调后端", async () => {
    const { speak } = await import("./tts.js");
    expect(await speak("", "sess_a")).toBeNull();
    expect(await speak("   ", "sess_a")).toBeNull();
    expect(ttsMock).not.toHaveBeenCalled();
  });

  it("后端 TTS 不可用时降级到浏览器朗读，并停止重复请求后端", async () => {
    const cancel = vi.fn();
    const nativeSpeak = vi.fn();
    globalThis.speechSynthesis = { cancel, speak: nativeSpeak };
    globalThis.SpeechSynthesisUtterance = class {
      constructor(text) { this.text = text; }
    };
    const { speak, isCached, stop } = await import("./tts.js");
    ttsMock.mockRejectedValue(new Error("TTS unavailable"));

    const first = await speak("Fallback text", "sess_a");
    const second = await speak("Another text", "sess_a");

    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    expect(ttsMock).toHaveBeenCalledTimes(1);
    expect(nativeSpeak).toHaveBeenCalledTimes(2);
    expect(isCached("Anything", "sess_b")).toBe(true);
    stop();
    expect(cancel).toHaveBeenCalled();
  });
});
