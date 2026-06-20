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

describe("PracticePage", () => {
  beforeEach(async () => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    const { api } = await import("../api/client.js");
    api.nextScenario.mockResolvedValue(SCENARIO_B);
    api.createPractice.mockResolvedValue(SESSION_B);
    api.getPractice.mockResolvedValue(SESSION);
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
    await waitFor(() => expect(screen.getByText("继续追问 AI")).toBeInTheDocument());

    const box = screen.getByPlaceholderText(/基于上面的反馈追问/);
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
});
