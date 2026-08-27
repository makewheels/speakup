import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

import PracticeScenarioCard from "./PracticeScenarioCard.jsx";

const t = (key) => ({
  "practice.place": "地点",
  "practice.scene": "情境",
  "practice.goal": "任务",
  "practice.scene_default": "场景",
}[key] || key);

const STANDARD = {
  where: "咖啡店 · 西雅图",
  story: "店员把你的热拿铁做成了冰拿铁。",
  mission: "礼貌说明问题，请店员重做。",
  points: ["说明饮品做错了", "要求重做一杯热的"],
};

describe("PracticeScenarioCard", () => {
  it("standard 题沿用 points 优先展示", () => {
    render(<PracticeScenarioCard scenario={STANDARD} t={t} />);
    expect(screen.getByText("说明饮品做错了")).toBeInTheDocument();
    expect(screen.getByText("要求重做一杯热的")).toBeInTheDocument();
    expect(screen.queryByText("礼貌说明问题，请店员重做。")).not.toBeInTheDocument();
  });

  it("standard 题无 points 时展示 mission", () => {
    render(<PracticeScenarioCard scenario={{ ...STANDARD, points: [] }} t={t} />);
    expect(screen.getByText("礼貌说明问题，请店员重做。")).toBeInTheDocument();
  });

  it("渐进式题即使带 points 也只展示宽泛 mission", () => {
    render(
      <PracticeScenarioCard
        scenario={{ ...STANDARD, interactionType: "progressive_hints", hints: ["提示一", "提示二"] }}
        t={t}
      />,
    );
    expect(screen.getByText("礼貌说明问题，请店员重做。")).toBeInTheDocument();
    expect(screen.queryByText("说明饮品做错了")).not.toBeInTheDocument();
    expect(screen.queryByText("提示一")).not.toBeInTheDocument();
  });
});
