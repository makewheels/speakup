import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import ReviewPage from "./ReviewPage.jsx";
import { UserProvider } from "../context/UserContext.jsx";

vi.mock("../api/client.js", () => ({
  api: {
    listReviewItems: vi.fn(),
    reviewItem: vi.fn(),
    restoreReviewItem: vi.fn(),
    translateReviewItem: vi.fn(),
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
  chinese: "能帮我看看吗？",
  contextSentence: "Could you take a look at this for me?",
  status: "active",
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
  chinese: "我赶时间",
  contextSentence: "",
  status: "active",
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
  chinese: "让我想想",
  contextSentence: "",
  status: "active",
  reviewCount: 5,
  interval: 10,
  nextReviewAt: futureDate,
};

const ITEM_RETIRED = {
  _id: "rv4",
  userId: "u_rv",
  expression: "No worries",
  original: "it's ok ok",
  note: "",
  chinese: "没关系",
  contextSentence: "",
  status: "retired",
  reviewCount: 1,
  interval: 1,
  nextReviewAt: pastDate,
};

function setup() {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  return render(
    <MemoryRouter initialEntries={["/review"]}>
      <UserProvider>
        <Routes>
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/practice/:practiceId" element={<div>Practice session</div>} />
        </Routes>
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

  it("card front shows the chinese prompt, never the user's wrong version", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    setup();
    await waitFor(() =>
      expect(screen.getByText("能帮我看看吗？")).toBeInTheDocument(),
    );
    expect(screen.getByText("Say it in English")).toBeInTheDocument();
    // 错误版本不应再出现（避免加深印象）
    expect(screen.queryByText("you see this")).not.toBeInTheDocument();
  });

  it("reveals answer on card tap without showing the wrong version", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    setup();
    await waitFor(() => screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("能帮我看看吗？"));
    await waitFor(() =>
      expect(screen.getByText("Could you take a look?")).toBeInTheDocument(),
    );
    expect(screen.queryByText("you see this")).not.toBeInTheDocument();
  });

  it("shows context sentence after reveal", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    setup();
    await waitFor(() => screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("能帮我看看吗？"));
    await waitFor(() =>
      expect(screen.getByText("Could you take a look at this for me?")).toBeInTheDocument(),
    );
  });

  it("lazily translates legacy items missing chinese", async () => {
    const { api } = await import("../api/client.js");
    const legacy = { ...ITEM_DUE, chinese: "" };
    api.listReviewItems.mockResolvedValue([legacy]);
    api.translateReviewItem.mockResolvedValue({ chinese: "能帮我看看吗？" });
    setup();
    await waitFor(() =>
      expect(api.translateReviewItem).toHaveBeenCalledWith("rv1", USER.userId),
    );
    await waitFor(() =>
      expect(screen.getByText("能帮我看看吗？")).toBeInTheDocument(),
    );
  });

  it("shows fallback text when lazy translation fails", async () => {
    const { api } = await import("../api/client.js");
    const legacy = { ...ITEM_DUE, chinese: "" };
    api.listReviewItems.mockResolvedValue([legacy]);
    api.translateReviewItem.mockResolvedValue({ chinese: "" });
    setup();
    await waitFor(() =>
      expect(screen.getByText("Prompt unavailable — tap to see the answer")).toBeInTheDocument(),
    );
  });

  it("'Got it' retires the item and calls reviewItem(true)", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE]);
    api.reviewItem.mockResolvedValue({ ...ITEM_DUE, status: "retired" });
    setup();
    await waitFor(() => screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("能帮我看看吗？")); // reveal
    await waitFor(() => screen.getByText("Got it"));
    await userEvent.click(screen.getByText("Got it"));
    await waitFor(() =>
      expect(api.reviewItem).toHaveBeenCalledWith("rv1", USER.userId, true),
    );
    // 收纳后卡片正面换成下一项的中文提示词
    await waitFor(() =>
      expect(screen.getByText("我赶时间")).toBeInTheDocument(),
    );
    expect(screen.queryByText("能帮我看看吗？")).not.toBeInTheDocument();
  });

  it("'Not yet' keeps the item and calls reviewItem(false)", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE]);
    api.reviewItem.mockResolvedValue({});
    setup();
    await waitFor(() => screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("能帮我看看吗？")); // reveal
    await waitFor(() => screen.getByText("Not yet"));
    await userEvent.click(screen.getByText("Not yet"));
    await waitFor(() =>
      expect(api.reviewItem).toHaveBeenCalledWith("rv1", USER.userId, false),
    );
  });

  it("shows 'Done for now' with archived count when all cards reviewed", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    api.reviewItem.mockResolvedValue({ ...ITEM_DUE, status: "retired" });
    setup();
    await waitFor(() => screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("能帮我看看吗？"));
    await waitFor(() => screen.getByText("Got it"));
    await userEvent.click(screen.getByText("Got it"));
    await waitFor(() =>
      expect(screen.getByText("Done for now")).toBeInTheDocument(),
    );
    expect(screen.getByText("1 mastered & archived")).toBeInTheDocument();
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
    await waitFor(() => screen.getByText(/Say it in English/));
    expect(screen.getByText("能帮我看看吗？")).toBeInTheDocument();
  });

  it("retired-only user sees the done screen, not empty state", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_RETIRED]);
    setup();
    await waitFor(() =>
      expect(screen.getByText("Done for now")).toBeInTheDocument(),
    );
    expect(screen.queryByText("No review items yet")).not.toBeInTheDocument();
  });
});

