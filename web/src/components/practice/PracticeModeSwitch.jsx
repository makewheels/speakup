/**
 * 练习模式切换：场景题 / 自由说。纯展示组件，状态在 PracticePage。
 * Props: mode ("scenario" | "free"), onSwitch(mode), t
 */
export default function PracticeModeSwitch({ mode, onSwitch, t }) {
  return (
    <div className="mode-switch" role="tablist" aria-label={t("practice.modeScenario")}>
      <button
        type="button"
        role="tab"
        aria-selected={mode !== "free"}
        className={"mode-switch-btn" + (mode !== "free" ? " active" : "")}
        onClick={() => onSwitch("scenario")}
      >
        {t("practice.modeScenario")}
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={mode === "free"}
        className={"mode-switch-btn" + (mode === "free" ? " active" : "")}
        onClick={() => onSwitch("free")}
      >
        {t("practice.modeFree")}
      </button>
    </div>
  );
}
