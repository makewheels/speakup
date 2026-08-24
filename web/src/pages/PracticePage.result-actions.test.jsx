import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  USER,
  SESSION,
  setup,
  installMediaStubs,
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

describe("PracticePage result actions", () => {
  beforeEach(async () => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    api.sharePractice.mockResolvedValue({ shareToken: "tok_result" });
    api.unsharePractice.mockResolvedValue({ ok: true });
    api.submitFeedback.mockResolvedValue({});
    api.listMyFeedbacks.mockResolvedValue([]);
    installMediaStubs();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders an error message in chat when chatStream errors", async () => {
    const { api, chatStream } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [{
        round: 1,
        transcript: "Can you redo my latte",
        summary: "ok",
        nativeVersion: "Could you remake my latte?",
        score: 6.5,
        gaps: [],
        progress: null,
        chat: [],
      }],
    });
    chatStream.mockImplementation((_data, { onError }) => {
      onError(new Error("net fail"));
      return { abort: vi.fn() };
    });

    setup("/practice/sess_abc?result=1");
    await waitFor(() => screen.getByText("Ask the coach"));
    const box = screen.getByPlaceholderText(/Ask about this feedback/);
    await userEvent.type(box, "为什么？");
    await userEvent.keyboard("{Enter}");

    await waitFor(() => expect(screen.getByText(/Error: net fail/)).toBeInTheDocument());
  });

  it("does not render a legacy AI-generated auto note", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [{
        round: 1,
        transcript: "Can you redo my latte",
        summary: "ok",
        nativeVersion: "Could you remake my latte?",
        standardAnswer: "Excuse me, could you remake my latte? I'm in a bit of a rush.",
        note: "I'm in a bit of a rush",
        noteChinese: "我有点赶时间",
        score: 6.0,
        gaps: [],
        progress: null,
      }],
    });

    setup("/practice/sess_abc?result=1");
    await waitFor(() => expect(screen.getByText("Share this result")).toBeInTheDocument());
    expect(screen.queryByText("Auto-noted")).not.toBeInTheDocument();
    expect(document.querySelector(".fb-page").lastElementChild)
      .toBe(screen.getByText("Share this result").closest(".fb-result-share-row"));
  });

  it("shares directly from the result page", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [{
        round: 1,
        transcript: "Can you redo my latte",
        summary: "ok",
        nativeVersion: "Could you remake my latte?",
        score: 6.0,
        gaps: [],
        progress: null,
      }],
    });

    setup("/practice/sess_abc?result=1");
    await waitFor(() => screen.getByText("Share this result"));
    await userEvent.click(screen.getByText("Share this result"));

    await waitFor(() => {
      expect(api.sharePractice).toHaveBeenCalledWith("sess_abc", USER.userId);
      expect(writeText).toHaveBeenCalledWith(expect.stringContaining("/s/tok_result"));
    });
    expect(screen.getByText("Share message copied")).toBeInTheDocument();
  });
});
