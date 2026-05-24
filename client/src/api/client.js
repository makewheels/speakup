const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || "Request failed");
  }
  return res.json();
}

export const api = {
  // Auth
  login: (phone) => request("/auth/login", { method: "POST", body: { phone } }),

  // Image generation (with cache)
  nextImage: (userId) => request("/generate/next", { method: "POST", body: { userId } }),
  prefetchImage: (userId) => request("/generate/prefetch", { method: "POST", body: { userId } }),

  // Sessions
  createSession: (data) => request("/sessions", { method: "POST", body: data }),
  getSession: (id) => request(`/sessions/${id}`),
  listSessions: (userId, skip = 0) => request(`/sessions?userId=${userId}&skip=${skip}`),

  // Correction
  correct: (data) => request("/correct", { method: "POST", body: data }),

  // Vocabulary
  addVocabulary: (userId, words) =>
    request("/vocabulary", { method: "POST", body: { userId, words } }),
  listVocabulary: (userId, due = false) =>
    request(`/vocabulary?userId=${userId}&due=${due}`),
  reviewWord: (id, remembered) =>
    request(`/vocabulary/${id}/review`, { method: "POST", body: { remembered } }),
  deleteWord: (id) => request(`/vocabulary/${id}`, { method: "DELETE" }),
};
