import { track } from "../lib/analytics.js";

// 场景标量：只上报不透明 ID 与分层标量，不带提示正文/作答正文（隐私边界见 docs/业务/数据埋点.md）
function scenarioProps(active) {
  const scenario = active?.scenario || {};
  return {
    practiceId: active?._id || "",
    sourceType: active?.sourceType || "",
    interactionType: scenario.interactionType || "standard",
    kind: scenario.kind || "",
    difficulty: scenario.difficulty ?? null,
  };
}

export function trackPracticeResult({ active, result, round, userId, attemptId = '', hintCount = 0 }) {
  track("practice_result", {
    mode: active.mode === "free" ? "free" : "scenario",
    score: result.score ?? null,
    gaps: (result.gaps ?? []).length,
    round,
    userId,
    attemptId,
    hintCount: hintCount || 0,
    ...scenarioProps(active),
  });
}

export function trackPracticeRecordingStarted(active, userId, hintCount = 0) {
  track("practice_recording_started", {
    mode: active?.mode === "free" ? "free" : "scenario",
    userId,
    hintCount: hintCount || 0,
    ...scenarioProps(active),
  });
}
