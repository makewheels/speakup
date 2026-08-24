import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  USER,
  SESSION,
  SCENARIO_B,
  SESSION_B,
  PREFS,
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
    sharePractice: vi.fn(),
    unsharePractice: vi.fn(),
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

describe("PracticePage feedback", () => {
  beforeEach(async () => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    const { api } = await import("../api/client.js");
    api.nextScenario.mockResolvedValue(SCENARIO_B);
    api.createPractice.mockResolvedValue(SESSION_B);
    api.getPractice.mockResolvedValue(SESSION);
    api.transcribeAudio.mockResolvedValue({ text: "Can you redo my latte" });
    api.uploadRecording.mockResolvedValue({});
    api.addReviewItems.mockResolvedValue({ ids: ["rv_1"] });
    api.deleteReviewItem.mockResolvedValue({});
    api.sharePractice.mockResolvedValue({ shareToken: "tok_result" });
    api.unsharePractice.mockResolvedValue({ ok: true });
    api.submitFeedback.mockResolvedValue({});
    api.listMyFeedbacks.mockResolvedValue([]);
    installMediaStubs();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("restores the feedback view from the latest attempt when URL has ?result=1", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        {
          _id: "pa_test_1",
          attemptId: "pa_test_1",
          round: 1,
          transcript: "Can you redo my latte",
          summary: "整体不错，请求可以更自然",
          standardAnswer: "Excuse me, could you remake my latte? I'm in a bit of a rush.",
          score: 6.5,
          gaps: [],
          progress: null,
        },
      ],
    });
    setup("/practice/sess_abc?result=1");
    await waitFor(() => expect(screen.getByText("Standard answer")).toBeInTheDocument());
    expect(screen.queryByText("Correction")).not.toBeInTheDocument();
    expect(screen.getByText("I'm in a bit of a rush.")).toBeInTheDocument();
  });

  it("结果页只在首帧滚到顶部，并按题目在前、分数在后的稳定顺序展示", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        {
          _id: "pa_test_1",
          attemptId: "pa_test_1",
          round: 1,
          transcript: "Can you redo my latte",
          summary: "整体不错",
          nativeVersion: "Could you remake my latte?",
          score: 6.5,
          gaps: [],
          progress: null,
        },
      ],
    });
    const scrollSpy = vi.fn();
    const originalScrollTo = window.scrollTo;
    window.scrollTo = scrollSpy;
    try {
      setup("/practice/sess_abc?result=1");
      await waitFor(() => expect(screen.getByText("6.5")).toBeInTheDocument());
      const anchor = document.querySelector(".fb-score-anchor");
      const resultPage = document.querySelector(".fb-page");
      const scenarioCard = document.querySelector(".fb-page .sc-card");
      expect(anchor).toBeTruthy();
      expect(scenarioCard).toBeTruthy();
      expect(anchor.querySelector(".fb-score")).toBeTruthy();
      expect(resultPage.firstElementChild).not.toBe(anchor);
      expect(scenarioCard.compareDocumentPosition(anchor) & Node.DOCUMENT_POSITION_FOLLOWING)
        .toBeTruthy();
      expect(scrollSpy).toHaveBeenCalledTimes(1);
    } finally {
      window.scrollTo = originalScrollTo;
    }
  });

  it("追问：发送问题后流式回答渲染、并以本练习上下文调用 chatStream", async () => {
    const { api, chatStream } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        {
          round: 1,
          transcript: "Can you redo my latte",
          summary: "整体不错",
          nativeVersion: "Could you remake my latte?",
          score: 6.5,
          gaps: [],
          progress: null,
          chat: [],
        },
      ],
    });
    chatStream.mockImplementation((_data, { onChunk, onDone }) => {
      onChunk("native ");
      onChunk("更自然。");
      onDone?.({ text: "native 更自然。" });
      return { abort: vi.fn() };
    });

    setup("/practice/sess_abc?result=1");
    await waitFor(() => expect(screen.getByText("Ask the coach")).toBeInTheDocument());

    const box = screen.getByPlaceholderText(/Ask about this feedback/);
    await userEvent.type(box, "为什么这么改？");
    await userEvent.keyboard("{Enter}");

    expect(chatStream).toHaveBeenCalledWith(
      expect.objectContaining({ userId: USER.userId, practiceId: "sess_abc", question: "为什么这么改？" }),
      expect.any(Object),
    );
    await waitFor(() => expect(screen.getByText("native 更自然。")).toBeInTheDocument());
    expect(screen.getByText("为什么这么改？")).toBeInTheDocument();
  });

  it("evaluates and renders score, broader gap pairs, and the independent answer", async () => {
    const { api, correctStream } = await import("../api/client.js");
    correctStream.mockImplementation((data, { onStarted, onChunk, onDone }) => {
      onStarted({ attemptId: "pa_test_1", round: 1 });
      onChunk("partial ");
      onDone({
        attemptId: "pa_test_1",
        result: {
          summary: "good",
          standardAnswer: "Hi, my latte came out wrong — could you remake it? I'm in a bit of a rush.",
          score: 7.0,
          gaps: [{ original: "redo my latte", better: "remake my latte", why: "more natural" }],
          progress: null,
        },
        autoSaved: 1,
        round: 1,
      });
      return { abort: vi.fn() };
    });

    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    await recordUntilEvaluating();

    await waitFor(() => expect(screen.getByText("Expression feedback")).toBeInTheDocument());
    expect(correctStream).toHaveBeenCalledWith(
      expect.objectContaining({ userId: USER.userId, practiceId: "sess_abc", text: "Can you redo my latte" }),
      expect.any(Object),
    );
    expect(screen.getByText("7.0")).toBeInTheDocument();
    expect(screen.queryByText("Correction")).not.toBeInTheDocument();
    expect(screen.getByText("Standard answer")).toBeInTheDocument();
    expect(screen.getByText(/my latte came out wrong/)).toBeInTheDocument();
    expect(screen.getByText("remake my latte")).toBeInTheDocument();
    expect(screen.getByText("more natural")).toBeInTheDocument();
    expect(screen.queryByText(/added to Review/)).not.toBeInTheDocument();
    expect(screen.getByText(/Say it again/)).toBeInTheDocument();
    expect(api.nextScenario).not.toHaveBeenCalled();
    await waitFor(() => expect(api.uploadRecording).toHaveBeenCalled());
  });

  it("stays on review and alerts when AI returns no usable feedback", async () => {
    const { correctStream } = await import("../api/client.js");
    vi.spyOn(window, "alert").mockImplementation(() => {});
    correctStream.mockImplementation((_data, { onDone }) => {
      onDone({
        result: {
          summary: "AI feedback could not be parsed. Try again.",
          score: null,
          gaps: [],
          progress: null,
        },
        autoSaved: 0,
        round: 1,
      });
      return { abort: vi.fn() };
    });

    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    await recordUntilEvaluating();

    await waitFor(() =>
      expect(window.alert).toHaveBeenCalledWith(expect.stringContaining("Feedback request failed")),
    );
    expect(screen.getByText("Review now")).toBeInTheDocument();
    expect(screen.getByText("Can you redo my latte")).toBeInTheDocument();
    expect(screen.queryByText("AI did not return usable corrections. Try Review now again.")).not.toBeInTheDocument();
  });

  it("treats an independent standard-answer-only result as usable feedback", async () => {
    const { correctStream } = await import("../api/client.js");
    vi.spyOn(window, "alert").mockImplementation(() => {});
    correctStream.mockImplementation((_data, { onDone }) => {
      onDone({
        result: {
          summary: "Correction unavailable; independent answer is ready.",
          standardAnswer: "Excuse me, could you remake my latte, please?",
          score: null,
          gaps: [],
          progress: null,
        },
        autoSaved: 0,
        round: 1,
      });
      return { abort: vi.fn() };
    });

    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    await recordUntilEvaluating();

    await waitFor(() => expect(screen.getByText("Standard answer")).toBeInTheDocument());
    expect(screen.getByText("Excuse me, could you remake my latte, please?")).toBeInTheDocument();
    expect(screen.getByText("No specific correction this time.")).toBeInTheDocument();
    expect(screen.queryByText("AI did not return usable corrections. Try Review now again.")).not.toBeInTheDocument();
    expect(window.alert).not.toHaveBeenCalled();
  });

  it("renders progress block (passed verdict + fixed/remaining chips) in feedback", async () => {
    const { correctStream } = await import("../api/client.js");
    correctStream.mockImplementation((_data, { onDone }) => {
      onDone({
        result: {
          summary: "great",
          nativeVersion: "Could you remake my latte?",
          score: 8.0,
          gaps: [],
          progress: {
            verdict: "passed",
            comment: "Much better this time",
            fixed: ["hot latte"],
            remaining: ["in a hurry"],
          },
        },
        autoSaved: 0,
        round: 1,
      });
      return { abort: vi.fn() };
    });

    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    await recordUntilEvaluating();

    await waitFor(() => expect(screen.getByText("Sounded native this time ✓")).toBeInTheDocument());
    expect(screen.getByText("Much better this time")).toBeInTheDocument();
    expect(screen.getByText("hot latte")).toBeInTheDocument();
    expect(screen.getByText("in a hurry")).toBeInTheDocument();
    expect(screen.getByText(/Next scenario/)).toBeInTheDocument();
    // 重说不封顶：即使 passed，重试按钮也常驻；按钮不重复展示轮次。
    expect(screen.getByRole("button", { name: "Say it again" })).toBeInTheDocument();
  });

  it("keeps the user on feedback after a streamed second-round review", async () => {
    const { api, correctStream } = await import("../api/client.js");
    correctStream.mockImplementation((_data, { onDone }) => {
      onDone({
        result: {
          summary: "still needs practice",
          nativeVersion: "Could you remake my latte? I'm in a hurry.",
          score: 6.5,
          gaps: [],
          progress: { verdict: "needs-work" },
        },
        autoSaved: 0,
        round: 2,
      });
      return { abort: vi.fn() };
    });

    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    await recordUntilEvaluating();

    await waitFor(() => expect(screen.getByText("still needs practice")).toBeInTheDocument());
    // 不封顶：第 2 轮反馈后仍可继续重说；当前轮次只在页面徽章展示。
    expect(screen.getByText("Attempt #2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Say it again" })).toBeInTheDocument();
    expect(screen.getByText(/Next/)).toBeInTheDocument();
    expect(screen.queryByText(/Tap once to record/)).not.toBeInTheDocument();
    expect(api.nextScenario).not.toHaveBeenCalled();
  });

  it("shows the attempt badge on the question once it is a second try", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        { round: 1, transcript: "x", summary: "s", nativeVersion: "n", score: 5.5, gaps: [], progress: null },
      ],
    });
    // 无 ?result → 回到题目页准备第 2 次（round = attempts+1 = 2）
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    expect(screen.getByText("Attempt #2")).toBeInTheDocument();
  });

  it("returns to review phase and alerts when correctStream errors", async () => {
    const { correctStream } = await import("../api/client.js");
    vi.spyOn(window, "alert").mockImplementation(() => {});
    correctStream.mockImplementation((_data, { onError }) => {
      onError(new Error("boom"));
      return { abort: vi.fn() };
    });

    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    await recordUntilEvaluating();

    await waitFor(() =>
      expect(window.alert).toHaveBeenCalledWith(expect.stringContaining("Feedback request failed")),
    );
    expect(screen.getByText("Review now")).toBeInTheDocument();
  });

  it("'Say it again' keeps the session and shows hint bar from prior gaps", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        {
          round: 1,
          transcript: "Can you redo my latte",
          summary: "ok",
          nativeVersion: "Could you remake my latte?",
          score: 6.0,
          gaps: [{ original: "redo", better: "remake my latte", why: "more natural" }],
          progress: { verdict: "needs-work" },
        },
      ],
    });
    setup("/practice/sess_abc?result=1");
    await waitFor(() => screen.getByText(/Say it again/));
    await userEvent.click(screen.getByText(/Say it again/));

    await waitFor(() => expect(screen.getByText("Tap once to record")).toBeInTheDocument());
    expect(screen.getByText(/Try to use/)).toBeInTheDocument();
    expect(screen.getByText("remake my latte")).toBeInTheDocument();
  });

  it("'Next' button starts a new round excluding current scenario", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        {
          round: 1,
          transcript: "x",
          summary: "s",
          nativeVersion: "N",
          score: 6.0,
          gaps: [],
          progress: { verdict: "needs-work" },
        },
      ],
    });
    setup("/practice/sess_abc?result=1");
    await waitFor(() => screen.getByText(/Say it again/));

    const nextBtn = screen.getAllByText(/Next/).find((el) => el.closest("button"));
    await userEvent.click(nextBtn.closest("button"));

    await waitFor(() =>
      expect(api.nextScenario).toHaveBeenCalledWith(
        USER.userId,
        expect.arrayContaining(["sc_coffee"]),
        PREFS,
      ),
    );
  });

  it("adds a gap to Review and toggles to 'In Review'", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        {
          round: 1,
          transcript: "Can you redo my latte",
          summary: "ok",
          nativeVersion: "Could you remake my latte?",
          score: 6.0,
          gaps: [{ original: "redo", better: "remake my latte", why: "more natural" }],
          progress: null,
        },
      ],
    });
    setup("/practice/sess_abc?result=1");
    await waitFor(() => screen.getByText("Add to Review"));
    await userEvent.click(screen.getByText("Add to Review").closest("button"));

    expect(api.addReviewItems).toHaveBeenCalledWith(
      USER.userId,
      expect.arrayContaining([
        expect.objectContaining({ expression: "remake my latte", original: "redo", note: "more natural" }),
      ]),
    );
    await waitFor(() => expect(screen.getByText("In Review")).toBeInTheDocument());
  });

  it("removes a gap that is already in Review", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        {
          round: 1,
          transcript: "Can you redo my latte",
          summary: "ok",
          nativeVersion: "Could you remake my latte?",
          score: 6.0,
          gaps: [{ original: "redo", better: "remake my latte", why: "more natural", reviewItemId: "rv_existing" }],
          progress: null,
        },
      ],
    });
    setup("/practice/sess_abc?result=1");
    await waitFor(() => screen.getByText("In Review"));
    await userEvent.click(screen.getByText("In Review").closest("button"));

    expect(api.deleteReviewItem).toHaveBeenCalledWith("rv_existing", USER.userId);
    await waitFor(() => expect(screen.getByText("Add to Review")).toBeInTheDocument());
  });

});
