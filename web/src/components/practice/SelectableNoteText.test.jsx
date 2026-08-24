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
      attemptId: "",
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

  it("anchors the toolbar to a touch selection and preserves it while the button is pressed", async () => {
    render(
      <SelectableNoteText practiceId="practice_1" userId="user_1">
        <p data-note-context="A sharp pain after eating.">A sharp pain after eating.</p>
      </SelectableNoteText>,
    );
    const paragraph = screen.getByText("A sharp pain after eating.");
    let liveSelection = {
      anchorNode: paragraph.firstChild,
      focusNode: paragraph.firstChild,
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({
        getClientRects: () => [{ left: 42, top: 120, bottom: 142, width: 80, height: 22 }],
      }),
      removeAllRanges: vi.fn(),
      toString: () => "sharp pain",
    };
    vi.spyOn(window, "getSelection").mockImplementation(() => liveSelection);

    fireEvent.touchEnd(paragraph);
    const toolbar = await screen.findByRole("toolbar");
    expect(toolbar).toHaveClass("is-anchored");
    expect(toolbar.style.getPropertyValue("--note-selection-left")).toBe("82px");

    const button = screen.getByRole("button", { name: /Add to Notes/i });
    fireEvent.pointerDown(button);
    liveSelection = null;
    document.dispatchEvent(new Event("selectionchange"));
    await userEvent.click(button);

    const { api } = await import("../../api/client.js");
    await waitFor(() => expect(api.addReviewItems).toHaveBeenCalledWith("user_1", [
      expect.objectContaining({ expression: "sharp pain", contextSentence: "A sharp pain after eating." }),
    ]));
  });
});
