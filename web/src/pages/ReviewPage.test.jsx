import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

import {
  USER,
  ITEM_DUE,
  ITEM_NOT_DUE,
  ITEM_MASTERED,
  ITEM_RETIRED,
  ITEM_NOTE,
  ITEM_EXTRA,
  setup,
} from "./ReviewPage.helpers.jsx";

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
    await waitFor(() => document.querySelector(".rv-list-toggle"));
    await userEvent.click(document.querySelector(".rv-list-toggle"));
    await waitFor(() =>
      expect(screen.getByText("All review items")).toBeInTheDocument(),
    );
  });

  it("shows chinese prompt + expression but never the wrong version", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE]);
    setup();
    await waitFor(() => document.querySelector(".rv-list-toggle"));
    await userEvent.click(document.querySelector(".rv-list-toggle"));
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
    await waitFor(() => document.querySelector(".rv-list-toggle"));
    await userEvent.click(document.querySelector(".rv-list-toggle"));
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
    await waitFor(() => document.querySelector(".rv-list-toggle"));
    await userEvent.click(document.querySelector(".rv-list-toggle"));

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
    await waitFor(() => document.querySelector(".rv-list-toggle"));
    await userEvent.click(document.querySelector(".rv-list-toggle"));

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
    await waitFor(() => document.querySelector(".rv-list-toggle"));
    await userEvent.click(document.querySelector(".rv-list-toggle"));
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

describe("ReviewPage quiz (温故而知新词卡出题)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("reveals a 4-choice quiz when enough items exist", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE, ITEM_EXTRA, ITEM_MASTERED]);
    setup();
    await waitFor(() => screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("能帮我看看吗？"));
    await waitFor(() =>
      expect(screen.getByText("Which one is correct?")).toBeInTheDocument(),
    );
    // 正确项 + 干扰项都在选项里（共 4 个）
    expect(screen.getByText("Could you take a look?")).toBeInTheDocument();
    expect(screen.getByText("I'm in a rush")).toBeInTheDocument();
    expect(document.querySelectorAll(".rv-quiz-opt")).toHaveLength(4);
  });

  it("correct pick archives on Next and calls reviewItem(true)", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE, ITEM_EXTRA, ITEM_MASTERED]);
    api.reviewItem.mockResolvedValue({});
    setup();
    await waitFor(() => screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("能帮我看看吗？"));
    await waitFor(() => screen.getByText("Which one is correct?"));
    await userEvent.click(screen.getByText("Could you take a look?")); // 选中正确项

    await waitFor(() =>
      expect(screen.getByText("Correct — archived ✓")).toBeInTheDocument(),
    );
    expect(api.reviewItem).toHaveBeenCalledWith("rv1", USER.userId, true);

    await userEvent.click(screen.getByText("Next"));
    // 收纳后展示下一张卡，当前项的中文提示不再出现
    await waitFor(() =>
      expect(screen.queryByText("能帮我看看吗？")).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("Correct — archived ✓")).not.toBeInTheDocument();
  });

  it("wrong pick keeps the item, highlights the answer, and Next advances", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE, ITEM_EXTRA, ITEM_MASTERED]);
    api.reviewItem.mockResolvedValue({});
    setup();
    await waitFor(() => screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("能帮我看看吗？"));
    await waitFor(() => screen.getByText("Which one is correct?"));
    await userEvent.click(screen.getByText("I'm in a rush")); // 选错

    await waitFor(() =>
      expect(screen.getByText("Not quite — keep at it")).toBeInTheDocument(),
    );
    expect(api.reviewItem).toHaveBeenCalledWith("rv1", USER.userId, false);
    const correct = document.querySelectorAll(".rv-quiz-opt.correct");
    expect(correct).toHaveLength(1);
    expect(correct[0]).toHaveTextContent("Could you take a look?");

    await userEvent.click(screen.getByText("Next"));
    await waitFor(() =>
      expect(screen.queryByText("Which one is correct?")).not.toBeInTheDocument(),
    );
  });

  it("falls back to reveal + self-grade when fewer than 4 items", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOT_DUE]);
    setup();
    await waitFor(() => screen.getByText("能帮我看看吗？"));
    await userEvent.click(screen.getByText("能帮我看看吗？"));
    await waitFor(() => expect(screen.getByText("Answer")).toBeInTheDocument());
    expect(screen.queryByText("Which one is correct?")).not.toBeInTheDocument();
    expect(screen.getByText("Got it")).toBeInTheDocument();
    expect(screen.getByText("Not yet")).toBeInTheDocument();
  });
});

describe("ReviewPage kind split (错题 / 笔记)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("shows kind filter chips with counts and filters the card queue", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOTE]);
    setup();
    // 三个过滤 chip（全部 / 错题 / 笔记），「All」文本与右上角列表入口相同，按类名断言
    await waitFor(() =>
      expect(document.querySelectorAll(".rv-kind-chip")).toHaveLength(3),
    );
    expect(screen.getByText("Mistakes 1")).toBeInTheDocument();
    expect(screen.getByText("Notes 1")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Notes 1"));
    await waitFor(() =>
      expect(screen.getByText("我可以")).toBeInTheDocument(),
    );
    expect(screen.queryByText("能帮我看看吗？")).not.toBeInTheDocument();
    // 卡片正面带「笔记」类别标签
    expect(screen.getByText("Notes", { selector: ".rv-kind-tag" })).toBeInTheDocument();
  });

  it("shows a hint when the filtered kind is empty", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE]);
    setup();
    await waitFor(() => screen.getByText("Notes 0"));
    await userEvent.click(screen.getByText("Notes 0"));
    await waitFor(() =>
      expect(screen.getByText("Nothing to review in this category yet")).toBeInTheDocument(),
    );
  });

  it("list view groups items into Mistakes / Notes sections", async () => {
    const { api } = await import("../api/client.js");
    api.listReviewItems.mockResolvedValue([ITEM_DUE, ITEM_NOTE]);
    setup();
    await waitFor(() => document.querySelector(".rv-list-toggle"));
    await userEvent.click(document.querySelector(".rv-list-toggle"));
    await waitFor(() => {
      expect(screen.getByText("Mistakes · 1")).toBeInTheDocument();
      expect(screen.getByText("Notes · 1")).toBeInTheDocument();
    });
  });
});
