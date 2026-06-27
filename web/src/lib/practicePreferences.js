export const DEFAULT_PRACTICE_PREFERENCES = {
  level: "daily",
  purpose: "openup",
};

export const LEVEL_OPTIONS = ["beginner", "daily", "advanced", "challenge"];
export const PURPOSE_OPTIONS = ["openup", "travel", "work", "expression", "review"];

const PREFIX = "speakup-practice-preferences";

const keyFor = (userId) => `${PREFIX}:${userId || "default"}`;

export function isValidPracticePreferences(value) {
  return (
    value &&
    LEVEL_OPTIONS.includes(value.level) &&
    PURPOSE_OPTIONS.includes(value.purpose)
  );
}

export function hasPracticePreferences(userId) {
  return isValidPracticePreferences(getPracticePreferences(userId, null));
}

export function getPracticePreferences(userId, fallback = DEFAULT_PRACTICE_PREFERENCES) {
  try {
    const raw = localStorage.getItem(keyFor(userId));
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return isValidPracticePreferences(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

export function savePracticePreferences(userId, prefs) {
  const next = isValidPracticePreferences(prefs) ? prefs : DEFAULT_PRACTICE_PREFERENCES;
  localStorage.setItem(keyFor(userId), JSON.stringify(next));
  return next;
}
