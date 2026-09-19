import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import PracticeFeedbackView from "./PracticeFeedbackView.jsx";
import { buildT } from "../../i18n/i18n-core.js";
import { LangContext } from "../../i18n/lang-context.js";

// 只保留本次要验的骨架：子区块各自有测试，这里用空实现隔离掉
vi.mock("./FeedbackGapList.jsx", () => ({ default: () => null }));
vi.mock("./PracticeMedia.jsx", () => ({ default: () => null }));
vi.mock("./PracticeScenarioCard.jsx", () => ({ default: () => null }));
vi.mock("./PracticeFreeCard.jsx", () => ({ default: () => null }));
vi.mock("./StandardAnswerCard.jsx", () => ({ default: () => null }));
vi.mock("./ResultFooterActions.jsx", () => ({ default: () => null }));
vi.mock("./SelectableNoteText.jsx", () => ({ default: ({ children }) => <>{children}</> }));

const RESULT = {
  summary: "整体不错",
  score: 6.5,
  standardAnswer: "",
  standardAnswerNotes: [],
  gaps: [],
  progress: null,
};

const TRANSCRIPT = "Can you redo my latte";

function renderView(overrides = {}) {
  const t = buildT("en");
  const props = {
    attemptId: "pa_1",
    chat: [],
    chatBusy: false,
    chatInput: "",
    loading: false,
    onShare: vi.fn(),
    result: RESULT,
    retrySame: vi.fn(),
    round: 1,
    savedMap: {},
    scenario: null,
    sendChat: vi.fn(),
    session: { _id: "sess_1", mode: "scenario" },
    setChatInput: vi.fn(),
    startNewRound: vi.fn(),
    t,
    toggleGap: vi.fn(),
    transcript: TRANSCRIPT,
    userId: "u_1",
    ...overrides,
  };
  return render(
    <LangContext.Provider value={{ lang: "en", setLang: () => {}, t }}>
      <PracticeFeedbackView {...props} />
    </LangContext.Provider>,
  );
}

describe("PracticeFeedbackView", () => {
  it("首轮不挂轮次徽章，第 2 轮起才显示", () => {
    const first = renderView({ round: 1 });
    expect(screen.queryByText("Attempt #1")).not.toBeInTheDocument();
    first.unmount();

    renderView({ round: 2 });
    expect(screen.getByText("Attempt #2")).toBeInTheDocument();
  });

  it("「你说的」默认折叠，展开后显示原话并渲染原声播放器", async () => {
    renderView({ recordingUrl: "blob:local-recording" });

    const summary = screen.getByText("You said");
    const details = summary.closest("details");
    expect(details).not.toHaveAttribute("open");  // 默认折叠（内容仍在 DOM，由 details 控制显隐）

    await userEvent.click(summary);

    expect(details).toHaveAttribute("open");
    expect(screen.getByText(TRANSCRIPT)).toBeInTheDocument();
    expect(document.querySelector(".rec-player")).toBeTruthy();
  });

  it("没有可用录音时只显示原话，不渲染播放器", async () => {
    renderView({ recordingUrl: "" });

    await userEvent.click(screen.getByText("You said"));

    expect(screen.getByText(TRANSCRIPT)).toBeInTheDocument();
    expect(document.querySelector(".rec-player")).toBeNull();
  });

  it("没有原话时不渲染「你说的」区块", () => {
    renderView({ transcript: "" });

    expect(screen.queryByText("You said")).not.toBeInTheDocument();
  });

  it("重说区带独立样式类，与上方追问区靠分割线区分", () => {
    renderView();

    expect(document.querySelector(".actions-row.fb-actions")).toBeTruthy();
  });
});
