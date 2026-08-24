import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import SessionDetailPage from "./SessionDetailPage.jsx";
import { UserProvider } from "../context/UserContext.jsx";

vi.mock("../api/client.js", () => ({
  api: {
    getPractice: vi.fn(),
    sharePractice: vi.fn(),
    unsharePractice: vi.fn(),
    submitFeedback: vi.fn(),
    listMyFeedbacks: vi.fn(),
  },
  chatStream: vi.fn((data, { onChunk, onDone }) => {
    onChunk?.("hi");
    onDone?.({ text: "hi" });
    return { abort() {} };
  }),
}));

vi.mock("../utils/tts.js", () => ({
  speak: vi.fn().mockResolvedValue(null),
  stop: vi.fn(),
  isCached: vi.fn().mockReturnValue(false),
}));

const USER = { userId: "u_1", phone: "13812345678", nickname: "Test" };

const SESSION = {
  _id: "sess_1",
  userId: "u_1",
  title: "Coffee shop",
  topic: "Coffee shop · Seattle",
  imageUrl: "",
  createdAt: "2026-06-01T10:00:00Z",
  attempts: [
    {
      round: 1,
      transcript: "I tried to order",
      nativeVersion: "I attempted to place an order.",
      score: 6.5,
      gaps: [
        { original: "tried to order", better: "attempted to place an order", why: "More formal" },
      ],
    },
  ],
  recordings: [],
};

function setup(practiceId = "sess_1") {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  return render(
    <MemoryRouter initialEntries={[`/history/${practiceId}`]}>
      <UserProvider>
        <Routes>
          <Route path="/history/:practiceId" element={<SessionDetailPage />} />
        </Routes>
      </UserProvider>
    </MemoryRouter>,
  );
}

