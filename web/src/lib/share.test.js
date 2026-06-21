import { describe, it, expect, vi, beforeEach } from "vitest";
import { shareUrl, buildShareText, copyShare } from "./share.js";

const SESSION = {
  title: "Coffee shop",
  topic: "Coffee shop · Seattle",
  attempts: [{ score: 6.0 }, { score: 7.5 }],
};

describe("lib/share", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { location: { origin: "https://speak.example" } });
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
});
