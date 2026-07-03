import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { api, correctStream, chatStream } from "./client.js";

const USER_KEY = "english-speak-user";

function storeToken(token = "tok_test") {
  localStorage.setItem(USER_KEY, JSON.stringify({ userId: "u1", token }));
}

// 把若干 SSE 文本帧封成一个最小可读流：每帧一次 read()
function sseStream(frames) {
  const encoder = new TextEncoder();
  let i = 0;
  return {
    getReader() {
      return {
        read() {
          if (i < frames.length) {
            return Promise.resolve({ done: false, value: encoder.encode(frames[i++]) });
          }
          return Promise.resolve({ done: true, value: undefined });
        },
      };
    },
  };
}

describe("api/client request 封装", () => {
  let fetchMock;

  beforeEach(() => {
    localStorage.clear();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const okJson = (data) => ({
    ok: true,
    json: () => Promise.resolve(data),
  });

  it("成功响应返回 .json() 解析结果", async () => {
    fetchMock.mockResolvedValue(okJson({ userId: "u1" }));
    const res = await api.login("13800000000");
    expect(res).toEqual({ userId: "u1" });
  });

  it("login 拼对 URL / method / JSON body / Content-Type", async () => {
    fetchMock.mockResolvedValue(okJson({}));
    await api.login("13800000000");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/login");
    expect(opts.method).toBe("POST");
    expect(opts.headers["Content-Type"]).toBe("application/json");
    expect(opts.body).toBe(JSON.stringify({ phone: "13800000000" }));
    expect(opts.signal).toBeInstanceOf(AbortSignal);
  });

  it("GET 请求不带 body（getPractice 拼 URL）", async () => {
    storeToken();
    fetchMock.mockResolvedValue(okJson({ id: "p1" }));
    await api.getPractice("p1");
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/practice-sessions/p1");
    expect(opts.method).toBeUndefined();
    expect(opts.body).toBeUndefined();
    expect(opts.headers.Authorization).toBe("Bearer tok_test");
  });

  it("响应非 ok 且 body 带 error → 抛出该 error 文案", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "手机号格式错误" }),
    });
    await expect(api.login("bad")).rejects.toThrow("手机号格式错误");
  });

  it("响应 401 时清掉本地登录态", async () => {
    storeToken();
    const onUnauthorized = vi.fn();
    window.addEventListener("speakup:unauthorized", onUnauthorized);
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: "请先登录" }),
    });
    await expect(api.getPractice("p1")).rejects.toThrow("请先登录");
    expect(localStorage.getItem(USER_KEY)).toBeNull();
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    window.removeEventListener("speakup:unauthorized", onUnauthorized);
  });

  it("响应非 ok 且 body 解析失败 → 抛出默认 Request failed", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      json: () => Promise.reject(new Error("invalid json")),
    });
    await expect(api.login("bad")).rejects.toThrow("Request failed");
  });

  it("超时（AbortError）→ 抛出中文超时文案", async () => {
    fetchMock.mockImplementation(() => {
      const e = new Error("aborted");
      e.name = "AbortError";
      return Promise.reject(e);
    });
    await expect(api.login("13800000000")).rejects.toThrow("请求超时，请重试");
  });

  it("非 Abort 的网络错误原样抛出", async () => {
    fetchMock.mockRejectedValue(new Error("network down"));
    await expect(api.login("13800000000")).rejects.toThrow("network down");
  });
});

