import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import useResultShare from "./useResultShare.js";

vi.mock("../api/client.js", () => ({
  api: {
    sharePractice: vi.fn(),
    unsharePractice: vi.fn(),
  },
}));

vi.mock("../lib/share.js", () => ({
  shareOrCopy: vi.fn(),
}));

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
    result: { score: 6.0 },
    round: 1,
    session,
    setSession,
    t,
    userId: "user_1",
  }));
  return { ...hook, currentSession: () => currentSession, setSession };
}

describe("useResultShare rollback", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../api/client.js");
    const { shareOrCopy } = await import("../lib/share.js");
    api.sharePractice.mockResolvedValue({ shareToken: "new_token" });
    api.unsharePractice.mockResolvedValue({ ok: true });
    shareOrCopy.mockResolvedValue("cancelled");
  });

  it("turns off a newly enabled public link when system share is cancelled", async () => {
    const { api } = await import("../api/client.js");
    const hook = setupHook();

    await act(() => hook.result.current.shareResult());

    expect(api.sharePractice).toHaveBeenCalledWith("practice_1", "user_1");
    expect(api.unsharePractice).toHaveBeenCalledWith("practice_1", "user_1");
    expect(hook.currentSession()).toMatchObject({ shared: false, shareToken: "new_token" });
    expect(hook.result.current.shareStatus).toBe("practice.resultShareCancelledRolledBack");
  });

  it("does not turn off a link that was already public when system share is cancelled", async () => {
    const { api } = await import("../api/client.js");
    const hook = setupHook({ ...BASE_SESSION, shared: true, shareToken: "existing_token" });

    await act(() => hook.result.current.shareResult());

    expect(api.sharePractice).not.toHaveBeenCalled();
    expect(api.unsharePractice).not.toHaveBeenCalled();
    expect(hook.result.current.shareStatus).toBe("practice.resultShareCancelled");
  });

  it("rolls back a newly enabled link when share and copy fail", async () => {
    const { api } = await import("../api/client.js");
    const { shareOrCopy } = await import("../lib/share.js");
    shareOrCopy.mockRejectedValue(new Error("clipboard blocked"));
    const hook = setupHook();

    await act(() => hook.result.current.shareResult());

    expect(api.unsharePractice).toHaveBeenCalledWith("practice_1", "user_1");
    expect(hook.currentSession()).toMatchObject({ shared: false, shareToken: "new_token" });
    expect(hook.result.current.shareStatus).toBe("practice.resultShareFailedRolledBack");
    expect(t).toHaveBeenCalledWith(
      "practice.resultShareFailedRolledBack",
      { msg: "clipboard blocked" },
    );
  });

  it("shows an explicit warning when the new public link cannot be rolled back", async () => {
    const { api } = await import("../api/client.js");
    api.unsharePractice.mockRejectedValue(new Error("rollback offline"));
    const hook = setupHook();

    await act(() => hook.result.current.shareResult());

    expect(hook.currentSession()).toMatchObject({ shared: true, shareToken: "new_token" });
    expect(hook.result.current.shareStatus).toBe("practice.resultShareCancelRollbackFailed");
    expect(t).toHaveBeenCalledWith(
      "practice.resultShareCancelRollbackFailed",
      expect.objectContaining({ rollbackMsg: "rollback offline" }),
    );
  });
});
