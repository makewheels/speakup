import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../api/client.js";
import Icon from "../Icon.jsx";
import { useT } from "../../i18n/useI18n.js";
import { selectionFrom } from "./noteSelection.js";

const MAX_NOTE_LENGTH = 500;

/**
 * 结果文字手动摘录：用户先用系统选区选中文字，再从底部浮条加入笔记。
 * 不调用 AI；后续解释能力可使用这里保留的 contextSentence 惰性生成。
 */
export default function SelectableNoteText({ children, practiceId, userId }) {
  const t = useT();
  const rootRef = useRef(null);
  const statusTimerRef = useRef(null);
  const [selection, setSelection] = useState(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const enabled = Boolean(practiceId && userId);

  const captureSelection = useCallback(() => {
    if (!enabled) {
      setSelection(null);
      return;
    }
    const next = selectionFrom(rootRef.current, window.getSelection?.());
    setSelection(next && next.text.length <= MAX_NOTE_LENGTH ? next : null);
    if (next?.text.length > MAX_NOTE_LENGTH) setStatus(t("practice.noteTooLong"));
  }, [enabled, t]);

  useEffect(() => {
    if (!enabled) return undefined;
    let frame = null;
    const onSelectionChange = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(captureSelection);
    };
    document.addEventListener("selectionchange", onSelectionChange);
    return () => {
      document.removeEventListener("selectionchange", onSelectionChange);
      cancelAnimationFrame(frame);
      clearTimeout(statusTimerRef.current);
    };
  }, [captureSelection, enabled]);

  const flash = (message) => {
    setStatus(message);
    clearTimeout(statusTimerRef.current);
    statusTimerRef.current = setTimeout(() => setStatus(""), 2200);
  };

  const saveSelection = async () => {
    if (!selection || !practiceId || !userId || saving) return;
    setSaving(true);
    try {
      const response = await api.addReviewItems(userId, [{
        kind: "note",
        expression: selection.text,
        original: "",
        note: "",
        chinese: "",
        contextSentence: selection.contextSentence,
        practiceId,
      }]);
      flash(response?.added === 0 ? t("practice.noteAlreadySaved") : t("practice.noteSaved"));
      window.getSelection?.()?.removeAllRanges?.();
      setSelection(null);
    } catch (error) {
      flash(t("practice.noteSaveFailed", { msg: error.message }));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div
        ref={rootRef}
        className="note-selectable-area"
        onMouseUp={captureSelection}
        onTouchEnd={() => setTimeout(captureSelection, 0)}
      >
        {children}
      </div>
      {selection && (
        <div className="note-selection-bar" role="toolbar" aria-label={t("practice.noteSelectionToolbar")}>
          <span className="note-selection-preview">“{selection.text}”</span>
          <button
            className="su-btn su-btn-primary"
            type="button"
            disabled={saving}
            onPointerDown={(event) => event.preventDefault()}
            onClick={saveSelection}
          >
            <Icon name="save" size={15} />
            {saving ? t("common.loadingDots") : t("practice.addSelectionToNotes")}
          </button>
        </div>
      )}
      {status && <div className="su-toast note-selection-toast" role="status">{status}</div>}
    </>
  );
}