describe("api/client 各方法 URL/method/body", () => {
  let fetchMock;

  beforeEach(() => {
    localStorage.clear();
    storeToken();
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  const callArgs = () => fetchMock.mock.calls[0];

  it("nextScenario 拼 userId + 多个 exclude 查询参数", async () => {
    await api.nextScenario("u1", ["sc_1", "sc_2"]);
    const [url] = callArgs();
    expect(url).toBe("/api/scenarios/next?userId=u1&exclude=sc_1&exclude=sc_2");
  });

  it("nextScenario 拼练习偏好", async () => {
    await api.nextScenario("u1", ["sc_1"], { level: "beginner", purpose: "travel" });
    const [url] = callArgs();
    expect(url).toBe("/api/scenarios/next?userId=u1&exclude=sc_1&level=beginner&purpose=travel");
  });

  it("nextScenario 默认无 exclude", async () => {
    await api.nextScenario("u1");
    const [url] = callArgs();
    expect(url).toBe("/api/scenarios/next?userId=u1");
  });

  it("practiceWord POST + body + 自定义 timeout", async () => {
    await api.practiceWord("u1", "give it a shot", "原句");
    const [url, opts] = callArgs();
    expect(url).toBe("/api/scenarios/practice-word");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(
      JSON.stringify({ userId: "u1", expression: "give it a shot", original: "原句" }),
    );
  });

  it("createPractice POST body", async () => {
    await api.createPractice({ userId: "u1", scenarioId: "sc_1" });
    const [url, opts] = callArgs();
    expect(url).toBe("/api/practice-sessions");
    expect(opts.method).toBe("POST");
    expect(opts.headers.Authorization).toBe("Bearer tok_test");
    expect(opts.body).toBe(JSON.stringify({ userId: "u1", scenarioId: "sc_1" }));
  });

  it("listPractices 拼 userId + skip", async () => {
    await api.listPractices("u1", 20);
    expect(callArgs()[0]).toBe("/api/practice-sessions?userId=u1&skip=20");
  });

  it("sharePractice POST share 路径 + userId body", async () => {
    await api.sharePractice("p1", "u1");
    const [url, opts] = callArgs();
    expect(url).toBe("/api/practice-sessions/p1/share");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ userId: "u1" }));
  });

  it("unsharePractice DELETE share 路径带 userId query", async () => {
    await api.unsharePractice("p1", "u1");
    const [url, opts] = callArgs();
    expect(url).toBe("/api/practice-sessions/p1/share?userId=u1");
    expect(opts.method).toBe("DELETE");
  });

  it("getSharedSession 拼 token 路径", async () => {
    await api.getSharedSession("tok_abc");
    expect(callArgs()[0]).toBe("/api/share/tok_abc");
  });

  it("listShared 拼 sharedOnly=true", async () => {
    await api.listShared("u1");
    expect(callArgs()[0]).toBe("/api/practice-sessions?userId=u1&sharedOnly=true");
  });

  it("correct POST body", async () => {
    await api.correct({ practiceId: "p1", text: "hi" });
    const [url, opts] = callArgs();
    expect(url).toBe("/api/correct");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ practiceId: "p1", text: "hi" }));
  });

  it("addReviewItems POST body", async () => {
    await api.addReviewItems("u1", [{ expression: "x" }]);
    const [url, opts] = callArgs();
    expect(url).toBe("/api/review-items");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ userId: "u1", items: [{ expression: "x" }] }));
  });

  it("listReviewItems 拼 userId + due", async () => {
    await api.listReviewItems("u1", true);
    expect(callArgs()[0]).toBe("/api/review-items?userId=u1&due=true");
  });

  it("listReviewItems 默认 due=false", async () => {
    await api.listReviewItems("u1");
    expect(callArgs()[0]).toBe("/api/review-items?userId=u1&due=false");
  });

  it("reviewItem POST 路径带 userId + remembered body", async () => {
    await api.reviewItem("r1", "u1", true);
    const [url, opts] = callArgs();
    expect(url).toBe("/api/review-items/r1/review?userId=u1");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ remembered: true }));
  });

  it("deleteReviewItem DELETE 路径带 userId", async () => {
    await api.deleteReviewItem("r1", "u1");
    const [url, opts] = callArgs();
    expect(url).toBe("/api/review-items/r1?userId=u1");
    expect(opts.method).toBe("DELETE");
  });

  it("tts POST body 并取 .url 字段", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ url: "https://oss/clip.mp3" }),
    });
    const url = await api.tts("hello", "p1");
    const [callUrl, opts] = callArgs();
    expect(callUrl).toBe("/api/tts");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ text: "hello", practiceId: "p1" }));
    expect(url).toBe("https://oss/clip.mp3");
  });
});

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

  it("uploadRecording POST FormData，成功返回 json", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve({ ok: 1 }) });
    const blob = new Blob(["x"], { type: "audio/webm" });
    const res = await api.uploadRecording("p1", "u1", blob, 2);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/practice-sessions/p1/recording");
    expect(opts.method).toBe("POST");
    expect(opts.headers.Authorization).toBe("Bearer tok_test");
    expect(opts.body).toBeInstanceOf(FormData);
    expect(opts.body.get("userId")).toBe("u1");
    expect(opts.body.get("attemptIndex")).toBe("2");
    expect(res).toEqual({ ok: 1 });
  });

  it("uploadRecording 非 ok → 抛出上传失败", async () => {
    fetchMock.mockResolvedValue({ ok: false });
    const blob = new Blob(["x"], { type: "audio/webm" });
    await expect(api.uploadRecording("p1", "u1", blob)).rejects.toThrow("录音上传失败");
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
      const e = new Error("aborted");
      e.name = "AbortError";
      return Promise.reject(e);
    });
    const blob = new Blob(["x"], { type: "audio/webm" });
    await expect(api.transcribeAudio("u1", blob)).rejects.toThrow("识别超时（90s），请重试");
  });
});

