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
