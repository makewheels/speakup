const storageKey = (userId) => `skipped:${userId}`;

export function readSkippedScenarios(userId) {
  try {
    return JSON.parse(sessionStorage.getItem(storageKey(userId)) || "[]");
  } catch {
    return [];
  }
}

export function writeSkippedScenarios(userId, scenarioIds) {
  sessionStorage.setItem(storageKey(userId), JSON.stringify(scenarioIds));
}
