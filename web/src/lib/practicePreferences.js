export const DEFAULT_PRACTICE_PREFERENCES = {
  level: "daily",
  purpose: "travel",
};

export const LEVEL_OPTIONS = ["beginner", "daily", "advanced", "challenge"];
export const PURPOSE_OPTIONS = ["travel", "work", "ielts", "toefl", "dailyLife"];

const LEGACY_PURPOSE_MAP = {
  openup: "dailyLife",
  expression: "ielts",
  exam: "ielts",
  review: "dailyLife",
};

const PREFIX = "speakup-practice-preferences";

const keyFor = (userId) => `${PREFIX}:${userId || "default"}`;

export function normalizePracticePreferences(value, fallback = DEFAULT_PRACTICE_PREFERENCES) {
  if (!value) return fallback;
  const purpose = LEGACY_PURPOSE_MAP[value.purpose] || value.purpose;
  const next = { level: value.level, purpose };
  return (
    LEVEL_OPTIONS.includes(next.level) &&
    PURPOSE_OPTIONS.includes(next.purpose)
  ) ? next : fallback;
}

export function isValidPracticePreferences(value) {
  return (
    normalizePracticePreferences(value, null) !== null
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
    return normalizePracticePreferences(parsed, fallback);
  } catch {
    return fallback;
  }
}

export function savePracticePreferences(userId, prefs) {
  const next = normalizePracticePreferences(prefs, DEFAULT_PRACTICE_PREFERENCES);
  localStorage.setItem(keyFor(userId), JSON.stringify(next));
  return next;
}
