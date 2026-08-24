import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SelectableNoteText from "./SelectableNoteText.jsx";

vi.mock("../../api/client.js", () => ({
  api: { addReviewItems: vi.fn() },
}));

describe("SelectableNoteText", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../../api/client.js");
    api.addReviewItems.mockResolvedValue({ added: 1, ids: ["review_1"] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("saves only the text selected by the user as a manual note", async () => {
    render(
      <SelectableNoteText practiceId="practice_1" userId="user_1">
        <p data-note-context="I would like a coffee, please.">I would like a coffee, please.</p>
      </SelectableNoteText>,
    );

    const paragraph = screen.getByText("I would like a coffee, please.");
    const selection = {
      anchorNode: paragraph.firstChild,
      focusNode: paragraph.firstChild,
      isCollapsed: false,
      removeAllRanges: vi.fn(),
      toString: () => "would like",
    };
    vi.spyOn(window, "getSelection").mockReturnValue(selection);

    fireEvent.mouseUp(paragraph);
    await userEvent.click(screen.getByRole("button", { name: /Add to Notes/i }));

    const { api } = await import("../../api/client.js");
    await waitFor(() => expect(api.addReviewItems).toHaveBeenCalledWith("user_1", [{
      kind: "note",
      attemptIndex: -1,
      expression: "would like",
      original: "",
      note: "",
      chinese: "",
      contextSentence: "I would like a coffee, please.",
      practiceId: "practice_1",
    }]));
    expect(selection.removeAllRanges).toHaveBeenCalled();
    expect(screen.getByText("Noted")).toBeInTheDocument();
  });

  it("does not expose note actions on a public read-only result", () => {
    render(
      <SelectableNoteText practiceId="practice_1" userId="">
        <p>Public answer</p>
      </SelectableNoteText>,
    );

    fireEvent.mouseUp(screen.getByText("Public answer"));
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });
});
