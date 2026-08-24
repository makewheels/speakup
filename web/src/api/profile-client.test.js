import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./client.js";

describe("profile API", () => {
  let fetchMock;

  beforeEach(() => {
    localStorage.setItem("english-speak-user", JSON.stringify({
      userId: "u1",
      token: "tok_test",
    }));
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ userId: "u1", nickname: "Mint Garden" }),
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("PATCHes the authenticated user's nickname", async () => {
    const response = await api.updateProfile("Mint Garden");
    const [url, options] = fetchMock.mock.calls[0];

    expect(response.nickname).toBe("Mint Garden");
    expect(url).toBe("/api/auth/profile");
    expect(options.method).toBe("PATCH");
    expect(options.headers.Authorization).toBe("Bearer tok_test");
    expect(options.body).toBe(JSON.stringify({ nickname: "Mint Garden" }));
  });
});
