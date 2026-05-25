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
