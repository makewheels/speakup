import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildShareText, copyShare, shareOrCopy, shareUrl } from "./share.js";

const SESSION = {
  title: "Coffee shop",
  topic: "Coffee shop · Seattle",
  attempts: [{ score: 6.0 }, { score: 7.5 }],
};

describe("lib/share", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { location: { origin: "https://speak.example" } });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shareUrl builds /s/<token> from current origin", () => {
    expect(shareUrl("tok_1")).toBe("https://speak.example/s/tok_1");
  });

  it("buildShareText includes title, latest score and link", () => {
    const text = buildShareText(SESSION, "tok_1");
    expect(text).toContain('"Coffee shop"');
    expect(text).toContain("IELTS 7.5"); // 取最新一轮
    expect(text).toContain("https://speak.example/s/tok_1");
  });

  it("buildShareText omits score when absent", () => {
    const text = buildShareText({ title: "X", attempts: [{}] }, "t");
    expect(text).not.toContain("IELTS");
    expect(text).toContain('"X"');
  });

  it("buildShareText falls back to a default title", () => {
    const text = buildShareText({ attempts: [] }, "t");
    expect(text).toContain("speaking practice");
  });

  it("copyShare writes the share text to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("window", { location: { origin: "https://speak.example" } });
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const text = await copyShare(SESSION, "tok_1");
    expect(writeText).toHaveBeenCalledWith(text);
    expect(text).toContain("https://speak.example/s/tok_1");
  });

  it("uses the mobile share sheet when Web Share is available", async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    const writeText = vi.fn();
    vi.stubGlobal("navigator", { share, clipboard: { writeText } });

    await expect(shareOrCopy(SESSION, "tok_1")).resolves.toBe("shared");
    expect(share).toHaveBeenCalledWith({ text: expect.stringContaining("/s/tok_1") });
    expect(writeText).not.toHaveBeenCalled();
  });

  it("falls back to copying when the share sheet fails", async () => {
    const share = vi.fn().mockRejectedValue(new Error("not supported here"));
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { share, clipboard: { writeText } });

    await expect(shareOrCopy(SESSION, "tok_1")).resolves.toBe("copied");
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("/s/tok_1"));
  });

  it("does not copy when the user cancels the share sheet", async () => {
    const error = new Error("cancelled");
    error.name = "AbortError";
    const share = vi.fn().mockRejectedValue(error);
    const writeText = vi.fn();
    vi.stubGlobal("navigator", { share, clipboard: { writeText } });

    await expect(shareOrCopy(SESSION, "tok_1")).resolves.toBe("cancelled");
    expect(writeText).not.toHaveBeenCalled();
  });
});