describe("api/client SSE 流（correctStream / chatStream）", () => {
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

  const flush = () => new Promise((r) => setTimeout(r, 0));

  it("correctStream 解析 chunk + done 事件，回调依次触发", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      body: sseStream([
        'data: {"type":"chunk","text":"He"}\n\n',
        'data: {"type":"chunk","text":"llo"}\n\ndata: {"type":"done","result":{"score":9},"autoSaved":true,"round":2}\n\n',
      ]),
    });
    const onChunk = vi.fn();
    const onDone = vi.fn();
    const onError = vi.fn();
    const ctrl = correctStream({ text: "hi" }, { onChunk, onDone, onError });
    expect(ctrl).toBeInstanceOf(AbortController);

    await flush();
    await flush();

    expect(onChunk).toHaveBeenNthCalledWith(1, "He");
    expect(onChunk).toHaveBeenNthCalledWith(2, "llo");
    expect(onDone).toHaveBeenCalledWith({ result: { score: 9 }, autoSaved: true, round: 2 });
    expect(onError).not.toHaveBeenCalled();

    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/correct/stream");
    expect(opts.method).toBe("POST");
    expect(opts.headers.Authorization).toBe("Bearer tok_test");
    expect(opts.body).toBe(JSON.stringify({ text: "hi" }));
  });

  it("correctStream 收到 error 事件 → onError", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      body: sseStream(['data: {"type":"error","message":"模型炸了"}\n\n']),
    });
    const onError = vi.fn();
    correctStream({ text: "hi" }, { onError });
    await flush();
    await flush();
    expect(onError).toHaveBeenCalled();
    expect(onError.mock.calls[0][0].message).toBe("模型炸了");
  });

  it("correctStream 非 ok 响应 → onError 带 detail", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: "请求体非法" }),
    });
    const onError = vi.fn();
    correctStream({ text: "hi" }, { onError });
    await flush();
    await flush();
    expect(onError).toHaveBeenCalled();
    expect(onError.mock.calls[0][0].message).toBe("请求体非法");
  });

  it("correctStream AbortError → 超时文案", async () => {
    fetchMock.mockImplementation(() => {
      const e = new Error("aborted");
      e.name = "AbortError";
      return Promise.reject(e);
    });
    const onError = vi.fn();
    correctStream({ text: "hi" }, { onError });
    await flush();
    await flush();
    expect(onError.mock.calls[0][0].message).toBe("请求超时，请重试");
  });

  it("chatStream 解析 chunk + done(text) 事件", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      body: sseStream([
        'data: {"type":"chunk","text":"答"}\n\ndata: {"type":"done","text":"答案全文"}\n\n',
      ]),
    });
    const onChunk = vi.fn();
    const onDone = vi.fn();
    chatStream({ question: "why" }, { onChunk, onDone });
    await flush();
    await flush();
    expect(onChunk).toHaveBeenCalledWith("答");
    expect(onDone).toHaveBeenCalledWith({ text: "答案全文" });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/correct/chat/stream");
  });

  it("chatStream 非 ok 响应 → onError", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "boom" }),
    });
    const onError = vi.fn();
    chatStream({ question: "why" }, { onError });
    await flush();
    await flush();
    expect(onError.mock.calls[0][0].message).toBe("boom");
  });
});
