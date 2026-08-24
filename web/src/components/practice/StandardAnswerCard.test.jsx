import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import StandardAnswerCard from "./StandardAnswerCard.jsx";

vi.mock("../SpeakBtn.jsx", () => ({
  default: ({ text }) => <button type="button" aria-label="play standard">play {text}</button>,
}));

const t = (key) => ({ "practice.standardAnswer": "标准答案" })[key] || key;

describe("StandardAnswerCard", () => {
  it("keeps playback outside summary so playing never collapses the answer", async () => {
    const { container } = render(
      <StandardAnswerCard answer="Could I get a latte, please?" practiceId="p1" t={t} />,
    );
    const details = container.querySelector("details");
    const play = screen.getByRole("button", { name: "play standard" });
    expect(play.closest("summary")).toBeNull();

    await userEvent.click(screen.getByText("标准答案"));
    expect(details).toHaveAttribute("open");
    await userEvent.click(play);
    expect(details).toHaveAttribute("open");
  });
});
