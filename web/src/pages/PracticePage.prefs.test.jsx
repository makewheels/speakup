import { screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  USER,
  SCENARIO_B,
  PREFS,
  setup,
  installMediaStubs,
} from "./PracticePage.feedback.helpers.jsx";
import { getPracticePreferences } from "../lib/practicePreferences.js";

vi.mock("../api/client.js", () => ({
  api: {
    nextScenario: vi.fn(),
    nextFreeTopic: vi.fn(),
    createPractice: vi.fn(),
    getPractice: vi.fn(),
    transcribeAudio: vi.fn(),
    uploadRecording: vi.fn(),
    addReviewItems: vi.fn(),
    deleteReviewItem: vi.fn(),
    tts: vi.fn(),
    getPracticePreferences: vi.fn().mockRejectedValue(new Error("offline")),
    savePracticePreferences: vi.fn().mockResolvedValue({}),
  },
  correctStream: vi.fn(),
  chatStream: vi.fn(),
}));

vi.mock("../utils/tts.js", () => ({
  speak: vi.fn().mockResolvedValue(null),
  stop: vi.fn(),
  isCached: vi.fn().mockReturnValue(false),
}));

describe("PracticePage 练习偏好服务端化", () => {
  beforeEach(async () => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    const { api } = await import("../api/client.js");
    api.nextScenario.mockResolvedValue(SCENARIO_B);
    api.nextFreeTopic.mockResolvedValue({ _id: "ft_1", text: "A topic", zh: "话题" });
    api.createPractice.mockResolvedValue({ _id: "sess_xyz" });
    api.getPractice.mockResolvedValue({});
    // 恢复工厂默认（clearAllMocks 会清掉实现）
    api.getPracticePreferences.mockRejectedValue(new Error("offline"));
    api.savePracticePreferences.mockResolvedValue({});
    installMediaStubs();
  });

  it("服务端有偏好时直接使用：不出选择题，本地缓存同步为服务端值", async () => {
    const { api } = await import("../api/client.js");
    api.getPracticePreferences.mockResolvedValue({ level: "advanced", purpose: "work" });

    setup("/practice", { prefs: false });

    await waitFor(() =>
      expect(api.nextScenario).toHaveBeenCalledWith(
        USER.userId,
        [],
        { level: "advanced", purpose: "work" },
      ),
    );
    expect(screen.queryByText("What do you want to practice?")).not.toBeInTheDocument();
    expect(getPracticePreferences(USER.userId)).toEqual({ level: "advanced", purpose: "work" });
  });

  it("服务端没有而本地有（旧版浏览器设置）：自动迁移到服务端", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice");

    await waitFor(() =>
      expect(api.savePracticePreferences).toHaveBeenCalledWith({
        userId: USER.userId,
        level: PREFS.level,
        purpose: PREFS.purpose,
      }),
    );
    await waitFor(() => expect(api.nextScenario).toHaveBeenCalledWith(USER.userId, [], PREFS));
  });

  it("服务端和本地都没有：显示首次选择题，不抽题", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice", { prefs: false });

    await waitFor(() =>
      expect(screen.getByText("What do you want to practice?")).toBeInTheDocument(),
    );
    expect(api.nextScenario).not.toHaveBeenCalled();
  });
});
