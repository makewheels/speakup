const BASE = "/api";
const DEFAULT_TIMEOUT = 90_000; // 90s，留足 AI 推理时间
const USER_STORAGE_KEY = "english-speak-user";
const UNAUTHORIZED_EVENT = "speakup:unauthorized";

function authHeaders() {
  try {
    const user = JSON.parse(localStorage.getItem(USER_STORAGE_KEY) || "null");
    return user?.token ? { Authorization: `Bearer ${user.token}` } : {};
  } catch {
    return {};
  }
}

function clearStoredUserOnUnauthorized(status) {
  if (status === 401) {
    try {
      localStorage.removeItem(USER_STORAGE_KEY);
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    } catch {
      // localStorage may be unavailable in tests or private browsing.
    }
  }
}

async function request(path, options = {}) {
  const { timeout = DEFAULT_TIMEOUT, ...fetchOpts } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const res = await fetch(`${BASE}${path}`, {
      ...fetchOpts,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(fetchOpts.headers || {}),
      },
      body: fetchOpts.body ? JSON.stringify(fetchOpts.body) : undefined,
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      clearStoredUserOnUnauthorized(res.status);
      throw new Error(err.detail || err.error || "Request failed");
    }
    return res.json();
  } catch (e) {
    if (e.name === "AbortError") {
      throw new Error("请求超时，请重试", { cause: e });
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
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(data),
        signal: controller.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        clearStoredUserOnUnauthorized(res.status);
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
            else if (event.type === "done") onDone?.({ result: event.result, autoSaved: event.autoSaved, round: event.round });
            else if (event.type === "error") onError?.(new Error(event.message));
          } catch {
            // 忽略不完整或非 JSON 的 SSE 片段，等待下一帧继续解析。
          }
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

/**
 * 追问对话流式（基于本次练习反馈继续问 AI）。SSE 纯文本。
 * data: { userId, practiceId, attemptIndex?, question }
 * handlers: { onChunk(text), onDone({text}), onError(err) }
 * 返回 AbortController。
 */
export function chatStream(data, { onChunk, onDone, onError } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120_000);

  (async () => {
    try {
      const res = await fetch(`${BASE}/correct/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(data),
        signal: controller.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        clearStoredUserOnUnauthorized(res.status);
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
            else if (event.type === "done") onDone?.({ text: event.text });
            else if (event.type === "error") onError?.(new Error(event.message));
          } catch {
            // 忽略不完整或非 JSON 的 SSE 片段，等待下一帧继续解析。
          }
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

  nextScenario: (userId, exclude = [], prefs = {}) => {
    const params = new URLSearchParams({ userId });
    for (const id of exclude) params.append("exclude", id);
    if (prefs?.level) params.set("level", prefs.level);
    if (prefs?.purpose) params.set("purpose", prefs.purpose);
    return request(`/scenarios/next?${params}`);
  },

  // 错题本「练这个词」：针对单个表达即时出题，返回 { scenarioId }（含图片生成，较慢）
  practiceWord: (userId, expression, original = "") =>
    request("/scenarios/practice-word", {
      method: "POST",
      body: { userId, expression, original },
      timeout: 60_000,
    }),

  createPractice: (data) => request("/practice-sessions", { method: "POST", body: data }),
  getPractice: (id) => request(`/practice-sessions/${id}`),
  listPractices: (userId, skip = 0) => request(`/practice-sessions?userId=${userId}&skip=${skip}`),

  // 分享
  sharePractice: (pid, userId) =>
    request(`/practice-sessions/${pid}/share`, { method: "POST", body: { userId } }),
  unsharePractice: (pid, userId) =>
    request(`/practice-sessions/${pid}/share?userId=${userId}`, { method: "DELETE" }),
  getSharedSession: (token) => request(`/share/${token}`),
  listShared: (userId) => request(`/practice-sessions?userId=${userId}&sharedOnly=true`),

  correct: (data) => request("/correct", { method: "POST", body: data }),

  tts: (text, practiceId) => request("/tts", { method: "POST", body: { text, practiceId } }).then((r) => r.url),

  uploadRecording: (practiceId, userId, blob, attemptIndex = -1) => {
    const form = new FormData();
    form.append("userId", userId);
    form.append("attemptIndex", attemptIndex);
    form.append("audio", blob, "recording.webm");
    return fetch(`${BASE}/practice-sessions/${practiceId}/recording`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    }).then((r) => {
      clearStoredUserOnUnauthorized(r.status);
      return r.ok ? r.json() : Promise.reject(new Error("录音上传失败"));
    });
  },

  // 全平台统一：录音上传 → 后端火山 openspeech ASR 返文本
  transcribeAudio: (userId, blob, practiceId) => {
    const form = new FormData();
    form.append("userId", userId);
    if (practiceId) form.append("practiceId", practiceId);
    const ext = (blob.type.includes("mp4") ? "m4a"
              : blob.type.includes("ogg") ? "ogg"
              : blob.type.includes("wav") ? "wav"
              : "webm");
    form.append("audio", blob, `recording.${ext}`);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90_000);
    return fetch(`${BASE}/transcribe`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
      signal: controller.signal,
    })
      .then(async (r) => {
        clearTimeout(timer);
        if (!r.ok) {
          clearStoredUserOnUnauthorized(r.status);
          // 502/503 多半是服务重启窗口；把状态码带出来，别再吞成空文案
          if (r.status === 502 || r.status === 503) {
            throw new Error(`服务正在重启，请稍后重试（HTTP ${r.status}）`);
          }
          const body = await r.text().catch(() => "");
          const detail = (() => {
            try { return JSON.parse(body).detail || ""; } catch { return body.slice(0, 120); }
          })();
          throw new Error(detail || `识别失败（HTTP ${r.status}）`);
        }
        return r.json();
      })
      .catch((e) => {
        clearTimeout(timer);
        if (e.name === "AbortError") throw new Error("识别超时（90s），请重试");
        throw e;
      });
  },

  addReviewItems: (userId, items) =>
    request("/review-items", { method: "POST", body: { userId, items } }),
  listReviewItems: (userId, due = false) =>
    request(`/review-items?userId=${userId}&due=${due}`),
  reviewItem: (id, userId, remembered) =>
    request(`/review-items/${id}/review?userId=${userId}`, { method: "POST", body: { remembered } }),
  deleteReviewItem: (id, userId) =>
    request(`/review-items/${id}?userId=${userId}`, { method: "DELETE" }),
};
