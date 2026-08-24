import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import SentenceCorrectionList from "./SentenceCorrectionList.jsx";

vi.mock("../SpeakBtn.jsx", () => ({ default: () => <button>standard audio</button> }));
vi.mock("../RecordingPlayBtn.jsx", () => ({ default: () => <button>my recording</button> }));

const t = (key) => ({
  "practice.sentenceComparison": "逐句对照",
  "practice.youSaid": "你说的",
  "practice.nativeVersion": "纠正版",
}[key] || key);

describe("SentenceCorrectionList", () => {
  it("pairs each source sentence above its correction by sourceId", () => {
    render(
      <SentenceCorrectionList
        practiceId="p1"
        recordingUrl="blob:recording"
        result={{
          nativeVersion: "I need help. Could you call an ambulance? Please hurry.",
          sentenceCorrections: [
            { sourceId: 0, original: "I need helps.", corrected: "I need help." },
            {
              sourceId: 1,
              original: "You call ambulance?",
              corrected: "Could you call an ambulance? Please hurry.",
            },
          ],
        }}
        transcript="I need helps. You call ambulance?"
        t={t}
      />,
    );
    const pairs = document.querySelectorAll(".fb-sentence-pair");
    expect(pairs).toHaveLength(2);
    expect(within(pairs[0]).getByText("I need helps.")).toBeInTheDocument();
    expect(within(pairs[0]).getByText("I need help.")).toBeInTheDocument();
    expect(within(pairs[1]).getByText("You call ambulance?")).toBeInTheDocument();
    expect(within(pairs[1]).getByText("Could you call an ambulance? Please hurry.")).toBeInTheDocument();
    expect(screen.getByText("逐句对照")).toBeInTheDocument();
  });

  it("keeps old results readable as one original/correction pair", () => {
    render(
      <SentenceCorrectionList
        result={{ nativeVersion: "I went there yesterday." }}
        transcript="I go there yesterday."
        t={t}
      />,
    );
    expect(screen.getByText("I go there yesterday.")).toBeInTheDocument();
    expect(screen.getByText("I went there yesterday.")).toBeInTheDocument();
  });
});
