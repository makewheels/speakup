import { act, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  SCENARIO_B,
  SESSION,
  SESSION_B,
  installMediaStubs,
  recordUntilEvaluating,
  setup,
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

describe("PracticePage result stability", () => {
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
    api.addReviewItems.mockResolvedValue({ ids: [] });
    api.submitFeedback.mockResolvedValue({});
    api.listMyFeedbacks.mockResolvedValue([]);
    installMediaStubs();
  });

  it("渐进加载保留题目后的评分占位，完成后不再次滚动", async () => {
    const { correctStream } = await import("../api/client.js");
    let streamHandlers;
    correctStream.mockImplementation((_data, handlers) => {
      streamHandlers = handlers;
      return { abort: vi.fn() };
    });
    const originalScrollTo = window.scrollTo;
    const scrollSpy = vi.fn();
    window.scrollTo = scrollSpy;
    try {
      setup("/practice/sess_abc");
      await waitFor(() => screen.getByText("Tap once to record"));
      await recordUntilEvaluating();
      await act(async () => {
        streamHandlers.onStarted({ attemptId: "pa_test_1", round: 1 });
      });
      await waitFor(() => expect(document.querySelector(".fb-score.is-loading")).toBeTruthy());

      const anchor = document.querySelector(".fb-score-anchor");
      const scenarioCard = document.querySelector(".fb-page .sc-card");
      expect(scenarioCard.compareDocumentPosition(anchor) & Node.DOCUMENT_POSITION_FOLLOWING)
        .toBeTruthy();
      expect(anchor.querySelector(".fb-score-num")).toHaveTextContent("–");
      expect(scrollSpy).toHaveBeenCalledTimes(1);

      await act(async () => {
        streamHandlers.onChunk("partial result");
        streamHandlers.onDone({
          attemptId: "pa_test_1",
          result: {
            summary: "整体不错",
            standardAnswer: "Could you remake my latte?",
            score: 6.5,
            gaps: [],
            progress: null,
          },
          autoSaved: 0,
          round: 1,
        });
      });

      await waitFor(() => expect(screen.getByText("6.5")).toBeInTheDocument());
      expect(document.querySelector(".fb-score-anchor")).toBe(anchor);
      expect(scrollSpy).toHaveBeenCalledTimes(1);
    } finally {
      window.scrollTo = originalScrollTo;
    }
  });
});
