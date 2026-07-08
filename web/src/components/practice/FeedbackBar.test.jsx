import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

import FeedbackBar from "./FeedbackBar.jsx";
import { UserProvider } from "../../context/UserContext.jsx";

vi.mock("../../api/client.js", () => ({
  api: { submitFeedback: vi.fn() },
}));

const USER = { userId: "u_test1", phone: "13800001234", nickname: "Test" };
const SNAPSHOT = { score: 7.5, summary: "good", nativeVersion: "Hi there.", gaps: [], transcript: "hi", round: 1 };

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

describe("FeedbackBar", () => {
  beforeEach(async () => {
    localStorage.clear();
    vi.clearAllMocks();
    const { api } = await import("../../api/client.js");
    api.submitFeedback.mockResolvedValue({});
  });

  it("renders nothing without practiceId", () => {
    setup({ practiceId: undefined });
    expect(screen.queryByText("Was this AI feedback helpful?")).not.toBeInTheDocument();
  });

  it("submits good with empty tags and snapshot, then locks", async () => {
    const { api } = await import("../../api/client.js");
    setup();
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
    // 锁定：thanks 出现，👍/👎 消失
    expect(screen.getByText("Thanks - it helps us improve")).toBeInTheDocument();
    expect(screen.queryByLabelText("Helpful")).not.toBeInTheDocument();
  });

  it("expands reason tags on thumbs-down and submits bad with selected tags", async () => {
    const { api } = await import("../../api/client.js");
    setup();
    await userEvent.click(screen.getByLabelText("Not helpful"));
    await userEvent.click(screen.getByText("Score too strict"));
    await userEvent.click(screen.getByText("Corrections inaccurate"));
    await userEvent.type(screen.getByPlaceholderText(/What was wrong/), "score weird");
    await userEvent.click(screen.getByText("Submit"));

    await waitFor(() => expect(api.submitFeedback).toHaveBeenCalled());
    const call = api.submitFeedback.mock.calls[0][0];
    expect(call.rating).toBe("bad");
    expect(call.tags).toEqual(["score_too_strict", "gap_wrong"]);
    expect(call.comment).toBe("score weird");
  });

  it("shows error message when submit fails", async () => {
    const { api } = await import("../../api/client.js");
    api.submitFeedback.mockRejectedValue(new Error("net"));
    setup();
    await userEvent.click(screen.getByLabelText("Helpful"));
    await waitFor(() => expect(screen.getByText("Failed to submit, please try again")).toBeInTheDocument());
    // 失败后仍可重试：按钮还在
    expect(screen.getByLabelText("Helpful")).toBeInTheDocument();
  });
});
