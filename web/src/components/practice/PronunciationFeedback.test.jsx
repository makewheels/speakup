import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api/client.js";
import PronunciationFeedback from "./PronunciationFeedback.jsx";

vi.mock("../../api/client.js", () => ({
  api: {
    getPronunciationClip: vi.fn(),
    getSharedPronunciationClip: vi.fn(),
  },
}));
vi.mock("../SpeakBtn.jsx", () => ({
  default: ({ label, text }) => <button>{label || `say ${text}`}</button>,
}));

const labels = {
  "practice.pronunciationSuggestions": "发音建议",
  "practice.pronunciationLoading": "正在分析",
  "practice.pronunciationUnavailable": "暂时不可用",
  "practice.pronunciationGood": "发音很好",
  "practice.playMyPronunciation": "播放我的发音",
  "practice.soundComparison": "音素对照",
  "practice.yourSound": "你读成",
  "practice.targetSound": "目标音",
  "practice.listenMine": "听我的",
  "practice.listenTarget": "听标准",
  "practice.pronunciationSoundTip": "你读得更接近 {actual}；重点听 {target}，再慢速跟读。",
};
const t = (key, vars = {}) => (labels[key] || key).replace(
  /\{(\w+)\}/g, (_, name) => vars[name] ?? `{${name}}`,
);

describe("PronunciationFeedback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getPronunciationClip.mockResolvedValue(new Blob(["clip"], { type: "audio/wav" }));
    URL.createObjectURL = vi.fn(() => "blob:clip");
    URL.revokeObjectURL = vi.fn();
    HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  });

  it("shows a compact loading card while the provider request is pending", () => {
    render(<PronunciationFeedback loading t={t} />);
    expect(screen.getByText("发音建议")).toBeInTheDocument();
    expect(screen.getByText("正在分析")).toBeInTheDocument();
  });

  it("labels the comparison and plays a real server-side clip", async () => {
    render(
      <PronunciationFeedback
        attemptIndex={0}
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
        practiceId="p1"
        t={t}
      />,
    );
    expect(screen.getByText("73 / 100")).toBeInTheDocument();
    expect(screen.getByText("happy")).toBeInTheDocument();
    expect(screen.getByText("你读成")).toBeInTheDocument();
    expect(screen.getByText("目标音")).toBeInTheDocument();
    expect(screen.getByText("/hepi/")).toBeInTheDocument();
    expect(screen.getByText("/hæpi/")).toBeInTheDocument();
    expect(screen.getByText("你读得更接近 /e/；重点听 /æ/，再慢速跟读。")).toBeInTheDocument();
    expect(screen.getByText("听标准")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "听我的" }));
    await waitFor(() => expect(api.getPronunciationClip).toHaveBeenCalledWith("p1", 0, 0));
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });
});
