import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PronunciationFeedback from "./PronunciationFeedback.jsx";

vi.mock("../SpeakBtn.jsx", () => ({ default: ({ text }) => <button>say {text}</button> }));

const labels = {
  "practice.pronunciationSuggestions": "发音建议",
  "practice.pronunciationLoading": "正在分析",
  "practice.pronunciationUnavailable": "暂时不可用",
  "practice.pronunciationGood": "发音很好",
  "practice.playMyPronunciation": "播放我的发音",
  "practice.soundComparison": "音素对照",
};
const t = (key) => labels[key] || key;

describe("PronunciationFeedback", () => {
  it("shows a compact loading card while the provider request is pending", () => {
    render(<PronunciationFeedback loading t={t} />);
    expect(screen.getByText("发音建议")).toBeInTheDocument();
    expect(screen.getByText("正在分析")).toBeInTheDocument();
  });

  it("shows detected and target phones with coaching", () => {
    render(
      <PronunciationFeedback
        pronunciation={{
          status: "completed",
          overallScore: 73,
          issues: [{
            word: "happy", score: 64, startMs: 200, endMs: 650,
            detectedIpa: "hepi", referenceIpa: "hæpi",
            phones: [{ detected: "e", reference: "æ" }],
            coaching: "先听标准音，再慢速跟读。",
          }],
        }}
        recordingUrl="recording.webm"
        practiceId="p1"
        t={t}
      />,
    );
    expect(screen.getByText("73 / 100")).toBeInTheDocument();
    expect(screen.getByText("happy")).toBeInTheDocument();
    expect(screen.getByText("/e/", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("先听标准音，再慢速跟读。")).toBeInTheDocument();
  });
});
