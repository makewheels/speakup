export const EMPTY_FEEDBACK = {
  summary: "", standardAnswer: "", standardAnswerNotes: [],
  score: null, gaps: [], progress: null,
};

export const hasUsableFeedback = (result) => Boolean(
  (result?.standardAnswer || "").trim()
  || (result?.gaps ?? []).length > 0
  || result?.score != null
  || result?.progress
);

export function reviewMapFromGaps(gaps = []) {
  const saved = {};
  gaps.forEach((gap, index) => { if (gap.reviewItemId) saved[index] = gap.reviewItemId; });
  return saved;
}

export function resultFromAttempt(attempt) {
  return {
    summary: attempt.summary,
    standardAnswer: attempt.standardAnswer ?? "",
    standardAnswerNotes: attempt.standardAnswerNotes ?? [],
    note: attempt.note ?? "",
    noteChinese: attempt.noteChinese ?? "",
    score: attempt.score,
    gaps: attempt.gaps ?? [],
    progress: attempt.progress ?? null,
  };
}
