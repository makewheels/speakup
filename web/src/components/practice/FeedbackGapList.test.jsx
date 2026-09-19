import { render, screen } from "@testing-library/react";
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
  it("renders each gap as You said / Say this / Why, without the retired example block", () => {
    render(<FeedbackGapList canSpeak={false} gaps={[GAP]} practiceId="practice_1" />);

    expect(screen.getByText("Grammar")).toBeInTheDocument();
    expect(screen.getByText("Use the past tense")).toBeInTheDocument();
    expect(screen.queryByText("Meaning")).not.toBeInTheDocument();
    expect([...document.querySelectorAll(".fb-gap-tag")].map((node) => node.textContent)).toEqual([
      "You said",
      "Say this",
      "Why",
    ]);
    // 「See it in a different situation」已下线：历史数据带 example 也不渲染
    expect(screen.queryByText(GAP.example)).not.toBeInTheDocument();
    expect(screen.queryByText(GAP.exampleChinese)).not.toBeInTheDocument();
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
    expect(t("practice.expressionSuggestions")).toBe("表达建议");
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
