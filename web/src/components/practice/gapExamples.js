function words(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLocaleLowerCase("en")
    .match(/[\p{L}\p{N}]+/gu) || [];
}

export function hasDistinctExample(better, example) {
  const betterWords = words(better);
  const exampleWords = words(example);
  if (!exampleWords.length) return false;
  if (!betterWords.length) return true;
  if (betterWords.join(" ") === exampleWords.join(" ")) return false;

  const remaining = new Map();
  for (const word of betterWords) remaining.set(word, (remaining.get(word) || 0) + 1);
  let overlap = 0;
  for (const word of exampleWords) {
    const count = remaining.get(word) || 0;
    if (!count) continue;
    overlap += 1;
    remaining.set(word, count - 1);
  }
  const shorterLength = Math.min(betterWords.length, exampleWords.length);
  const nearCopy = shorterLength >= 4
    && overlap / shorterLength >= 0.9
    && Math.abs(betterWords.length - exampleWords.length) <= 2;
  return !nearCopy;
}