describe("ReviewPage list view", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
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

  it("shows chinese prompt + expression but never the wrong version", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE]);
    setup();
    await waitFor(() => screen.getByText(/All \d/));
    await userEvent.click(screen.getByText(/All \d/));
    await waitFor(() => {
      expect(screen.getByText("Could you take a look?")).toBeInTheDocument();
      expect(screen.getByText("I'm in a rush")).toBeInTheDocument();
      expect(screen.getByText("能帮我看看吗？")).toBeInTheDocument();
    });
    expect(screen.queryByText("you see this")).not.toBeInTheDocument();
    expect(screen.queryByText("I hurry")).not.toBeInTheDocument();
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

  it("archived section lists retired items and restores them", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_RETIRED]);
    api.restoreReviewItem.mockResolvedValue({ ...ITEM_RETIRED, status: "active" });
    setup();
    await waitFor(() => screen.getByText(/All \d/));
    await userEvent.click(screen.getByText(/All \d/));

    await waitFor(() => screen.getByText("Archived 1"));
    await userEvent.click(screen.getByText("Archived 1"));
    await waitFor(() =>
      expect(screen.getByText("No worries")).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByText("Restore"));
    await waitFor(() =>
      expect(api.restoreReviewItem).toHaveBeenCalledWith("rv4", USER.userId),
    );
    // 恢复后回到活动列表：已收纳区消失，恢复项带 Due 状态（nextReviewAt 已到期）
    await waitFor(() =>
      expect(screen.queryByText("Archived 1")).not.toBeInTheDocument(),
    );
    expect(screen.getAllByText("Due")).toHaveLength(2);
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
      expect(screen.getByText("Say it in English")).toBeInTheDocument(),
    );
  });
});

describe("ReviewPage practice-word regressions", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("'Practice this word' creates a practice session and navigates to it", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    api.practiceWord.mockResolvedValue({ scenarioId: "sc_word" });
    api.createPractice.mockResolvedValue({ _id: "ps_word" });
    setup();
    await waitFor(() => screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("Practice this word"));

    await waitFor(() => expect(screen.getByText("Practice session")).toBeInTheDocument());
    expect(api.practiceWord).toHaveBeenCalledWith(USER.userId, ITEM_DUE.expression, ITEM_DUE.original);
    expect(api.createPractice).toHaveBeenCalledWith({ userId: USER.userId, scenarioId: "sc_word" });
  });

  it("'Practice this word' shows an alert and stays on review when scenario creation fails", async () => {
    const { api } = await import("../api/client.js");
    vi.spyOn(window, "alert").mockImplementation(() => {});
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    api.practiceWord.mockRejectedValue(new Error("boom"));
    setup();
    await waitFor(() => screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("Practice this word"));

    await waitFor(() =>
      expect(window.alert).toHaveBeenCalledWith("Failed to create scenario: boom"),
    );
    expect(screen.getByText("Answer")).toBeInTheDocument();
    expect(screen.queryByText("Practice session")).not.toBeInTheDocument();
  });
});
