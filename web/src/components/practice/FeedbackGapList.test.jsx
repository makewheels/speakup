import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import FeedbackGapList from "./FeedbackGapList.jsx";
import { buildT } from "../../i18n/i18n-core.js";
import { LangContext } from "../../i18n/lang-context.js";

const GAP = {
  category: "grammar",
  title: "Use the past tense",
  original: "I go there yesterday.",
  better: "I went there yesterday.",
  why: "The event happened in the past.",
  chinese: "我昨天去了那里。",
  example: "I met her last weekend.",
  exampleChinese: "我上周末见到了她。",
};

describe("FeedbackGapList", () => {
  it("keeps the correction core together and moves the bilingual example into details", async () => {
    render(<FeedbackGapList canSpeak={false} gaps={[GAP]} practiceId="practice_1" />);

    expect(screen.getByText("Grammar")).toBeInTheDocument();
    expect(screen.getByText("Use the past tense")).toBeInTheDocument();
    expect(screen.queryByText("Meaning")).not.toBeInTheDocument();
    expect([...document.querySelectorAll(".fb-gap-tag")].map((node) => node.textContent)).toEqual([
      "You said",
      "Say this",
      "Why",
    ]);

    const summary = screen.getByText("Show example & translation");
    const details = summary.closest("details");
    expect(details).not.toHaveAttribute("open");
    await userEvent.click(summary);
    expect(details).toHaveAttribute("open");
    expect(screen.getByText(GAP.example)).toBeInTheDocument();
    expect(screen.getByText(GAP.exampleChinese)).toBeInTheDocument();
  });

  it("uses complete Chinese result labels in Chinese mode", () => {
    const t = buildT("zh-CN");
    render(
      <LangContext.Provider value={{ lang: "zh-CN", setLang: () => {}, t }}>
        <FeedbackGapList canSpeak={false} gaps={[GAP]} practiceId="practice_1" />
      </LangContext.Provider>,
    );

    expect(screen.getByText("差距 · 1 处")).toBeInTheDocument();
    expect(screen.getByText("语法")).toBeInTheDocument();
    expect([...document.querySelectorAll(".fb-gap-tag")].map((node) => node.textContent)).toEqual([
      "你说",
      "这样说",
      "为什么",
    ]);
    expect(t("practice.youSaid")).toBe("你说的");
    expect(t("practice.nativeVersion")).toBe("纠正版");
    expect(t("practice.standardAnswer")).toBe("标准答案");
  });

  it("can omit its title when a parent disclosure already provides it", () => {
    render(
      <FeedbackGapList
        canSpeak={false}
        gaps={[GAP]}
        practiceId="practice_1"
        showTitle={false}
      />,
    );

    expect(screen.queryByText("Gaps · 1")).not.toBeInTheDocument();
    expect(screen.getByText("Use the past tense")).toBeInTheDocument();
  });
});
