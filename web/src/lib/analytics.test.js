import { describe, expect, it, vi } from "vitest";

import { initAnalytics, track } from "./analytics.js";

describe("analytics", () => {
  it("track is a no-op without umami loaded", () => {
    expect(() => track("some_event", { a: 1 })).not.toThrow();
  });

  it("track forwards to window.umami when present", () => {
    const spy = vi.fn();
    window.umami = { track: spy };
    track("practice_result", { score: 6.5 });
    expect(spy).toHaveBeenCalledWith("practice_result", { score: 6.5 });
    delete window.umami;
  });

  it("initAnalytics does not inject the script outside production", () => {
    initAnalytics();
    expect(document.querySelector("script[data-website-id]")).toBeNull();
  });
});
