import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

import FeedbackPage from "./FeedbackPage.jsx";
import { UserProvider } from "../context/UserContext.jsx";

vi.mock("../api/client.js", () => ({
  api: { submitFeedback: vi.fn() },
}));

const USER = { userId: "u_test1", phone: "13800001234", nickname: "Test" };

function setup() {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  return render(
    <MemoryRouter>
      <UserProvider>
        <FeedbackPage />
      </UserProvider>
    </MemoryRouter>,
  );
}

describe("FeedbackPage", () => {
  beforeEach(async () => {
    localStorage.clear();
    vi.clearAllMocks();
    const { api } = await import("../api/client.js");
    api.submitFeedback.mockResolvedValue({});
  });

  it("disables submit when nothing entered", () => {
    setup();
    expect(screen.getByText("Send feedback").closest("button")).toBeDisabled();
  });

  it("submits general feedback with selected tag and comment", async () => {
    const { api } = await import("../api/client.js");
    setup();
    await userEvent.click(screen.getByText("Bug"));
    await userEvent.type(screen.getByPlaceholderText(/Tell us more/), "mic button dead");
    await userEvent.click(screen.getByText("Send feedback"));

    await waitFor(() => expect(api.submitFeedback).toHaveBeenCalled());
    const call = api.submitFeedback.mock.calls[0][0];
    expect(call.type).toBe("general");
    expect(call.tags).toEqual(["bug"]);
    expect(call.comment).toBe("mic button dead");
  });

  it("shows thanks after submit", async () => {
    setup();
    await userEvent.click(screen.getByText("Bug"));
    await userEvent.click(screen.getByText("Send feedback"));

    await waitFor(() => expect(screen.getByText(/Got your feedback/)).toBeInTheDocument());
  });

  it("allows image-only feedback and submits all selected originals", async () => {
    const { api } = await import("../api/client.js");
    const { container } = setup();
    const files = [
      new File(["one"], "one.png", { type: "image/png" }),
      new File(["two"], "two.jpg", { type: "image/jpeg" }),
    ];
    await userEvent.upload(container.querySelector('input[type="file"]'), files);
    await userEvent.click(screen.getByText("Send feedback"));

    await waitFor(() => expect(api.submitFeedback).toHaveBeenCalledWith(
      expect.objectContaining({ type: "general", comment: "" }),
      files,
    ));
  });
});
