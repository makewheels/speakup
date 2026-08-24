import { describe, expect, it } from "vitest";

import { resolveRequestedAttempt } from "./practiceAttemptRouting.js";

const ATTEMPTS = [
  { _id: "pa_one", attemptId: "pa_one", round: 1 },
  { _id: "pa_two", attemptId: "pa_two", round: 2 },
];

describe("resolveRequestedAttempt", () => {
  it("resolves a stable Attempt id without rewriting it", () => {
    const result = resolveRequestedAttempt(ATTEMPTS, new URLSearchParams("attempt=pa_one"));
    expect(result).toMatchObject({ attemptId: "pa_one", round: 1, shouldReplace: false });
  });

  it("canonicalizes legacy numeric and result URLs", () => {
    expect(resolveRequestedAttempt(ATTEMPTS, new URLSearchParams("attempt=2")))
      .toMatchObject({ attemptId: "pa_two", round: 2, shouldReplace: true });
    expect(resolveRequestedAttempt(ATTEMPTS, new URLSearchParams("result=1")))
      .toMatchObject({ attemptId: "pa_two", round: 2, shouldReplace: true });
  });
});
