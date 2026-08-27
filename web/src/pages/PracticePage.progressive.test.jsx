import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { setup, installMediaStubs, USER } from "./PracticePage.feedback.helpers.jsx";

vi.mock("../api/client.js", () => ({
  api: {
    // 偏好对账默认走"服务端未设置/离线"：使用本地缓存路径（与生产降级一致）
    getPracticePreferences: vi.fn().mockRejectedValue(new Error("offline")),
    savePracticePreferences: vi.fn().mockResolvedValue({}),
    nextScenario: vi.fn(),
    scenarioBySlug: vi.fn(),
    createPractice: vi.fn(),
    getPractice: vi.fn(),
    revealNextHint: vi.fn(),
    transcribeAudio: vi.fn(),
    uploadRecording: vi.fn(),
    addReviewItems: vi.fn(),
    deleteReviewItem: vi.fn(),
    tts: vi.fn(),
  },
  correctStream: vi.fn(),
  chatStream: vi.fn(),
}));

vi.mock("../utils/tts.js", () => ({
  speak: vi.fn().mockResolvedValue(null),
  stop: vi.fn(),
  isCached: vi.fn().mockReturnValue(false),
}));

// by-slug 响应：与 /next 同形 + 归一化 interactionType/hints/difficulty
const PROGRESSIVE_SCENARIO = {
  scenarioId: "sc_prog",
  kind: "task",
  title: "咖啡店重做饮品",
  where: "咖啡店 · 西雅图",
  story: "店员把你的热拿铁做成了冰拿铁。",
  mission: "礼貌说明问题，请店员重做。",
  points: ["说明饮品做错了", "要求重做一杯热的"],
  imageUrl: "",
  videoUrl: "",
  isCustom: false,
  preferenceMatch: "exact",
  targetWords: [],
  difficulty: 2,
  interactionType: "progressive_hints",
  hints: ["我点的是热拿铁，但这杯是冰的。", "能麻烦你重新做一杯热的吗？"],
};

const PROGRESSIVE_SESSION = {
  _id: "sess_prog",
  userId: USER.userId,
  scenarioId: "sc_prog",
  mode: "scenario",
  sourceType: "human",
  title: "咖啡店重做饮品",
  topic: "咖啡店 · 西雅图",
  scenario: {
    kind: "task",
    title: "咖啡店重做饮品",
    where: "咖啡店 · 西雅图",
    story: "店员把你的热拿铁做成了冰拿铁。",
    mission: "礼貌说明问题，请店员重做。",
    points: ["说明饮品做错了", "要求重做一杯热的"],
    targetWords: [],
    interactionType: "progressive_hints",
    hints: ["我点的是热拿铁，但这杯是冰的。", "能麻烦你重新做一杯热的吗？"],
    difficulty: 2,
  },
  revealedHintCount: 0,
  attempts: [],
};

describe("PracticePage 渐进式提示 / 指定题目 URL", () => {
  beforeEach(async () => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    const { api } = await import("../api/client.js");
    api.scenarioBySlug.mockResolvedValue(PROGRESSIVE_SCENARIO);
    api.createPractice.mockResolvedValue(PROGRESSIVE_SESSION);
    api.getPractice.mockResolvedValue(PROGRESSIVE_SESSION);
    api.revealNextHint.mockResolvedValue({
      requestId: "r1", revealedHintCount: 1, hintIndex: 0,
      hint: "我点的是热拿铁，但这杯是冰的。", exhausted: false,
    });
    api.transcribeAudio.mockResolvedValue({ text: "My latte is iced" });
    api.uploadRecording.mockResolvedValue({});
    installMediaStubs();
  });

  it("指定 URL 精确取题：展示 mission、隐藏 points，会话创建前无提示按钮", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice?scenario=prog-coffee-remake");
    await waitFor(() => expect(api.scenarioBySlug).toHaveBeenCalledWith("prog-coffee-remake"));
    await waitFor(() =>
      expect(screen.getByText("店员把你的热拿铁做成了冰拿铁。")).toBeInTheDocument(),
    );
    expect(screen.getByText("礼貌说明问题，请店员重做。")).toBeInTheDocument();
    expect(screen.queryByText("说明饮品做错了")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Give me a hint" })).not.toBeInTheDocument();
    expect(api.createPractice).not.toHaveBeenCalled();
  });

  it("开始动作创建会话并逐条领取提示，用尽后不再显示按钮", async () => {
    const { api } = await import("../api/client.js");
    api.revealNextHint
      .mockResolvedValueOnce({
        requestId: "r1", revealedHintCount: 1, hintIndex: 0,
        hint: "我点的是热拿铁，但这杯是冰的。", exhausted: false,
      })
      .mockResolvedValueOnce({
        requestId: "r2", revealedHintCount: 2, hintIndex: 1,
        hint: "能麻烦你重新做一杯热的吗？", exhausted: true,
      });
    setup("/practice?scenario=prog-coffee-remake");
    await waitFor(() =>
      expect(screen.getByText("礼貌说明问题，请店员重做。")).toBeInTheDocument(),
    );

    await userEvent.click(document.querySelector(".su-rec"));
    await waitFor(() =>
      expect(api.createPractice).toHaveBeenCalledWith(expect.objectContaining({
        userId: USER.userId,
        scenarioId: "sc_prog",
        requestId: expect.any(String),
      })),
    );

    const first = await screen.findByRole("button", { name: "Give me a hint" });
    await userEvent.click(first);
    await waitFor(() =>
      expect(screen.getByText("我点的是热拿铁，但这杯是冰的。")).toBeInTheDocument(),
    );
    expect(screen.queryByText("能麻烦你重新做一杯热的吗？")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Give me another hint" }));
    await waitFor(() =>
      expect(screen.getByText("能麻烦你重新做一杯热的吗？")).toBeInTheDocument(),
    );
    expect(screen.getByText("All hints shown")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Give me another hint" })).not.toBeInTheDocument();
    expect(api.revealNextHint).toHaveBeenCalledTimes(2);
  });

  it("刷新后按服务端计数恢复已显示提示前缀", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({ ...PROGRESSIVE_SESSION, revealedHintCount: 1 });
    setup("/practice/sess_prog");
    await waitFor(() =>
      expect(screen.getByText("我点的是热拿铁，但这杯是冰的。")).toBeInTheDocument(),
    );
    expect(screen.queryByText("能麻烦你重新做一杯热的吗？")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Give me another hint" })).toBeInTheDocument();
  });

  it("不可用 slug：明确错误提示，不创建会话", async () => {
    const { api } = await import("../api/client.js");
    api.scenarioBySlug.mockRejectedValue(new Error("场景不存在或不可用"));
    setup("/practice?scenario=no-such");
    await waitFor(() =>
      expect(screen.getByText("This scenario is not available.")).toBeInTheDocument(),
    );
    expect(api.createPractice).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Back to practice" })).toBeInTheDocument();
  });

  it("standard 会话不出现提示按钮", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...PROGRESSIVE_SESSION,
      scenario: { ...PROGRESSIVE_SESSION.scenario, interactionType: "standard", hints: [] },
    });
    setup("/practice/sess_prog");
    await waitFor(() =>
      expect(screen.getByText("店员把你的热拿铁做成了冰拿铁。")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: "Give me a hint" })).not.toBeInTheDocument();
  });
});