describe("SessionDetailPage", () => {
  beforeEach(async () => {
    localStorage.clear();
    vi.clearAllMocks();
    const { api } = await import("../api/client.js");
    api.listMyFeedbacks.mockResolvedValue([]);
  });

  it("shows the practice feedback bar on the history detail page", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() => expect(screen.getByText("Give feedback on this result")).toBeInTheDocument());
  });

  it("shows loading while fetching", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockReturnValue(new Promise(() => {}));
    setup();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows not found when session is null", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(null);
    setup();
    await waitFor(() =>
      expect(screen.getByText("Practice not found")).toBeInTheDocument(),
    );
  });

  it("renders session title", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() =>
      expect(screen.getByText("Coffee shop")).toBeInTheDocument(),
    );
  });

  it("renders an attempted session video in the full-width media container", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      imageUrl: "https://oss.example/cover.jpg",
      videoUrl: "https://oss.example/cover.mp4",
    });
    const { container } = setup();

    const video = await screen.findByLabelText("scene video");
    const media = video.closest(".session-practice-media");
    expect(media).toHaveClass("session-detail-video");
    expect(video.closest(".detail-hero-media")).toBeNull();
    expect(video.closest(".detail-hero")).toBeNull();
    expect(container.querySelector(".detail-hero")?.nextElementSibling).toHaveClass("share-bar");
    expect(container.querySelector(".share-bar")?.nextElementSibling).toBe(media);
  });

  it("keeps an attempted session image as the compact hero thumbnail", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      imageUrl: "https://oss.example/cover.jpg",
      videoUrl: "",
    });
    setup();

    const image = await screen.findByAltText("scene");
    expect(image.closest(".detail-hero-media")).toBeInTheDocument();
    expect(image.closest(".session-detail-video")).toBeNull();
  });

  it("shows a Free talk badge for free-mode sessions and topic card", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      scenarioId: "",
      mode: "free",
      freeTopic: "Your favorite breakfast",
      title: "Your favorite breakfast",
      scenario: { kind: "free", title: "Your favorite breakfast", freeTopic: "Your favorite breakfast" },
    });
    setup();
    // 标题和徽章同在一个容器里，用正则匹配标题文本
    await waitFor(() =>
      expect(screen.getByText(/Your favorite breakfast/)).toBeInTheDocument(),
    );
    expect(screen.getByText("Free talk")).toBeInTheDocument();
  });

  it("does not show Free talk badge for scenario sessions", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() => screen.getByText("Coffee shop"));
    expect(screen.queryByText("Free talk")).not.toBeInTheDocument();
  });

  it("renders formatted datetime", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() =>
      expect(screen.getByText(/2026-06-01/)).toBeInTheDocument(),
    );
  });

  it("shows no feedback message when no attempts", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({ ...SESSION, attempts: [] });
    setup();
    await waitFor(() =>
      expect(
        screen.getByText("No AI feedback for this practice yet"),
      ).toBeInTheDocument(),
    );
  });

  it("uses gap pairs instead of repeating the whole transcript", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() => expect(screen.getByText("tried to order")).toBeInTheDocument());
    expect(screen.queryByText("I tried to order")).not.toBeInTheDocument();
  });

  it("does not render the legacy whole corrected version", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() => expect(screen.getByText("attempted to place an order")).toBeInTheDocument());
    expect(screen.queryByText("I attempted to place an order.")).not.toBeInTheDocument();
  });

  it("renders the standard answer when the attempt has one", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({
      ...SESSION,
      attempts: [
        { ...SESSION.attempts[0], standardAnswer: "Could I get a large coffee to go, please?" },
      ],
    });
    setup();
    await waitFor(() => expect(screen.getByText("Standard answer")).toBeInTheDocument());
    expect(screen.getByText("Could I get a large coffee to go, please?")).toBeInTheDocument();
  });

  it("renders IELTS score", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() =>
      expect(screen.getByText("6.5")).toBeInTheDocument(),
    );
  });

  it("renders gap 'You said' and 'Say this'", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() => {
      expect(screen.getByText("tried to order")).toBeInTheDocument();
      expect(screen.getByText("attempted to place an order")).toBeInTheDocument();
    });
  });

  it("renders gap why explanation", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() =>
      expect(screen.getByText("More formal")).toBeInTheDocument(),
    );
  });

  it("shows Back button", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() =>
      expect(screen.getByText("Back")).toBeInTheDocument(),
    );
  });

  it("renders Attempt label for each attempt", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() =>
      expect(screen.getByText("Attempt 1")).toBeInTheDocument(),
    );
  });

  it("shows attempt tabs and switches between attempts", async () => {
    const { api } = await import("../api/client.js");
    const multiSession = {
      ...SESSION,
      attempts: [
        { ...SESSION.attempts[0], gaps: [{ original: "First try", better: "First revision", why: "x" }] },
        { ...SESSION.attempts[0], gaps: [{ original: "Second try", better: "Second revision", why: "x" }] },
      ],
    };
    api.getPractice.mockResolvedValue(multiSession);
    setup();
    // 两个 tab 都在；默认选中最新一轮（Attempt 2 → "Second try"）
    await waitFor(() => {
      expect(screen.getAllByText("Attempt 2").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Attempt 1").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("Second try")).toBeInTheDocument();
    expect(screen.queryByText("First try")).not.toBeInTheDocument();

    // 切到 Attempt 1 → 只显示该轮内容
    const tab1 = screen.getAllByText("Attempt 1").find((el) => el.tagName === "BUTTON");
    await userEvent.click(tab1);
    await waitFor(() => {
      expect(screen.getByText("First try")).toBeInTheDocument();
      expect(screen.queryByText("Second try")).not.toBeInTheDocument();
    });
  });

  it("shows 'Not shared' state with a Share button when not shared", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() =>
      expect(screen.getByText("Not shared")).toBeInTheDocument(),
    );
    expect(screen.getByText("Share")).toBeInTheDocument();
  });

  it("shares: calls api.sharePractice, copies text+link, shows Shared state", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    api.sharePractice.mockResolvedValue({ shareToken: "tok_abc" });
    setup();
    await waitFor(() => expect(screen.getByText("Share")).toBeInTheDocument());

    await userEvent.click(screen.getByText("Share"));

    await waitFor(() => {
      expect(api.sharePractice).toHaveBeenCalledWith("sess_1", "u_1");
      expect(writeText).toHaveBeenCalled();
    });
    // 复制内容含文案 + 链接
    const copied = writeText.mock.calls[0][0];
    expect(copied).toContain("Coffee shop");
    expect(copied).toContain("/s/tok_abc");
    // 切换到已分享状态
    await waitFor(() => {
      expect(screen.getByText("Shared")).toBeInTheDocument();
      expect(screen.getByText("Stop sharing")).toBeInTheDocument();
    });
    vi.unstubAllGlobals();
  });

  it("renders Shared state for an already-shared session and stops sharing", async () => {
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue({ ...SESSION, shared: true, shareToken: "tok_existing" });
    api.unsharePractice.mockResolvedValue({ ok: true });
    setup();
    await waitFor(() => expect(screen.getByText("Shared")).toBeInTheDocument());

    await userEvent.click(screen.getByText("Stop sharing"));

    await waitFor(() => {
      expect(api.unsharePractice).toHaveBeenCalledWith("sess_1", "u_1");
      expect(screen.getByText("Not shared")).toBeInTheDocument();
    });
    vi.unstubAllGlobals();
  });

  it("ask-the-coach: shows input on latest attempt and sends a question via chatStream", async () => {
    const { api, chatStream } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() =>
      expect(screen.getByText("Ask the coach")).toBeInTheDocument(),
    );

    const input = screen.getByPlaceholderText(/Ask about this feedback/);
    await userEvent.type(input, "Why this change?");
    // 输入框旁的发送按钮（只含图标，无文字）
    const sendBtn = input.parentElement.querySelector("button");
    await userEvent.click(sendBtn);

    await waitFor(() => {
      expect(chatStream).toHaveBeenCalled();
    });
    expect(chatStream.mock.calls[0][0]).toMatchObject({
      userId: "u_1",
      practiceId: "sess_1",
      question: "Why this change?",
    });
    // onChunk("hi") 写入助手回复
    await waitFor(() =>
      expect(screen.getByText("hi")).toBeInTheDocument(),
    );
  });

  it("sends the question when pressing Enter in the ask-the-coach input", async () => {
    const { api, chatStream } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() => expect(screen.getByText("Ask the coach")).toBeInTheDocument());

    const input = screen.getByPlaceholderText(/Ask about this feedback/);
    await userEvent.type(input, "More examples?{Enter}");

    await waitFor(() => expect(chatStream).toHaveBeenCalled());
    expect(chatStream.mock.calls[0][0].question).toBe("More examples?");
  });

  it("older attempt tab shows read-only chat without an input box", async () => {
    const { api } = await import("../api/client.js");
    const multiSession = {
      ...SESSION,
      attempts: [
        {
          ...SESSION.attempts[0],
          transcript: "First try",
          chat: [
            { role: "user", content: "old question" },
            { role: "assistant", content: "old answer" },
          ],
        },
        { ...SESSION.attempts[0], transcript: "Second try" },
      ],
    };
    api.getPractice.mockResolvedValue(multiSession);
    setup();
    await waitFor(() =>
      expect(screen.getAllByText("Attempt 1").length).toBeGreaterThan(0),
    );

    // 最新一轮有输入框
    expect(screen.getByPlaceholderText(/Ask about this feedback/)).toBeInTheDocument();

    // 切到旧轮 → coach 追问只读、无追问输入框（反馈条仍在，可对该轮反馈）
    const tab1 = screen.getAllByText("Attempt 1").find((el) => el.tagName === "BUTTON");
    await userEvent.click(tab1);
    await waitFor(() => {
      expect(screen.getByText("old question")).toBeInTheDocument();
      expect(screen.getByText("old answer")).toBeInTheDocument();
    });
    expect(screen.queryByPlaceholderText(/Ask about this feedback/)).not.toBeInTheDocument();
  });
});
