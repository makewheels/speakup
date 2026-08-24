import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import StandardAnswerCard from "./StandardAnswerCard.jsx";

vi.mock("../SpeakBtn.jsx", () => ({
  default: ({ text }) => <button type="button" aria-label="play standard">play {text}</button>,
}));

const t = (key) => ({
  "practice.standardAnswer": "标准答案",
  "practice.standardAnswerNotes": "重点表达",
  "practice.viewStandardAnswer": "查看答案",
})[key] || key;

describe("StandardAnswerCard", () => {
  it("is expanded by default and playing never collapses the answer", async () => {
    const { container } = render(
      <StandardAnswerCard answer="Could I get a latte, please?" practiceId="p1" t={t} />,
    );
    const details = container.querySelector("details");
    const play = screen.getByRole("button", { name: "play standard" });
    const title = screen.getByRole("heading", { level: 2, name: "标准答案" });
    expect(title.closest("summary")).toBeNull();
    expect(play.closest("summary")).toBeNull();
    expect(details).toHaveAttribute("open");
    await userEvent.click(play);
    expect(details).toHaveAttribute("open");
  });

  it("renders key expression explanations when the independent answer provides them", () => {
    render(
      <StandardAnswerCard
        answer="I've had gastritis before, and I'm allergic to penicillin."
        notes={[
          {
            expression: "gastritis",
            chinese: "胃炎",
            explanation: "I've had ... before 用于说明既往病史。",
          },
          {
            expression: "allergic to penicillin",
            chinese: "对青霉素过敏",
            explanation: "be allergic to + 药物或食物。",
          },
        ]}
        canSpeak={false}
        t={t}
      />,
    );
    expect(screen.getByRole("heading", { level: 3, name: "重点表达" })).toBeInTheDocument();
    expect(screen.getByText("gastritis")).toBeInTheDocument();
    expect(screen.getByText("对青霉素过敏")).toBeInTheDocument();
  });
});
