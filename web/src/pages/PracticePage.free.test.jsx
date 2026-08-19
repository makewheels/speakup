import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import {
  USER,
  SESSION,
  SCENARIO_B,
  setup,
  installMediaStubs,
  recordUntilEvaluating,
} from "./PracticePage.feedback.helpers.jsx";

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
    submitFeedback: vi.fn(),
    listMyFeedbacks: vi.fn(),
  },
  correctStream: vi.fn(),
  chatStream: vi.fn(),
}));

vi.mock("../utils/tts.js", () => ({
  speak: vi.fn().mockResolvedValue(null),
  stop: vi.fn(),
  isCached: vi.fn().mockReturnValue(false),
}));

const FREE_TOPIC = { _id: "ft_1", text: "Your favorite breakfast", zh: "你最喜欢的早餐" };

const FREE_SESSION = {
  ...SESSION,
  _id: "sess_free",
  scenarioId: "",
  mode: "free",
  freeTopicId: "ft_1",
  freeTopic: "Your favorite breakfast",
  title: "Your favorite breakfast",
  topic: "",
  imageUrl: "",
  videoUrl: "",
  scenario: {
    kind: "free",
    title: "Your favorite breakfast",
    freeTopic: "Your favorite breakfast",
    where: "",
    story: "",
    mission: "",
    points: [],
    targetWords: [],
  },
};

describe("PracticePage 自由说模式", () => {
  beforeEach(async () => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    const { api } = await import("../api/client.js");
    api.nextScenario.mockResolvedValue(SCENARIO_B);
    api.nextFreeTopic.mockResolvedValue(FREE_TOPIC);
    api.createPractice.mockResolvedValue(FREE_SESSION);
    api.getPractice.mockResolvedValue(FREE_SESSION);
    api.transcribeAudio.mockResolvedValue({ text: "I like egg and bread" });
    api.uploadRecording.mockResolvedValue({});
    api.addReviewItems.mockResolvedValue({ ids: ["rv_1"] });
    api.deleteReviewItem.mockResolvedValue({});
    api.submitFeedback.mockResolvedValue({});
    api.listMyFeedbacks.mockResolvedValue([]);
    installMediaStubs();
  });

  it("shows the mode switch and fetches a topic when entering free mode via URL", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice?mode=free");
    await waitFor(() => expect(api.nextFreeTopic).toHaveBeenCalledWith(USER.userId));
    // 话题卡（英文话题 + 中文释义）
    await waitFor(() =>
      expect(screen.getByText("Your favorite breakfast")).toBeInTheDocument(),
    );
    expect(screen.getByText("你最喜欢的早餐")).toBeInTheDocument();
    // 「不用题目，随便说」入口 + 换一个话题
    expect(screen.getByText("No topic, just talk")).toBeInTheDocument();
    expect(screen.getByText("Try another topic")).toBeInTheDocument();
    // 场景题不抽题
    expect(api.nextScenario).not.toHaveBeenCalled();
  });

  it("switching from scenario to free mode fetches a topic instead of a scenario", async () => {
    const { api } = await import("../api/client.js");
    // helpers 默认 getPractice 返回自由说会话，这里显式换回场景会话
    api.getPractice.mockResolvedValue(SESSION);
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("You got the wrong drink."));
    expect(api.nextFreeTopic).not.toHaveBeenCalled();

    await userEvent.click(screen.getByText("Free talk"));

    await waitFor(() => expect(api.nextFreeTopic).toHaveBeenCalledWith(USER.userId));
    await waitFor(() =>
      expect(screen.getByText("Your favorite breakfast")).toBeInTheDocument(),
    );
  });

  it("tapping record in free mode creates a session with mode/freeTopic before recording", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice?mode=free");
    await waitFor(() => screen.getByText("Your favorite breakfast"));

    await userEvent.click(document.querySelector(".su-rec"));

    await waitFor(() =>
      expect(api.createPractice).toHaveBeenCalledWith({
        userId: USER.userId,
        mode: "free",
        freeTopicId: "ft_1",
        freeTopic: "Your favorite breakfast",
      }),
    );
    await waitFor(() => expect(screen.getByText("Tap once to stop")).toBeInTheDocument());
  });

  it("no-topic button creates a session without topic and starts recording", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice?mode=free");
    await waitFor(() => screen.getByText("Your favorite breakfast"));

    await userEvent.click(screen.getByText("No topic, just talk"));

    await waitFor(() =>
      expect(api.createPractice).toHaveBeenCalledWith({
        userId: USER.userId,
        mode: "free",
        freeTopicId: "",
        freeTopic: "",
      }),
    );
    await waitFor(() => expect(screen.getByText("Tap once to stop")).toBeInTheDocument());
  });

  it("evaluation in free mode passes mode=free and the topic to correct stream", async () => {
    const { api, correctStream } = await import("../api/client.js");
    setup("/practice?mode=free");
    await waitFor(() => screen.getByText("Your favorite breakfast"));
    await recordUntilEvaluating();

    expect(api.transcribeAudio).toHaveBeenCalledWith(USER.userId, expect.any(Object), "sess_free");
    expect(correctStream).toHaveBeenCalledWith(
      expect.objectContaining({
        practiceId: "sess_free",
        mode: "free",
        freeTopic: "Your favorite breakfast",
      }),
      expect.any(Object),
    );
  });

  it("feedback view in free mode offers Next topic", async () => {
    const { api, correctStream } = await import("../api/client.js");
    setup("/practice?mode=free");
    await waitFor(() => screen.getByText("Your favorite breakfast"));
    await recordUntilEvaluating();
    const onDone = correctStream.mock.calls[0][1].onDone;
    await act(async () => {
      onDone({
        result: {
          summary: "不错", nativeVersion: "I like eggs and bread.", standardAnswer: "",
          gaps: [], score: 6.0, progress: null, note: "", noteChinese: "",
        },
        autoSaved: 0,
        round: 1,
      });
    });
    // 自由说结果页：「下一个话题」按钮（不抽场景题）
    await waitFor(() => expect(screen.getByText("Next topic")).toBeInTheDocument());
    expect(screen.getByText("I like eggs and bread.")).toBeInTheDocument();
    expect(api.nextScenario).not.toHaveBeenCalled();
  });

  it("reloads a free session from URL without re-fetching a topic", async () => {
    setup("/practice/sess_free");
    await waitFor(() =>
      expect(screen.getByText("Your favorite breakfast")).toBeInTheDocument(),
    );
    // 刷新还原后不重复抽题（话题来自会话快照）
    const { api } = await import("../api/client.js");
    expect(api.nextFreeTopic).not.toHaveBeenCalled();
  });
});
