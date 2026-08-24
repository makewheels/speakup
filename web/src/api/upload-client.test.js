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

  it("uploadRecording uses the stable Attempt id when available", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve({ ok: 1 }) });
    const blob = new Blob(["x"], { type: "audio/webm" });
    await api.uploadRecording("p1", "u1", blob, "pa_1787578000000aaaaaaaaaa");
    const form = fetchMock.mock.calls[0][1].body;
    expect(form.get("attemptId")).toBe("pa_1787578000000aaaaaaaaaa");
    expect(form.get("attemptIndex")).toBeNull();
  });

  it("uploadRecording 非 ok → 抛出上传失败", async () => {
    fetchMock.mockResolvedValue({ ok: false });
    const blob = new Blob(["x"], { type: "audio/webm" });
    await expect(api.uploadRecording("p1", "u1", blob)).rejects.toThrow("录音上传失败");
  });

  it("submitFeedback sends multiple image originals in one multipart request", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve({ _id: "fb_1" }) });
    const first = new File(["one-original"], "one.png", { type: "image/png" });
    const second = new File(["two-original"], "two.jpg", { type: "image/jpeg" });

    await api.submitFeedback({ type: "general", comment: "layout" }, [first, second]);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/feedbacks/with-images");
    expect(options.headers.Authorization).toBe("Bearer tok_test");
    expect(options.body).toBeInstanceOf(FormData);
    expect(JSON.parse(options.body.get("payload"))).toEqual({ type: "general", comment: "layout" });
    expect(options.body.getAll("images").map((file) => file.name)).toEqual(["one.png", "two.jpg"]);
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
