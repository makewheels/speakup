import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import PracticePage from "./PracticePage.jsx";
import { UserProvider } from "../context/UserContext.jsx";
import { savePracticePreferences } from "../lib/practicePreferences.js";

vi.mock("../api/client.js", () => ({
  api: {
    nextScenario: vi.fn(),
    createPractice: vi.fn(),
    getPractice: vi.fn(),
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

const USER = { userId: "u_test1", phone: "13800001234", nickname: "Test" };

const SESSION = {
  _id: "sess_abc",
  userId: "u_test1",
  scenarioId: "sc_coffee",
  title: "Coffee shop mess",
  topic: "Coffee shop · Seattle",
  scenario: {
    title: "Coffee shop mess",
    where: "Coffee shop · Seattle",
    story: "You got the wrong drink.",
    mission: "Ask them to redo it.",
    points: ["Ask for hot latte", "Say you are in a hurry"],
  },
  imageUrl: "https://oss.example.com/img.jpg",
  imageKey: "scenarios/sc_coffee/cover.jpg",
  attempts: [],
  createdAt: "2026-06-01T10:00:00Z",
};

const SCENARIO_B = {
  scenarioId: "sc_airport",
  title: "Airport check-in",
  where: "Airport",
  story: "Your bag is overweight.",
  mission: "Negotiate with the agent.",
  points: [],
  imageUrl: "https://oss.example.com/airport.jpg",
  isCustom: false,
};

const SESSION_B = {
  ...SESSION,
  _id: "sess_xyz",
  scenarioId: "sc_airport",
  title: "Airport check-in",
};

const PREFS = { level: "daily", purpose: "travel" };

function setup(path = "/practice", { prefs = true } = {}) {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  if (prefs) savePracticePreferences(USER.userId, PREFS);
  return render(
    <MemoryRouter initialEntries={[path]}>
      <UserProvider>
        <Routes>
          <Route path="/practice" element={<PracticePage />} />
          <Route path="/practice/:practiceId" element={<PracticePage />} />
        </Routes>
      </UserProvider>
    </MemoryRouter>,
  );
}

class FakeMediaRecorder {
  static isTypeSupported() { return true; }
  constructor(stream) {
    this.stream = stream;
    this.mimeType = "audio/webm";
    this.state = "inactive";
    this.ondataavailable = null;
    this.onstop = null;
  }
  start() {
    this.state = "recording";
    this.ondataavailable?.({ data: { size: 10 } });
  }
  requestData() {
    this.ondataavailable?.({ data: { size: 10 } });
  }
  stop() {
    this.state = "inactive";
    this.onstop?.();
  }
}

function installMediaStubs() {
  const track = { stop: vi.fn() };
  globalThis.MediaRecorder = FakeMediaRecorder;
  Object.defineProperty(globalThis.navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) },
  });
  if (!globalThis.URL.createObjectURL) globalThis.URL.createObjectURL = vi.fn();
  globalThis.URL.createObjectURL = vi.fn(() => "blob:fake-url");
  globalThis.URL.revokeObjectURL = vi.fn();
}

async function recordUntilEvaluating() {
  const { api } = await import("../api/client.js");
  const micBtn = document.querySelector(".su-rec");
  await userEvent.click(micBtn);
  await waitFor(() => expect(screen.getByText("Tap once to stop")).toBeInTheDocument());
  await userEvent.click(document.querySelector(".su-rec"));
  await waitFor(() => expect(api.transcribeAudio).toHaveBeenCalled());
}

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
    installMediaStubs();
  });

  it("restores the feedback view from the latest attempt when URL has ?result=1", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        {
          round: 1,
          transcript: "Can you redo my latte",
          summary: "整体不错，请求可以更自然",
          nativeVersion: "Could you remake my latte? I'm in a hurry.",
          score: 6.5,
          gaps: [],
          progress: null,
        },
      ],
    });
    setup("/practice/sess_abc?result=1");
    await waitFor(() =>
      expect(screen.getByText("Native version")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Could you remake my latte/)).toBeInTheDocument();
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

  it("evaluates and renders feedback (score / nativeVersion / gaps) on stream done", async () => {
    const { api, correctStream } = await import("../api/client.js");
    correctStream.mockImplementation((data, { onChunk, onDone }) => {
      onChunk("partial ");
      onDone({
        result: {
          summary: "good",
          nativeVersion: "Could you remake my latte? I'm in a hurry.",
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

    await waitFor(() => expect(screen.getByText("Native version")).toBeInTheDocument());
    expect(correctStream).toHaveBeenCalledWith(
      expect.objectContaining({ userId: USER.userId, practiceId: "sess_abc", text: "Can you redo my latte" }),
      expect.any(Object),
    );
    expect(screen.getByText("7.0")).toBeInTheDocument();
    expect(screen.getByText(/Could you remake my latte/)).toBeInTheDocument();
    expect(screen.getByText("remake my latte")).toBeInTheDocument();
    expect(screen.getByText("more natural")).toBeInTheDocument();
    expect(screen.getByText(/1 added to Review/)).toBeInTheDocument();
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
          nativeVersion: "",
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
    expect(screen.queryByText(/Say it again/)).not.toBeInTheDocument();
  });

  it("keeps the user on feedback after a streamed final-round review", async () => {
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

    await waitFor(() => expect(screen.getByText("Native version")).toBeInTheDocument());
    expect(screen.getByText(/these expressions are saved to review/)).toBeInTheDocument();
    expect(screen.getByText(/Next scenario/)).toBeInTheDocument();
    expect(screen.queryByText(/Tap once to record/)).not.toBeInTheDocument();
    expect(api.nextScenario).not.toHaveBeenCalled();
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

  it("shows 'rounds out' note when last round and not passed", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        { round: 1, transcript: "a", summary: "s", nativeVersion: "N1", score: 6, gaps: [], progress: { verdict: "needs-work" } },
        { round: 2, transcript: "b", summary: "s", nativeVersion: "N2", score: 6.5, gaps: [], progress: { verdict: "needs-work" } },
      ],
    });
    setup("/practice/sess_abc?result=1");
    await waitFor(() =>
      expect(screen.getByText(/these expressions are saved to review/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Next scenario/)).toBeInTheDocument();
    expect(screen.queryByText(/Say it again/)).not.toBeInTheDocument();
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

  it("renders an error message in chat when chatStream errors", async () => {
    const { api, chatStream } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        {
          round: 1,
          transcript: "Can you redo my latte",
          summary: "ok",
          nativeVersion: "Could you remake my latte?",
          score: 6.5,
          gaps: [],
          progress: null,
          chat: [],
        },
      ],
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
});
