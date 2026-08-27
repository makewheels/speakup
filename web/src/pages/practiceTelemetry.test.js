import { describe, it, expect, vi, beforeEach } from "vitest";

import { trackPracticeRecordingStarted, trackPracticeResult } from "./practiceTelemetry.js";

vi.mock("../lib/analytics.js", () => ({ track: vi.fn() }));

const SESSION = {
  _id: "sess_p1",
  sourceType: "human",
  mode: "scenario",
  scenario: {
    kind: "task",
    interactionType: "progressive_hints",
    difficulty: 2,
  },
};

describe("practiceTelemetry", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
  });

  it("录音开始事件带去重 ID、交互类型、难度与提示计数", async () => {
    const { track } = await import("../lib/analytics.js");
    trackPracticeRecordingStarted(SESSION, "u1", 1);
    expect(track).toHaveBeenCalledWith("practice_recording_started", expect.objectContaining({
      mode: "scenario",
      userId: "u1",
      practiceId: "sess_p1",
      sourceType: "human",
      interactionType: "progressive_hints",
      kind: "task",
      difficulty: 2,
      hintCount: 1,
    }));
  });

  it("standard/free 缺省归一：interactionType=standard、hintCount=0", async () => {
    const { track } = await import("../lib/analytics.js");
    trackPracticeRecordingStarted({ _id: "sess_f", mode: "free", scenario: { kind: "free" } }, "u1");
    expect(track).toHaveBeenCalledWith("practice_recording_started", expect.objectContaining({
      mode: "free",
      interactionType: "standard",
      hintCount: 0,
    }));
  });

  it("结果事件带 attemptId 与提示计数，且不含提示正文", async () => {
    const { track } = await import("../lib/analytics.js");
    trackPracticeResult({
      active: SESSION, result: { score: 6.5, gaps: [1, 2] }, round: 2, userId: "u1", attemptId: "pa_9", hintCount: 2,
    });
    const [event, props] = track.mock.calls[0];
    expect(event).toBe("practice_result");
    expect(props).toMatchObject({
      attemptId: "pa_9",
      practiceId: "sess_p1",
      interactionType: "progressive_hints",
      hintCount: 2,
      score: 6.5,
      gaps: 2,
      round: 2,
    });
    // 隐私边界：只有计数/标量，没有提示正文键
    expect(props).not.toHaveProperty("hints");
    expect(props).not.toHaveProperty("story");
    expect(props).not.toHaveProperty("transcript");
  });
});
