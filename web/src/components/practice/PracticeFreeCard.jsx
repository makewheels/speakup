/**
 * 自由说话题卡片：英文话题 + 中文释义；无话题时显示「自由发挥」占位。
 * 纯展示组件。Props:
 *  - freeTopic: string（话题文本，空=无话题自由说）
 *  - zh: string（中文释义，可空；历史/结果页快照里没有 zh 时只显示英文）
 *  - t: i18n 函数
 */
export default function PracticeFreeCard({ freeTopic = "", zh = "", t }) {
  return (
    <div className="sc-card free-card">
      <div className="free-card-label">{t("practice.freeTopicLabel")}</div>
      {freeTopic ? (
        <>
          <p className="free-card-topic">{freeTopic}</p>
          {zh && <p className="free-card-zh">{zh}</p>}
          <p className="free-card-hint">{t("practice.freeHint")}</p>
        </>
      ) : (
        <p className="free-card-topic">{t("practice.freeNoTopicCard")}</p>
      )}
    </div>
  );
}
