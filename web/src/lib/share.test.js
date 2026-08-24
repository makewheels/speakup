import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { copyShareLink, shareUrl } from "./share.js";

describe("lib/share", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { location: { origin: "https://speak.example" } });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shareUrl builds /s/<token> from current origin", () => {
    expect(shareUrl("tok_1")).toBe("https://speak.example/s/tok_1");
    expect(shareUrl("tok_1", "pa_2")).toBe("https://speak.example/s/tok_1?attempt=pa_2");
  });

  it("copyShareLink writes only the public URL to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const url = await copyShareLink("tok_1");
    expect(writeText).toHaveBeenCalledWith("https://speak.example/s/tok_1");
    expect(url).toBe("https://speak.example/s/tok_1");
  });

  it("copyShareLink can target one attempt", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    await copyShareLink("tok_1", "pa_2");
    expect(writeText).toHaveBeenCalledWith("https://speak.example/s/tok_1?attempt=pa_2");
  });
});
