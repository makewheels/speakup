// 指定题目 URL 不可用（不存在/已归档/无权）：明确提示并可返回，不静默换随机题。
export default function PracticeUnavailable({ modeSwitch, onBack, t }) {
  return (
    <div className="practice-page">
      {modeSwitch}
      <div className="sc-unavailable" role="alert">
        <p>{t("practice.scenarioUnavailable")}</p>
        <button className="su-btn su-btn-primary" onClick={onBack}>
          {t("practice.backToPractice")}
        </button>
      </div>
    </div>
  );
}
