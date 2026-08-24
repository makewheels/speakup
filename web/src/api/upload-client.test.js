import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./client.js";

function storeToken() {
  localStorage.setItem("english-speak-user", JSON.stringify({ userId: "u1", token: "tok_test" }));
}

describe("api/client FormData 上传方法", () => {
  let fetchMock;

  beforeEach(() => {
    localStorage.clear();
    storeToken();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("uploadRecording 按真实 WebM 容器命名并上传", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve({ ok: 1 }) });
    const blob = new Blob(["x"], { type: "audio/webm;codecs=opus" });
    const res = await api.uploadRecording("p1", "u1", blob, 2);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/practice-sessions/p1/recording");
    expect(opts.method).toBe("POST");
    expect(opts.headers.Authorization).toBe("Bearer tok_test");
    expect(opts.body).toBeInstanceOf(FormData);
    expect(opts.body.get("userId")).toBe("u1");
    expect(opts.body.get("attemptIndex")).toBe("2");
    expect(opts.body.get("audio").name).toBe("recording.webm");
    expect(res).toEqual({ ok: 1 });
  });

  it("uploadRecording 按 Safari 的 MP4 音频命名为 m4a", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve({ ok: 1 }) });
    const blob = new Blob(["x"], { type: "audio/mp4" });
    await api.uploadRecording("p1", "u1", blob, 0);
    expect(fetchMock.mock.calls[0][1].body.get("audio").name).toBe("recording.m4a");
  });

  it("uploadRecording 非 ok → 抛出上传失败", async () => {
    fetchMock.mockResolvedValue({ ok: false });
    const blob = new Blob(["x"], { type: "audio/webm" });
    await expect(api.uploadRecording("p1", "u1", blob)).rejects.toThrow("录音上传失败");
  });

  it("evaluatePronunciation POSTs the linked attempt", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: "completed", overallScore: 82 }),
    });
    const result = await api.evaluatePronunciation("p1", 2);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/practice-sessions/p1/attempts/2/pronunciation");
    expect(opts.method).toBe("POST");
    expect(result.overallScore).toBe(82);
  });

  it("transcribeAudio 成功返回 json，webm 扩展名", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve({ text: "hi" }) });
    const blob = new Blob(["x"], { type: "audio/webm" });
    const res = await api.transcribeAudio("u1", blob);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/transcribe");
    expect(opts.method).toBe("POST");
    expect(opts.headers.Authorization).toBe("Bearer tok_test");
    expect(opts.body.get("userId")).toBe("u1");
    expect(res).toEqual({ text: "hi" });
  });

  it("transcribeAudio 502 → 服务重启文案", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 502 });
    const blob = new Blob(["x"], { type: "audio/webm" });
    await expect(api.transcribeAudio("u1", blob)).rejects.toThrow(/服务正在重启.*502/);
  });

  it("transcribeAudio 其它错误码带 detail", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      text: () => Promise.resolve(JSON.stringify({ detail: "音频太短" })),
    });
    const blob = new Blob(["x"], { type: "audio/wav" });
    await expect(api.transcribeAudio("u1", blob)).rejects.toThrow("音频太短");
  });

  it("transcribeAudio AbortError → 识别超时文案", async () => {
    fetchMock.mockImplementation(() => {
      const error = new Error("aborted");
      error.name = "AbortError";
      return Promise.reject(error);
    });
    const blob = new Blob(["x"], { type: "audio/webm" });
    await expect(api.transcribeAudio("u1", blob)).rejects.toThrow("识别超时（90s），请重试");
  });
});
