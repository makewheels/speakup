const MAX_CONTEXT_LENGTH = 500;

const normalizeSelection = (value = "") => value.replace(/\s+/g, " ").trim();

export function selectionFrom(root, selection) {
  if (!root || !selection || selection.isCollapsed || !selection.anchorNode || !selection.focusNode) {
    return null;
  }
  if (!root.contains(selection.anchorNode) || !root.contains(selection.focusNode)) return null;

  const text = normalizeSelection(selection.toString());
  if (!text) return null;

  const anchor = selection.anchorNode.nodeType === Node.ELEMENT_NODE
    ? selection.anchorNode
    : selection.anchorNode.parentElement;
  const contextNode = anchor?.closest?.("[data-note-context]");
  const contextSentence = normalizeSelection(
    contextNode && root.contains(contextNode)
      ? (contextNode.dataset.noteContext || contextNode.textContent)
      : root.textContent,
  ).slice(0, MAX_CONTEXT_LENGTH);

  return { text, contextSentence };
}

export function selectionAnchorFrom(selection) {
  if (!selection || selection.rangeCount < 1 || typeof selection.getRangeAt !== "function") {
    return null;
  }
  const range = selection.getRangeAt(0);
  const rects = typeof range.getClientRects === "function"
    ? Array.from(range.getClientRects()).filter((rect) => rect.width || rect.height)
    : [];
  const rect = rects.at(-1)
    || (typeof range.getBoundingClientRect === "function" ? range.getBoundingClientRect() : null);
  if (!rect || !Number.isFinite(rect.left) || !Number.isFinite(rect.top)) return null;
  return {
    left: rect.left + (rect.width / 2),
    top: rect.top,
    bottom: rect.bottom,
  };
}
