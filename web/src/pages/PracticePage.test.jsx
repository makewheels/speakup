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

// SpeakBtn → tts → Audio.play() jsdom 里不支持，直接 stub
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
  videoUrl: "https://oss.example.com/clip.mp4",
  videoKey: "scenarios/sc_coffee/cover.mp4",
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

// ── 录音相关的浏览器 API 在 jsdom 里没有，统一 stub ─────────
// MediaRecorder：start() 立刻可用，stop() 同步触发 onstop（onstop 内会调 transcribeAudio）
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

// 一路把录音录到底、停掉、转写完成，进入 AI 自动评估
async function recordUntilEvaluating() {
  const { api } = await import("../api/client.js");
  const micBtn = document.querySelector(".su-rec");
  await userEvent.click(micBtn);
  await waitFor(() => expect(screen.getByText("Tap once to stop")).toBeInTheDocument());
  await userEvent.click(document.querySelector(".su-rec"));
  await waitFor(() => expect(api.transcribeAudio).toHaveBeenCalled());
}

describe("PracticePage", () => {
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

  // ── 初始加载 ────────────────────────────────────────────

  it("shows loading prompt immediately", () => {
    setup("/practice/sess_abc");
    expect(screen.getByText("Loading scenario…")).toBeInTheDocument();
  });

  it("fetches session by ID when practiceId is in URL", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice/sess_abc");
    await waitFor(() => expect(api.getPractice).toHaveBeenCalledWith("sess_abc"));
  });

  it("renders scenario story after session loads", async () => {
    setup("/practice/sess_abc");
    await waitFor(() =>
      expect(screen.getByText("You got the wrong drink.")).toBeInTheDocument(),
    );
  });

  it("does NOT show feedback (shows ready) when attempts exist but URL lacks ?result=1", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [{ round: 1, transcript: "x", summary: "s", nativeVersion: "N", score: 6, gaps: [], progress: null }],
    });
    setup("/practice/sess_abc");
    await waitFor(() =>
      expect(screen.getByText("You got the wrong drink.")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Native version")).not.toBeInTheDocument();
  });

  it("renders scenario points after session loads", async () => {
    setup("/practice/sess_abc");
    await waitFor(() =>
      expect(screen.getByText("Ask for hot latte")).toBeInTheDocument(),
    );
  });

  it("renders place label from scenario where", async () => {
    setup("/practice/sess_abc");
    await waitFor(() =>
      expect(screen.getByText("Coffee shop · Seattle")).toBeInTheDocument(),
    );
  });

  // ── 换题按钮（ready 阶段）──────────────────────────────

  it("shows Try another scenario button when ready", async () => {
    setup("/practice/sess_abc");
    await waitFor(() =>
      expect(screen.getByTitle("Try another scenario")).toBeInTheDocument(),
    );
  });

  it("Try another scenario passes current scenarioId in exclude list", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByTitle("Try another scenario"));

    await userEvent.click(screen.getByTitle("Try another scenario"));

    await waitFor(() =>
      expect(api.nextScenario).toHaveBeenCalledWith(
        USER.userId,
        expect.arrayContaining(["sc_coffee"]),
        PREFS,
      ),
    );
  });

  it("accumulates skip list across multiple switches", async () => {
    const { api } = await import("../api/client.js");
    // Initial load returns SESSION (sc_coffee); after navigation getPractice returns SESSION_B (sc_airport)
    api.getPractice.mockResolvedValueOnce(SESSION).mockResolvedValue(SESSION_B);
    api.nextScenario.mockResolvedValue(SCENARIO_B);
    api.createPractice.mockResolvedValue(SESSION_B);

    setup("/practice/sess_abc");
    await waitFor(() => screen.getByTitle("Try another scenario"));
    await userEvent.click(screen.getByTitle("Try another scenario"));

    await waitFor(() => screen.getByTitle("Try another scenario"));
    await userEvent.click(screen.getByTitle("Try another scenario"));

    const calls = api.nextScenario.mock.calls;
    expect(calls.length).toBeGreaterThanOrEqual(2);
    // First switch must exclude the original scenario
    expect(calls[0][1]).toContain("sc_coffee");
    // Second switch must exclude the scenario seen in the second session
    expect(calls[calls.length - 1][1]).toContain("sc_airport");
  });

  it("shows loading state while switching scenario", async () => {
    const { api } = await import("../api/client.js");
    // 让 nextScenario 挂住，检查 loading 状态
    let resolve;
    api.nextScenario.mockReturnValue(new Promise((r) => { resolve = r; }));

    setup("/practice/sess_abc");
    await waitFor(() => screen.getByTitle("Try another scenario"));
    await userEvent.click(screen.getByTitle("Try another scenario"));

    expect(screen.getByText("Loading scenario…")).toBeInTheDocument();
    resolve(SCENARIO_B);
  });

  it("calls createPractice with userId and the new scenarioId", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByTitle("Try another scenario"));
    await userEvent.click(screen.getByTitle("Try another scenario"));

    await waitFor(() =>
      expect(api.createPractice).toHaveBeenCalledWith({
        userId: USER.userId,
        scenarioId: SCENARIO_B.scenarioId,
      }),
    );
  });

  // ── 录音按钮 ──────────────────────────────────────────

  it("record button is disabled while loading", () => {
    setup("/practice/sess_abc");
    const micBtn = document.querySelector(".su-rec");
    expect(micBtn).toBeDisabled();
  });

  it("record button is enabled in ready phase", async () => {
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    const micBtn = document.querySelector(".su-rec");
    expect(micBtn).not.toBeDisabled();
  });

  // ── 无 practiceId 时调 startNewRound ──────────────────

  it("shows preference welcome before first practice", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice", { prefs: false });

    expect(screen.getByText("What do you want to practice?")).toBeInTheDocument();
    expect(api.nextScenario).not.toHaveBeenCalled();

    await userEvent.click(screen.getByText("IELTS"));
    await userEvent.click(screen.getByText("Beginner"));
    await userEvent.click(screen.getByText("Start practicing"));

    await waitFor(() =>
      expect(api.nextScenario).toHaveBeenCalledWith(
        USER.userId,
        [],
        { level: "beginner", purpose: "ielts" },
      ),
    );
  });

  it("fetches next scenario when no practiceId in URL", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice");
    await waitFor(() => expect(api.nextScenario).toHaveBeenCalledWith(USER.userId, [], PREFS));
  });

  it("shows a short note when the library falls back from the selected preference", async () => {
    const { api } = await import("../api/client.js");
    api.nextScenario.mockResolvedValue({
      ...SCENARIO_B,
      preferenceMatch: "fallback",
    });
    setup("/practice");

    await waitFor(() =>
      expect(screen.getByText(/The library is being filled in/)).toBeInTheDocument(),
    );
  });

  // ── 录音 → 转写 → review ───────────────────────────────

  it("requests microphone and shows recording UI after tapping start", async () => {
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    await userEvent.click(document.querySelector(".su-rec"));

    const { api } = await import("../api/client.js");
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText("Tap once to stop")).toBeInTheDocument());
    expect(screen.getByText("Listening…")).toBeInTheDocument();
    expect(api).toBeDefined();
  });

  it("transcribes audio after stop and automatically starts AI review", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    await recordUntilEvaluating();

    expect(api.transcribeAudio).toHaveBeenCalledWith(USER.userId, expect.any(Object));
    expect(screen.getByText("Can you redo my latte")).toBeInTheDocument();
    expect(screen.getAllByText(/AI is reviewing/).length).toBeGreaterThan(0);
  });

  it("shows review phase even when transcription fails", async () => {
    const { api } = await import("../api/client.js");
    api.transcribeAudio.mockRejectedValue(new Error("asr down"));
    vi.spyOn(window, "alert").mockImplementation(() => {});
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    await userEvent.click(document.querySelector(".su-rec"));
    await waitFor(() => screen.getByText("Tap once to stop"));
    await userEvent.click(document.querySelector(".su-rec"));

    await waitFor(() => expect(screen.getByText("Review now")).toBeInTheDocument());
    expect(window.alert).toHaveBeenCalledWith(expect.stringContaining("Transcription failed"));
  });

  it("Review now is disabled when transcript is empty", async () => {
    const { api } = await import("../api/client.js");
    api.transcribeAudio.mockResolvedValue({ text: "" });
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap once to record"));
    const micBtn = document.querySelector(".su-rec");
    await userEvent.click(micBtn);
    await waitFor(() => expect(screen.getByText("Tap once to stop")).toBeInTheDocument());
    await userEvent.click(document.querySelector(".su-rec"));
    await waitFor(() => expect(screen.getByText("Review now")).toBeInTheDocument());

    const btn = screen.getByText("Review now").closest("button");
    expect(btn).toBeDisabled();
  });

});
