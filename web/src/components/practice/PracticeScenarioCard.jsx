// 去掉文本里的 emoji（旧场景数据的 where/points 可能带 emoji，统一不显示）
const stripEmoji = (s = "") =>
  s
    .replace(/[\u{1F000}-\u{1FAFF}]/gu, "")
    .replace(/[\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}]/gu, "")
    .replace(/[\u{FE00}-\u{FE0F}\u{200D}]/gu, "")
    .replace(/^[\s·•・]+/, "")
    .replace(/\s{2,}/g, " ")
    .trim();

export default function PracticeScenarioCard({ scenario, topic, t }) {
  const points = scenario?.points ?? [];
  const where = stripEmoji(scenario?.where || topic || t("practice.scene_default"));
  return (
    <div className="sc-card">
      <div className="sc-grid">
        <div className="sc-k">{t("practice.place")}</div>
        <div className="sc-v sc-v-where">{where}</div>

        {scenario?.story && <>
          <div className="sc-k">{t("practice.scene")}</div>
          <div className="sc-v">{stripEmoji(scenario.story)}</div>
        </>}

        <div className="sc-k say">{t("practice.goal")}</div>
        <div className="sc-v say">
          {points.length > 0 ? (
            <ul className="sc-points">
              {points.map((p, i) => <li key={i}>{stripEmoji(p)}</li>)}
            </ul>
          ) : (
            <span className="sc-say-text">{stripEmoji(scenario?.mission || "")}</span>
          )}
        </div>
      </div>
    </div>
  );
}
