import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

import FeedbackBar from "./FeedbackBar.jsx";
import { UserProvider } from "../../context/UserContext.jsx";

vi.mock("../../api/client.js", () => ({
  api: { submitFeedback: vi.fn(), listMyFeedbacks: vi.fn() },
}));

const USER = { userId: "u_test1", phone: "13800001234", nickname: "Test" };
const SNAPSHOT = { score: 7.5, summary: "good", gaps: [], transcript: "hi", round: 1 };

function setup(props) {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  return render(
    <MemoryRouter>
      <UserProvider>
        <FeedbackBar practiceId="sess_abc" attemptIndex={0} snapshot={SNAPSHOT} {...props} />
      </UserProvider>
    </MemoryRouter>,
  );
}

async function openFeedback() {
  const trigger = await screen.findByRole("button", { name: "Give feedback on this result" });
  await userEvent.click(trigger);
}

// submitFeedback 在 beforeEach 里 mock 成回显提交数据（模拟后端 upsert 返回）

describe("FeedbackBar", () => {
  beforeEach(async () => {
    localStorage.clear();
    vi.clearAllMocks();
    const { api } = await import("../../api/client.js");
    api.listMyFeedbacks.mockResolvedValue([]); // 默认未反馈
    api.submitFeedback.mockImplementation(async (data) => ({
      _id: "fb_new",
      type: data.type,
      rating: data.rating,
      tags: data.tags,
      comment: data.comment,
      practiceId: data.practiceId,
      attemptIndex: data.attemptIndex,
      snapshot: data.snapshot,
    }));
  });

  it("renders nothing without practiceId", () => {
    setup({ practiceId: undefined });
    expect(screen.queryByText("Was this AI feedback helpful?")).not.toBeInTheDocument();
  });

  it("uses a short action label in the result footer and still expands", async () => {
    setup({ compact: true });
    const trigger = await screen.findByRole("button", { name: "Feedback" });
    await userEvent.click(trigger);
    expect(await screen.findByText("Was this AI feedback helpful?")).toBeInTheDocument();
  });

  it("submits good and enters submitted state (locks thumbs)", async () => {
    const { api } = await import("../../api/client.js");
    setup();
    await openFeedback();
    await waitFor(() => expect(screen.getByLabelText("Helpful")).toBeInTheDocument());
    await userEvent.click(screen.getByLabelText("Helpful"));

    await waitFor(() => expect(api.submitFeedback).toHaveBeenCalled());
    const call = api.submitFeedback.mock.calls[0][0];
    expect(call).toMatchObject({
      type: "practice",
      rating: "good",
      tags: [],
      comment: "",
      practiceId: "sess_abc",
      attemptIndex: 0,
    });
    expect(call.snapshot).toEqual(SNAPSHOT);
    // 提交后自动收起，只有结果反馈按钮留在页面上。
    expect(screen.getByRole("button", { name: "Feedback sent · view or edit" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Helpful")).not.toBeInTheDocument();
  });

  it("shows comment box before any rating and submits good with the comment", async () => {
    const { api } = await import("../../api/client.js");
    setup();
    await openFeedback();
    const box = await screen.findByPlaceholderText(/Anything to add/);
    await userEvent.type(box, "很有帮助，但希望多给例句");
    await userEvent.click(screen.getByLabelText("Helpful"));

    await waitFor(() => expect(api.submitFeedback).toHaveBeenCalled());
    const call = api.submitFeedback.mock.calls[0][0];
    expect(call).toMatchObject({
      type: "practice",
      rating: "good",
      tags: [],
      comment: "很有帮助，但希望多给例句",
    });
    await userEvent.click(screen.getByRole("button", { name: "Feedback sent · view or edit" }));
    expect(screen.getByText("很有帮助，但希望多给例句")).toBeInTheDocument();
  });

  it("expands reason tags on thumbs-down and submits bad with selected tags", async () => {
    const { api } = await import("../../api/client.js");
    setup();
    await openFeedback();
    await waitFor(() => expect(screen.getByLabelText("Not helpful")).toBeInTheDocument());
    await userEvent.click(screen.getByLabelText("Not helpful"));
    await userEvent.click(screen.getByText("Score too strict"));
    await userEvent.click(screen.getByText("Corrections inaccurate"));
    await userEvent.type(screen.getByPlaceholderText(/Anything to add/), "score weird");
    await userEvent.click(screen.getByText("Submit"));

    await waitFor(() => expect(screen.getByRole("button", { name: "Feedback sent · view or edit" })).toBeInTheDocument());
    const call = api.submitFeedback.mock.calls[0][0];
    expect(call.rating).toBe("bad");
    expect(call.tags).toEqual(["score_too_strict", "gap_wrong"]);
    expect(call.comment).toBe("score weird");
    await userEvent.click(screen.getByRole("button", { name: "Feedback sent · view or edit" }));
    expect(screen.getByText("Score too strict")).toBeInTheDocument();
    expect(screen.getByText("score weird")).toBeInTheDocument();
  });

  it("shows error message when submit fails, keeps thumbs for retry", async () => {
    const { api } = await import("../../api/client.js");
    api.submitFeedback.mockRejectedValue(new Error("net"));
    setup();
    await openFeedback();
    await waitFor(() => expect(screen.getByLabelText("Helpful")).toBeInTheDocument());
    await userEvent.click(screen.getByLabelText("Helpful"));
    await waitFor(() => expect(screen.getByText("Failed to submit, please try again")).toBeInTheDocument());
    expect(screen.getByLabelText("Helpful")).toBeInTheDocument();
  });

  it("loads existing feedback and shows it with edit button", async () => {
    const { api } = await import("../../api/client.js");
    api.listMyFeedbacks.mockResolvedValue([
      {
        _id: "fb_1", type: "practice", rating: "bad",
        tags: ["score_too_strict"], comment: "太严了",
        practiceId: "sess_abc", attemptIndex: 0,
      },
    ]);
    setup();
    const trigger = await screen.findByRole("button", { name: "Feedback sent · view or edit" });
    await userEvent.click(trigger);
    await waitFor(() => expect(screen.getByText("Edit")).toBeInTheDocument());
    expect(screen.getByText("Score too strict")).toBeInTheDocument();
    expect(screen.getByText("太严了")).toBeInTheDocument();
    // 不在 thumbs 态
    expect(screen.queryByLabelText("Helpful")).not.toBeInTheDocument();
  });

  it("edit reopens thumbs and resubmit updates the feedback", async () => {
    const { api } = await import("../../api/client.js");
    api.listMyFeedbacks.mockResolvedValue([
      { _id: "fb_1", type: "practice", rating: "good", tags: [], comment: "", practiceId: "sess_abc", attemptIndex: 0 },
    ]);
    setup();
    await userEvent.click(await screen.findByRole("button", { name: "Feedback sent · view or edit" }));
    await waitFor(() => expect(screen.getByText("Edit")).toBeInTheDocument());
    await userEvent.click(screen.getByText("Edit"));

    // 回到 thumbs，改成 bad
    await waitFor(() => expect(screen.getByLabelText("Not helpful")).toBeInTheDocument());
    await userEvent.click(screen.getByLabelText("Not helpful"));
    await userEvent.click(screen.getByText("Submit"));

    await waitFor(() => expect(api.submitFeedback).toHaveBeenCalled());
    expect(api.submitFeedback.mock.calls[0][0].rating).toBe("bad");
    // 回到已反馈态
    expect(screen.getByRole("button", { name: "Feedback sent · view or edit" })).toBeInTheDocument();
  });
});
