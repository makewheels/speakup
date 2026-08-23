import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const MAX_STYLE_LINES = 500;

export function countPhysicalLines(source) {
  if (!source) return 0;
  const lines = source.split(/\r\n|\r|\n/).length;
  return /(?:\r\n|\r|\n)$/.test(source) ? lines - 1 : lines;
}

async function listCssFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...await listCssFiles(entryPath));
    } else if (entry.isFile() && entry.name.endsWith(".css")) {
      files.push(entryPath);
    }
  }

  return files.sort();
}

export async function inspectStyleLines(rootDirectory, limit = MAX_STYLE_LINES) {
  const files = await listCssFiles(rootDirectory);
  const oversized = [];

  for (const file of files) {
    const source = await readFile(file, "utf8");
    const lines = countPhysicalLines(source);
    if (lines > limit) {
      oversized.push({
        file: path.relative(rootDirectory, file),
        lines,
      });
    }
  }

  return { files, oversized };
}

async function main() {
  const sourceRoot = fileURLToPath(new URL("../src/", import.meta.url));
  const { files, oversized } = await inspectStyleLines(sourceRoot);

  if (oversized.length > 0) {
    console.error(`CSS physical line limit exceeded (max ${MAX_STYLE_LINES}):`);
    for (const item of oversized) {
      console.error(`- ${item.file}: ${item.lines} lines`);
    }
    process.exitCode = 1;
    return;
  }

  console.log(`CSS line check passed: ${files.length} files <= ${MAX_STYLE_LINES} physical lines`);
}

const invokedUrl = process.argv[1]
  ? pathToFileURL(path.resolve(process.argv[1])).href
  : "";

if (import.meta.url === invokedUrl) {
  await main();
}
