/** Resolve a result URL to one stable Attempt and its canonical pa_ URL state. */
export function resolveRequestedAttempt(attempts, searchParams) {
  const requested = searchParams.get("attempt") || "";
  const legacyRound = Number(requested);
  let attempt = null;

  if (requested) {
    attempt = attempts.find((item) => (
      item.attemptId === requested || item._id === requested
    )) || (Number.isInteger(legacyRound) && legacyRound > 0
      ? attempts[legacyRound - 1]
      : null);
  } else if (searchParams.get("result") && attempts.length > 0) {
    attempt = attempts[attempts.length - 1];
  }

  if (!attempt) return null;
  const attemptId = attempt.attemptId || attempt._id;
  return {
    attempt,
    attemptId,
    round: attempt.round || attempts.indexOf(attempt) + 1,
    shouldReplace: requested !== attemptId,
  };
}
