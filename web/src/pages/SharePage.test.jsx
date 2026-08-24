import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import SharePage from "./SharePage.jsx";

vi.mock("../api/client.js", () => ({
  api: {
    getSharedSession: vi.fn(),
  },
}));

vi.mock("../utils/tts.js", () => ({
  speak: vi.fn().mockResolvedValue(null),
  stop: vi.fn(),
  isCached: vi.fn().mockReturnValue(false),
}));

const SHARED = {
  _id: "sess_1",
  title: "Coffee shop",
  topic: "Coffee shop · Seattle",
  scenario: {
    where: "Coffee shop · Seattle",
    story: "You are ordering coffee before work.",
    mission: "Order a coffee politely",
    points: ["Ask for a latte", "Ask about the price"],
  },
  imageUrl: "https://oss.example/cover.jpg",
  videoUrl: "https://oss.example/cover.mp4",
  createdAt: "2026-06-01T10:00:00Z",
  ownerNickname: "Alice",
  attempts: [
    {
      attemptId: "pa_1",
      round: 1,
      transcript: "I tried to order",
      score: 6.5,
      gaps: [{ original: "I tried to order", better: "I attempted to place an order.", why: "More natural" }],
    },
    {
      attemptId: "pa_2",
      round: 2,
      transcript: "The second attempt",
      score: 7,
      gaps: [{ original: "The second attempt", better: "The improved second attempt", why: "Clearer" }],
    },
  ],
  recordings: [],
};

function setup(token = "tok_1", query = "") {
  return render(
    <MemoryRouter initialEntries={[`/s/${token}${query}`]}>
      <Routes>
        <Route path="/s/:token" element={<SharePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SharePage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders shared session content and owner", async () => {
    const { api } = await import("../api/client.js");
    api.getSharedSession.mockResolvedValue(SHARED);
    setup();
    await waitFor(() => {
      expect(screen.getByText("Coffee shop")).toBeInTheDocument();
      expect(screen.getByText("Shared by Alice")).toBeInTheDocument();
      expect(screen.getByText("The second attempt")).toBeInTheDocument();
    });
  });

  it("opens the attempt selected by the share link", async () => {
    const { api } = await import("../api/client.js");
    api.getSharedSession.mockResolvedValue(SHARED);
    setup("tok_1", "?attempt=pa_1");
    expect(await screen.findByText("I tried to order")).toBeInTheDocument();
  });

  it("hides the ask-the-coach input in read-only mode", async () => {
    const { api } = await import("../api/client.js");
    api.getSharedSession.mockResolvedValue(SHARED);
    setup();
    await waitFor(() => expect(screen.getByText("Coffee shop")).toBeInTheDocument());
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("renders shared session video when available", async () => {
    const { api } = await import("../api/client.js");
    api.getSharedSession.mockResolvedValue(SHARED);
    setup();
    const video = await screen.findByLabelText("scene video");
    expect(video).toHaveAttribute("src", "https://oss.example/cover.mp4");
    expect(video).toHaveAttribute("poster", "https://oss.example/cover.jpg");
    expect(video.closest(".session-practice-media")).toHaveClass("session-detail-video");
    expect(video.closest(".detail-hero-media")).toBeNull();
  });

  it("renders an unattempted shared practice as a playable prompt preview", async () => {
    const { api } = await import("../api/client.js");
    api.getSharedSession.mockResolvedValue({ ...SHARED, attempts: [] });
    setup();
    const video = await screen.findByLabelText("scene video");
    expect(video.closest(".session-practice-media")).toBeInTheDocument();
    expect(screen.getByText("You are ordering coffee before work.")).toBeInTheDocument();
    expect(screen.getByText("Ask for a latte")).toBeInTheDocument();
  });

  it("shows a friendly message when the share is closed", async () => {
    const { api } = await import("../api/client.js");
    api.getSharedSession.mockRejectedValue(new Error("404"));
    setup();
    await waitFor(() =>
      expect(screen.getByText("This share is closed or doesn't exist")).toBeInTheDocument(),
    );
  });
});
