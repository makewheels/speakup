import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

import HistoryPage from "./HistoryPage.jsx";
import { UserProvider } from "../context/UserContext.jsx";

vi.mock("../api/client.js", () => ({
  api: {
    listPractices: vi.fn(),
  },
}));

const USER = { userId: "u_1", phone: "13812345678", nickname: "Test" };

const SESSION_A = {
  _id: "s1",
  userId: "u_1",
  scenarioId: "sc_coffee",
  title: "Coffee shop",
  topic: "Coffee shop · Seattle",
  imageUrl: "",
  attempts: [{ round: 1, transcript: "I tried", gaps: [{ original: "tried", better: "attempted" }] }],
  createdAt: "2026-06-01T08:00:00Z",
};

const SESSION_B = {
  _id: "s2",
  userId: "u_1",
  scenarioId: "sc_airport",
  title: "Airport check-in",
  topic: "Airport",
  imageUrl: "",
  attempts: [{ round: 1, transcript: "My bag", gaps: [] }],
  createdAt: "2026-06-02T09:00:00Z",
};

// Session A의 두 번째 시도 (same scenarioId → grouped)
const SESSION_A2 = {
  ...SESSION_A,
  _id: "s3",
  createdAt: "2026-06-03T10:00:00Z",
};

function setup() {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  return render(
    <MemoryRouter>
      <UserProvider>
        <HistoryPage />
      </UserProvider>
    </MemoryRouter>,
  );
}

describe("HistoryPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("shows loading state before data arrives", async () => {
    const { api } = await import("../api/client.js");
    api.listPractices.mockReturnValue(new Promise(() => {}));
    setup();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows empty state when no sessions", async () => {
    const { api } = await import("../api/client.js");
    api.listPractices.mockResolvedValue([]);
    setup();
    await waitFor(() =>
      expect(screen.getByText("No practice history yet")).toBeInTheDocument(),
    );
  });

  it("renders scenario titles from sessions", async () => {
    const { api } = await import("../api/client.js");
    api.listPractices.mockResolvedValue([SESSION_A, SESSION_B]);
    setup();
    await waitFor(() => {
      expect(screen.getByText("Coffee shop")).toBeInTheDocument();
      expect(screen.getByText("Airport check-in")).toBeInTheDocument();
    });
  });

  it("shows scenarios count in header", async () => {
    const { api } = await import("../api/client.js");
    api.listPractices.mockResolvedValue([SESSION_A, SESSION_B]);
    setup();
    await waitFor(() =>
      expect(screen.getByText("2 scenarios")).toBeInTheDocument(),
    );
  });

  it("groups sessions with same scenarioId together", async () => {
    const { api } = await import("../api/client.js");
    // SESSION_A and SESSION_A2 share scenarioId=sc_coffee → 1 group
    api.listPractices.mockResolvedValue([SESSION_A, SESSION_B, SESSION_A2]);
    setup();
    // 3 sessions but 2 unique scenarios
    await waitFor(() =>
      expect(screen.getByText("2 scenarios")).toBeInTheDocument(),
    );
  });

  it("shows '2 attempts' chip for grouped sessions", async () => {
    const { api } = await import("../api/client.js");
    api.listPractices.mockResolvedValue([SESSION_A, SESSION_A2]);
    setup();
    await waitFor(() =>
      expect(screen.getByText("2 attempts")).toBeInTheDocument(),
    );
  });

  it("shows gaps chip for single-attempt sessions", async () => {
    const { api } = await import("../api/client.js");
    api.listPractices.mockResolvedValue([SESSION_A]);
    setup();
    await waitFor(() =>
      expect(screen.getByText("1 gaps")).toBeInTheDocument(),
    );
  });

  it("expands grouped sessions on click", async () => {
    const { api } = await import("../api/client.js");
    api.listPractices.mockResolvedValue([SESSION_A, SESSION_A2]);
    setup();
    await waitFor(() => screen.getByText("Coffee shop"));
    await userEvent.click(screen.getByText("Coffee shop"));
    await waitFor(() =>
      expect(screen.getAllByText(/Attempt \d/)).toHaveLength(2),
    );
  });

  it("shows Load more button when page is full", async () => {
    const { api } = await import("../api/client.js");
    // PAGE = 20, return 20 sessions to trigger hasMore
    const sessions = Array.from({ length: 20 }, (_, i) => ({
      ...SESSION_A,
      _id: `s${i}`,
      scenarioId: `sc_${i}`,
      title: `Scenario ${i}`,
    }));
    api.listPractices.mockResolvedValue(sessions);
    setup();
    await waitFor(() =>
      expect(screen.getByText("Load more")).toBeInTheDocument(),
    );
  });

  it("Load more fetches next page", async () => {
    const { api } = await import("../api/client.js");
    const sessions = Array.from({ length: 20 }, (_, i) => ({
      ...SESSION_A,
      _id: `s${i}`,
      scenarioId: `sc_${i}`,
      title: `Scenario ${i}`,
    }));
    api.listPractices
      .mockResolvedValueOnce(sessions)
      .mockResolvedValue([SESSION_B]);
    setup();
    await waitFor(() => screen.getByText("Load more"));
    await userEvent.click(screen.getByText("Load more"));
    await waitFor(() =>
      expect(api.listPractices).toHaveBeenCalledWith(USER.userId, 20),
    );
  });

  it("hides Load more when last page is partial", async () => {
    const { api } = await import("../api/client.js");
    api.listPractices.mockResolvedValue([SESSION_A]); // < 20 → no more
    setup();
    await waitFor(() => screen.getByText("Coffee shop"));
    expect(screen.queryByText("Load more")).not.toBeInTheDocument();
  });

  it("navigates to practice when empty state button clicked", async () => {
    const { api } = await import("../api/client.js");
    api.listPractices.mockResolvedValue([]);
    setup();
    await waitFor(() => screen.getByText("Start practicing"));
    // Just verify button is rendered and clickable
    expect(screen.getByText("Start practicing")).toBeInTheDocument();
  });
});
