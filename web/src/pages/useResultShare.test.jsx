import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import useResultShare from "./useResultShare.js";

vi.mock("../api/client.js", () => ({ api: { sharePractice: vi.fn() } }));

const BASE_SESSION = {
  _id: "practice_1",
  title: "Coffee shop",
  attempts: [{ score: 6.0 }],
};
const t = vi.fn((key) => key);

function setupHook(session = BASE_SESSION) {
  let currentSession = session;
  const setSession = vi.fn((updater) => {
    currentSession = typeof updater === "function" ? updater(currentSession) : updater;
  });
  const hook = renderHook(() => useResultShare({
    session,
    setSession,
    t,
    userId: "user_1",
  }));
  return { ...hook, currentSession: () => currentSession };
}

describe("useResultShare", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    vi.stubGlobal("window", { location: { origin: "https://speak.example" } });
    const { api } = await import("../api/client.js");
    api.sharePractice.mockResolvedValue({ shareToken: "new_token" });
  });

  it("creates a link without opening the system share sheet or copying automatically", async () => {
    const systemShare = vi.fn();
    const writeText = vi.fn();
    vi.stubGlobal("navigator", { share: systemShare, clipboard: { writeText } });
    const { api } = await import("../api/client.js");
    const hook = setupHook();

    await act(() => hook.result.current.shareResult("pa_1"));

    expect(api.sharePractice).toHaveBeenCalledWith("practice_1", "user_1");
    expect(hook.result.current.shareLink).toBe("https://speak.example/s/new_token?attempt=pa_1");
    expect(hook.currentSession()).toMatchObject({ shared: true, shareToken: "new_token" });
    expect(systemShare).not.toHaveBeenCalled();
    expect(writeText).not.toHaveBeenCalled();
  });

  it("reuses an existing token and copies only after the user asks", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { share: vi.fn(), clipboard: { writeText } });
    const { api } = await import("../api/client.js");
    const hook = setupHook({ ...BASE_SESSION, shared: true, shareToken: "existing_token" });

    await act(() => hook.result.current.shareResult());
    expect(api.sharePractice).not.toHaveBeenCalled();
    await act(() => hook.result.current.copyShareLink());

    expect(writeText).toHaveBeenCalledWith("https://speak.example/s/existing_token");
    expect(hook.result.current.shareStatus).toBe("practice.resultLinkCopied");
  });

  it("closes the popover without disabling the public link", async () => {
    const hook = setupHook();
    await act(() => hook.result.current.shareResult());
    act(() => hook.result.current.closeShareLink());
    expect(hook.result.current.shareLink).toBe("");
    expect(hook.currentSession()).toMatchObject({ shared: true, shareToken: "new_token" });
  });
});
