import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./client.js";

const USER_KEY = "english-speak-user";

describe("api/client 发音词片段", () => {
  let fetchMock;

  beforeEach(() => {
    localStorage.setItem(USER_KEY, JSON.stringify({ userId: "u1", token: "tok_test" }));
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("owner 请求带鉴权并返回真实词片段", async () => {
    const clip = new Blob(["clip"], { type: "audio/wav" });
    fetchMock.mockResolvedValue({ ok: true, blob: () => Promise.resolve(clip) });

    const result = await api.getPronunciationClip("p1", 2, 1);
    const [url, opts] = fetchMock.mock.calls[0];

    expect(url).toBe("/api/practice-sessions/p1/attempts/2/pronunciation/issues/1/audio");
    expect(opts.headers.Authorization).toBe("Bearer tok_test");
    expect(result).toBe(clip);
  });

  it("分享请求使用公开片段路径", async () => {
    const clip = new Blob(["clip"], { type: "audio/wav" });
    fetchMock.mockResolvedValue({ ok: true, blob: () => Promise.resolve(clip) });

    const result = await api.getSharedPronunciationClip("tok_abc", 0, 2);

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/share/tok_abc/attempts/0/pronunciation/issues/2/audio",
    );
    expect(result).toBe(clip);
  });
});
