import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import PracticePage from "./PracticePage.jsx";
import { UserProvider } from "../context/UserContext.jsx";

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

function setup(path = "/practice") {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
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
let lastRecorder;
class FakeMediaRecorder {
  static isTypeSupported() { return true; }
  constructor(stream) {
    this.stream = stream;
    this.mimeType = "audio/webm";
    this.ondataavailable = null;
    this.onstop = null;
    lastRecorder = this;
  }
  start() {
    this.ondataavailable?.({ data: { size: 10 } });
  }
  stop() {
    this.onstop?.();
  }
}

function installMediaStubs() {
  lastRecorder = undefined;
  const track = { stop: vi.fn() };
  global.MediaRecorder = FakeMediaRecorder;
  Object.defineProperty(global.navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) },
  });
  if (!global.URL.createObjectURL) global.URL.createObjectURL = vi.fn();
  global.URL.createObjectURL = vi.fn(() => "blob:fake-url");
  global.URL.revokeObjectURL = vi.fn();
}

// 一路把录音录到底、停掉、转写完成，停在 review 阶段
async function recordUntilReview() {
  const micBtn = document.querySelector(".su-rec");
  await userEvent.click(micBtn);
  await waitFor(() => expect(screen.getByText("Tap to stop")).toBeInTheDocument());
  await userEvent.click(document.querySelector(".su-rec"));
  await waitFor(() => expect(screen.getByText("Get feedback")).toBeInTheDocument());
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

  // ── 结果页刷新可还原（URL ?result=1）────────────────────
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
    // nativeVersion 被 splitSentences 拆成多个 <p>，匹配其中一句即可
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
    // mock：把流式回答一段段喂回去，再 done
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
    // 用户问题也渲染出来
    expect(screen.getByText("为什么这么改？")).toBeInTheDocument();
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

  it("Tap to start button is disabled while loading", () => {
    setup("/practice/sess_abc");
    const micBtn = document.querySelector(".su-rec");
    expect(micBtn).toBeDisabled();
  });

  it("Tap to start button is enabled in ready phase", async () => {
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap to start"));
    const micBtn = document.querySelector(".su-rec");
    expect(micBtn).not.toBeDisabled();
  });

  // ── 无 practiceId 时调 startNewRound ──────────────────

  it("fetches next scenario when no practiceId in URL", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice");
    await waitFor(() => expect(api.nextScenario).toHaveBeenCalledWith(USER.userId, []));
  });

  // ── 录音 → 转写 → review ───────────────────────────────

  it("requests microphone and shows recording UI after tapping start", async () => {
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap to start"));
    await userEvent.click(document.querySelector(".su-rec"));

    const { api } = await import("../api/client.js");
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText("Tap to stop")).toBeInTheDocument());
    expect(screen.getByText("Listening…")).toBeInTheDocument();
    expect(api).toBeDefined();
  });

  it("transcribes audio after stop and shows transcript in review phase", async () => {
    const { api } = await import("../api/client.js");
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap to start"));
    await recordUntilReview();

    expect(api.transcribeAudio).toHaveBeenCalledWith(USER.userId, expect.any(Object));
    expect(screen.getByText("Can you redo my latte")).toBeInTheDocument();
    // review 阶段两个按钮
    expect(screen.getByText("Get feedback")).toBeInTheDocument();
    expect(screen.getByText(/Redo/)).toBeInTheDocument();
  });

  it("shows review phase even when transcription fails", async () => {
    const { api } = await import("../api/client.js");
    api.transcribeAudio.mockRejectedValue(new Error("asr down"));
    vi.spyOn(window, "alert").mockImplementation(() => {});
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap to start"));
    await userEvent.click(document.querySelector(".su-rec"));
    await waitFor(() => screen.getByText("Tap to stop"));
    await userEvent.click(document.querySelector(".su-rec"));

    await waitFor(() => expect(screen.getByText("Get feedback")).toBeInTheDocument());
    expect(window.alert).toHaveBeenCalledWith(expect.stringContaining("Transcription failed"));
  });

  it("Get feedback is disabled when transcript is empty", async () => {
    const { api } = await import("../api/client.js");
    api.transcribeAudio.mockResolvedValue({ text: "" });
    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap to start"));
    await recordUntilReview();

    const btn = screen.getByText("Get feedback").closest("button");
    expect(btn).toBeDisabled();
  });

  // ── 提交评估（correctStream）───────────────────────────

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
    await waitFor(() => screen.getByText("Tap to start"));
    await recordUntilReview();
    await userEvent.click(screen.getByText("Get feedback"));

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
    // 录音异步上传
    await waitFor(() => expect(api.uploadRecording).toHaveBeenCalled());
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
    await waitFor(() => screen.getByText("Tap to start"));
    await recordUntilReview();
    await userEvent.click(screen.getByText("Get feedback"));

    await waitFor(() => expect(screen.getByText("Sounded native this time ✓")).toBeInTheDocument());
    expect(screen.getByText("Much better this time")).toBeInTheDocument();
    expect(screen.getByText("hot latte")).toBeInTheDocument();
    expect(screen.getByText("in a hurry")).toBeInTheDocument();
    // passed → 只有 Next scenario，没有 Say it again
    expect(screen.getByText(/Next scenario/)).toBeInTheDocument();
    expect(screen.queryByText(/Say it again/)).not.toBeInTheDocument();
  });

  it("returns to review phase and alerts when correctStream errors", async () => {
    const { correctStream } = await import("../api/client.js");
    vi.spyOn(window, "alert").mockImplementation(() => {});
    correctStream.mockImplementation((_data, { onError }) => {
      onError(new Error("boom"));
      return { abort: vi.fn() };
    });

    setup("/practice/sess_abc");
    await waitFor(() => screen.getByText("Tap to start"));
    await recordUntilReview();
    await userEvent.click(screen.getByText("Get feedback"));

    await waitFor(() =>
      expect(window.alert).toHaveBeenCalledWith(expect.stringContaining("Feedback request failed")),
    );
    expect(screen.getByText("Get feedback")).toBeInTheDocument();
  });

  // ── 三轮重说 / 下一题 ──────────────────────────────────

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

    await waitFor(() => expect(screen.getByText("Tap to start")).toBeInTheDocument());
    // 提示条带着上一轮 better
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
      expect(api.nextScenario).toHaveBeenCalledWith(USER.userId, expect.arrayContaining(["sc_coffee"])),
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
    // 最后一轮 → 只有 Next scenario
    expect(screen.getByText(/Next scenario/)).toBeInTheDocument();
    expect(screen.queryByText(/Say it again/)).not.toBeInTheDocument();
  });

  // ── 收录 / 取消收录 gap ────────────────────────────────

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

  // ── 追问对话错误分支 ───────────────────────────────────

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
