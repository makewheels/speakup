import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import SessionDetailPage from "./SessionDetailPage.jsx";
import { UserProvider } from "../context/UserContext.jsx";

vi.mock("../api/client.js", () => ({
  api: {
    getPractice: vi.fn(),
  },
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
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
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

  it("renders transcript from attempt", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() =>
      expect(screen.getByText("I tried to order")).toBeInTheDocument(),
    );
  });

  it("renders native version from attempt", async () => {
    const { api } = await import("../api/client.js");
    api.getPractice.mockResolvedValue(SESSION);
    setup();
    await waitFor(() =>
      expect(screen.getByText("I attempted to place an order.")).toBeInTheDocument(),
    );
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
        { ...SESSION.attempts[0], transcript: "First try" },
        { ...SESSION.attempts[0], transcript: "Second try" },
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
});
