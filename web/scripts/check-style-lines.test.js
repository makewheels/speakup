import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { countPhysicalLines, inspectSourceLines } from "./check-style-lines.js";

const createdDirectories = [];

async function createTaskTempDirectory() {
  const directory = await mkdtemp(path.join(tmpdir(), "speakup-style-lines-"));
  createdDirectories.push(directory);
  return directory;
}

afterEach(async () => {
  const tempRoot = `${path.resolve(tmpdir())}${path.sep}`;
  for (const directory of createdDirectories.splice(0)) {
    const resolved = path.resolve(directory);
    if (!resolved.startsWith(tempRoot) || !path.basename(resolved).startsWith("speakup-style-lines-")) {
      throw new Error(`Refusing to clean unexpected path: ${resolved}`);
    }
    await rm(resolved, { recursive: true, force: true });
  }
});

describe("check-style-lines", () => {
  it("counts physical lines without inventing a line after the final newline", () => {
    expect(countPhysicalLines("")).toBe(0);
    expect(countPhysicalLines("a")).toBe(1);
    expect(countPhysicalLines("a\n")).toBe(1);
    expect(countPhysicalLines("a\n\n")).toBe(2);
    expect(countPhysicalLines("a\r\nb")).toBe(2);
  });

  it("reports only CSS files above the configured limit when scanning CSS only", async () => {
    const root = await createTaskTempDirectory();
    await mkdir(path.join(root, "nested"));
    await writeFile(path.join(root, "ok.css"), "a {}\n".repeat(3));
    await writeFile(path.join(root, "nested", "too-long.css"), "a {}\n".repeat(6));
    await writeFile(path.join(root, "ignored.js"), "x\n".repeat(20));

    const result = await inspectSourceLines(root, 5, [".css"]);

    expect(result.files).toHaveLength(2);
    expect(result.oversized).toEqual([
      { file: path.join("nested", "too-long.css"), lines: 6 },
    ]);
  });

  it("checks CSS, JS and JSX sources by default and skips other extensions", async () => {
    const root = await createTaskTempDirectory();
    await mkdir(path.join(root, "nested"));
    await writeFile(path.join(root, "ok.jsx"), "export default 1;\n".repeat(3));
    await writeFile(path.join(root, "nested", "too-long.js"), "x\n".repeat(6));
    await writeFile(path.join(root, "nested", "too-long.css"), "a {}\n".repeat(7));
    await writeFile(path.join(root, "ignored.md"), "x\n".repeat(30));

    const result = await inspectSourceLines(root, 5);

    expect(result.files).toHaveLength(3);
    expect(result.oversized).toEqual([
      { file: path.join("nested", "too-long.css"), lines: 7 },
      { file: path.join("nested", "too-long.js"), lines: 6 },
    ]);
  });
});
