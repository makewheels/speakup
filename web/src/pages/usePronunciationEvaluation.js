import { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";

export const EMPTY_FEEDBACK = {
  summary: "", nativeVersion: "", sentenceCorrections: [], standardAnswer: "",
  score: null, gaps: [], progress: null,
};

export const hasUsableFeedback = (result) => Boolean(
  (result?.nativeVersion || "").trim()
  || (result?.sentenceCorrections ?? []).length > 0
  || (result?.standardAnswer || "").trim()
  || (result?.gaps ?? []).length > 0,
);

export function reviewMapFromGaps(gaps = []) {
  const saved = {};
  gaps.forEach((gap, index) => { if (gap.reviewItemId) saved[index] = gap.reviewItemId; });
  return saved;
}

export function resultFromAttempt(attempt) {
  return {
    summary: attempt.summary,
    nativeVersion: attempt.nativeVersion,
    sentenceCorrections: attempt.sentenceCorrections ?? [],
    standardAnswer: attempt.standardAnswer ?? "",
    note: attempt.note ?? "",
    noteChinese: attempt.noteChinese ?? "",
    score: attempt.score,
    gaps: attempt.gaps ?? [],
    progress: attempt.progress ?? null,
  };
}

export default function usePronunciationEvaluation() {
  const [pronunciation, setPronunciation] = useState(null);
  const [pronunciationLoading, setPronunciationLoading] = useState(false);
  const requestRef = useRef(0);

  useEffect(() => () => { requestRef.current += 1; }, []);

  const resetPronunciation = () => {
    requestRef.current += 1;
    setPronunciation(null);
    setPronunciationLoading(false);
  };

  const evaluateRecording = async ({ audioBlob, practiceId, userId, attemptIndex }) => {
    if (!audioBlob || !practiceId) return;
    const requestId = ++requestRef.current;
    try {
      const upload = await api.uploadRecording(practiceId, userId, audioBlob, attemptIndex);
      if (!upload.pronunciationEnabled || requestRef.current !== requestId) return;
      setPronunciationLoading(true);
      const result = await api.evaluatePronunciation(practiceId, attemptIndex);
      if (requestRef.current === requestId) setPronunciation(result);
    } catch (error) {
      console.warn("Pronunciation evaluation unavailable:", error);
      if (requestRef.current === requestId) setPronunciation({ status: "failed" });
    } finally {
      if (requestRef.current === requestId) setPronunciationLoading(false);
    }
  };

  return {
    evaluateRecording,
    pronunciation,
    pronunciationLoading,
    resetPronunciation,
    restorePronunciation: setPronunciation,
  };
}
