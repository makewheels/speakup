const BASE = "/api";
const DEFAULT_TIMEOUT = 90_000; // 90s，留足 AI 推理时间

async function request(path, options = {}) {
  const { timeout = DEFAULT_TIMEOUT, ...fetchOpts } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...fetchOpts,
      body: fetchOpts.body ? JSON.stringify(fetchOpts.body) : undefined,
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Request failed");
    }
    return res.json();
  } catch (e) {
    if (e.name === "AbortError") {
      throw new Error("请求超时，请重试");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 流式 AI 评估。使用 SSE（fetch + ReadableStream）。
 * handlers: { onChunk(text), onDone({result, autoSaved}), onError(err) }
 * 返回 AbortController，调用方可 .abort() 取消。
 */
export function correctStream(data, { onChunk, onDone, onError } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120_000);

  (async () => {
    try {
      const res = await fetch(`${BASE}/correct/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
        signal: controller.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || "请求失败");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(part.slice(6));
            if (event.type === "chunk") onChunk?.(event.text);
            else if (event.type === "done") onDone?.({ result: event.result, autoSaved: event.autoSaved });
            else if (event.type === "error") onError?.(new Error(event.message));
          } catch {}
        }
      }
    } catch (e) {
      if (e.name === "AbortError") onError?.(new Error("请求超时，请重试"));
      else onError?.(e);
    } finally {
      clearTimeout(timer);
    }
  })();

  return controller;
}

export const api = {
  login: (phone) => request("/auth/login", { method: "POST", body: { phone } }),

  nextImage: () => request("/generate/next", { method: "POST" }),

  createSession: (data) => request("/sessions", { method: "POST", body: data }),
  getSession: (id) => request(`/sessions/${id}`),
  listSessions: (userId, skip = 0) => request(`/sessions?userId=${userId}&skip=${skip}`),

  correct: (data) => request("/correct", { method: "POST", body: data }),

  addVocabulary: (userId, words) =>
    request("/vocabulary", { method: "POST", body: { userId, words } }),
  listVocabulary: (userId, due = false) =>
    request(`/vocabulary?userId=${userId}&due=${due}`),
  reviewWord: (id, userId, remembered) =>
    request(`/vocabulary/${id}/review?userId=${userId}`, { method: "POST", body: { remembered } }),
  deleteWord: (id, userId) =>
    request(`/vocabulary/${id}?userId=${userId}`, { method: "DELETE" }),
};
