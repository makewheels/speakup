import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

import ReviewPage from "./ReviewPage.jsx";
import { UserProvider } from "../context/UserContext.jsx";

vi.mock("../api/client.js", () => ({
  api: {
    listReviewItems: vi.fn(),
    reviewItem: vi.fn(),
    practiceWord: vi.fn(),
    createPractice: vi.fn(),
    deleteReviewItem: vi.fn(),
  },
}));

vi.mock("../utils/tts.js", () => ({
  speak: vi.fn().mockResolvedValue(null),
  stop: vi.fn(),
  isCached: vi.fn().mockReturnValue(false),
}));

const USER = { userId: "u_rv", phone: "13800000001", nickname: "Reviewer" };

const now = new Date();
const pastDate = new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000).toISOString(); // 2 days ago
const futureDate = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000).toISOString(); // future

const ITEM_DUE = {
  _id: "rv1",
  userId: "u_rv",
  expression: "Could you take a look?",
  original: "you see this",
  note: "More polite request",
  contextSentence: "Could you take a look at this for me?",
  reviewCount: 1,
  interval: 1,
  nextReviewAt: pastDate,
};

const ITEM_NOT_DUE = {
  _id: "rv2",
  userId: "u_rv",
  expression: "I'm in a rush",
  original: "I hurry",
  note: "More natural",
  contextSentence: "",
  reviewCount: 1,
  interval: 3,
  nextReviewAt: futureDate,
};

const ITEM_MASTERED = {
  _id: "rv3",
  userId: "u_rv",
  expression: "Let me think about it",
  original: "I think",
  note: "Natural stall phrase",
  contextSentence: "",
  reviewCount: 5,
  interval: 10,
  nextReviewAt: futureDate,
};

function setup() {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  return render(
    <MemoryRouter>
      <UserProvider>
        <ReviewPage />
      </UserProvider>
    </MemoryRouter>,
  );
}

describe("ReviewPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("shows loading while fetching", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockReturnValue(new Promise(() => {}));
    setup();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows empty state when no review items", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([]);
    setup();
    await waitFor(() =>
      expect(screen.getByText("No review items yet")).toBeInTheDocument(),
    );
  });

  it("renders card with expression and original", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    setup();
    await waitFor(() =>
      expect(screen.getByText("you see this")).toBeInTheDocument(),
    );
    // Before revealing answer, shows "You said" side
    expect(screen.getByText("What you said")).toBeInTheDocument();
  });

  it("reveals native version on card tap", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    setup();
    await waitFor(() => screen.getByText("you see this"));
    await userEvent.click(screen.getByText("you see this"));
    await waitFor(() =>
      expect(screen.getByText("Could you take a look?")).toBeInTheDocument(),
    );
  });

  it("shows context sentence after reveal", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    setup();
    await waitFor(() => screen.getByText("you see this"));
    await userEvent.click(screen.getByText("you see this"));
    await waitFor(() =>
      expect(screen.getByText("Could you take a look at this for me?")).toBeInTheDocument(),
    );
  });

  it("'Got it' advances to next card and calls reviewItem(true)", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE]);
    api.reviewItem.mockResolvedValue({});
    setup();
    await waitFor(() => screen.getByText("you see this"));
    await userEvent.click(screen.getByText("you see this")); // reveal
    await waitFor(() => screen.getByText("Got it"));
    await userEvent.click(screen.getByText("Got it"));
    await waitFor(() =>
      expect(api.reviewItem).toHaveBeenCalledWith("rv1", USER.userId, true),
    );
  });

  it("'Forgot' advances to next card and calls reviewItem(false)", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE]);
    api.reviewItem.mockResolvedValue({});
    setup();
    await waitFor(() => screen.getByText("you see this"));
    await userEvent.click(screen.getByText("you see this")); // reveal
    await waitFor(() => screen.getByText("Forgot"));
    await userEvent.click(screen.getByText("Forgot"));
    await waitFor(() =>
      expect(api.reviewItem).toHaveBeenCalledWith("rv1", USER.userId, false),
    );
  });

  it("shows 'Done for now' when all cards reviewed", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    api.reviewItem.mockResolvedValue({});
    setup();
    await waitFor(() => screen.getByText("you see this"));
    await userEvent.click(screen.getByText("you see this"));
    await waitFor(() => screen.getByText("Got it"));
    await userEvent.click(screen.getByText("Got it"));
    await waitFor(() =>
      expect(screen.getByText("Done for now")).toBeInTheDocument(),
    );
  });

  it("shows progress counter", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE]);
    setup();
    await waitFor(() =>
      expect(screen.getByText("1 / 2")).toBeInTheDocument(),
    );
  });

  it("due items appear before non-due items in queue", async () => {
    const { api } = await import("../api/client.js");
    // Pass in non-due first, due second — due should be shown first
    api.listReviewItems.mockResolvedValue([ITEM_NOT_DUE, ITEM_DUE]);
    setup();
    await waitFor(() => screen.getByText(/What you said/));
    // ITEM_DUE's original should be shown first
    expect(screen.getByText("you see this")).toBeInTheDocument();
  });

  it("switches to list view when 'All N' is clicked", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE]);
    setup();
    await waitFor(() => screen.getByText(/All \d/));
    await userEvent.click(screen.getByText(/All \d/));
    await waitFor(() =>
      expect(screen.getByText("All review items")).toBeInTheDocument(),
    );
  });

  it("shows all items in list view", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE]);
    setup();
    await waitFor(() => screen.getByText(/All \d/));
    await userEvent.click(screen.getByText(/All \d/));
    await waitFor(() => {
      expect(screen.getByText("Could you take a look?")).toBeInTheDocument();
      expect(screen.getByText("I'm in a rush")).toBeInTheDocument();
    });
  });

  it("shows Due / Learning / Mastered status chip", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE, ITEM_MASTERED]);
    setup();
    await waitFor(() => screen.getByText(/All \d/));
    await userEvent.click(screen.getByText(/All \d/));
    await waitFor(() => {
      expect(screen.getByText("Due")).toBeInTheDocument();
      expect(screen.getByText("Learning")).toBeInTheDocument();
      expect(screen.getByText("Mastered")).toBeInTheDocument();
    });
  });

  it("delete requires two taps (confirm pattern)", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    api.deleteReviewItem.mockResolvedValue({});
    setup();
    await waitFor(() => screen.getByText(/All \d/));
    await userEvent.click(screen.getByText(/All \d/));

    // First tap → "Confirm" label appears
    const delBtn = screen.getByLabelText("Delete");
    await userEvent.click(delBtn);
    expect(screen.getByText("Confirm")).toBeInTheDocument();
    expect(api.deleteReviewItem).not.toHaveBeenCalled();

    // Second tap → actually deletes
    await userEvent.click(screen.getByText("Confirm"));
    await waitFor(() =>
      expect(api.deleteReviewItem).toHaveBeenCalledWith("rv1", USER.userId),
    );
  });

  it("switches back to cards view from list view", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    setup();
    await waitFor(() => screen.getByText(/All \d/));
    await userEvent.click(screen.getByText(/All \d/));
    await waitFor(() => screen.getByText("Flashcards"));
    await userEvent.click(screen.getByText("Flashcards"));
    await waitFor(() =>
      expect(screen.getByText("What you said")).toBeInTheDocument(),
    );
  });
});
