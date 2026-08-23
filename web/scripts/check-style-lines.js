import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const MAX_SOURCE_LINES = 500;
export const CHECKED_EXTENSIONS = [".css", ".js", ".jsx", ".ts", ".tsx"];

export function countPhysicalLines(source) {
  if (!source) return 0;
  const lines = source.split(/\r\n|\r|\n/).length;
  return /(?:\r\n|\r|\n)$/.test(source) ? lines - 1 : lines;
}

async function listSourceFiles(directory, extensions) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...await listSourceFiles(entryPath, extensions));
    } else if (entry.isFile() && extensions.includes(path.extname(entry.name))) {
      files.push(entryPath);
    }
  }

  return files.sort();
}

export async function inspectSourceLines(rootDirectory, limit = MAX_SOURCE_LINES, extensions = CHECKED_EXTENSIONS) {
  const files = await listSourceFiles(rootDirectory, extensions);
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
  const webRoot = fileURLToPath(new URL("../", import.meta.url));
  const scanRoots = [path.join(webRoot, "src"), path.join(webRoot, "scripts")];
  const allFiles = [];
  const oversized = [];

  for (const root of scanRoots) {
    const result = await inspectSourceLines(root);
    allFiles.push(...result.files.map((file) => path.relative(webRoot, path.join(root, file))));
    oversized.push(...result.oversized.map((item) => ({
      ...item,
      file: path.relative(webRoot, path.join(root, item.file)),
    })));
  }

  if (oversized.length > 0) {
    console.error(`Source physical line limit exceeded (max ${MAX_SOURCE_LINES}):`);
    for (const item of oversized.sort((a, b) => a.file.localeCompare(b.file))) {
      console.error(`- ${item.file}: ${item.lines} lines`);
    }
    process.exitCode = 1;
    return;
  }

  console.log(`Source line check passed: ${allFiles.length} files <= ${MAX_SOURCE_LINES} physical lines`);
}

const invokedUrl = process.argv[1]
  ? pathToFileURL(path.resolve(process.argv[1])).href
  : "";

if (import.meta.url === invokedUrl) {
  await main();
}
