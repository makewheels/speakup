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
  imageUrl: "https://oss.example/cover.jpg",
  videoUrl: "https://oss.example/cover.mp4",
  createdAt: "2026-06-01T10:00:00Z",
  ownerNickname: "Alice",
  attempts: [
    { round: 1, transcript: "I tried to order", nativeVersion: "I attempted to place an order.", score: 6.5, gaps: [] },
  ],
  recordings: [],
};

function setup(token = "tok_1") {
  return render(
    <MemoryRouter initialEntries={[`/s/${token}`]}>
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
      expect(screen.getByText("I tried to order")).toBeInTheDocument();
    });
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
