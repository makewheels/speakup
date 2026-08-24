import { track } from "../lib/analytics.js";

export function trackPracticeResult(active, result, round, userId) {
  track("practice_result", {
    mode: active.mode === "free" ? "free" : "scenario",
    score: result.score ?? null,
    gaps: (result.gaps ?? []).length,
    round,
    userId,
  });
}

export function trackPracticeRecordingStarted(mode, userId) {
  track("practice_recording_started", { mode, userId });
}
