import Icon from "../Icon.jsx";
import SpeakBtn from "../SpeakBtn.jsx";
import { useT } from "../../i18n/useI18n.js";

export default function FeedbackGapList({
  canSpeak = true,
  gaps = [],
  onToggleGap = null,
  practiceId,
  savedMap = {},
  showTitle = true,
}) {
  const t = useT();
  if (!gaps.length) return null;

  return (
    <div className="fb-gaps-section">
      {showTitle && (
        <div className="fb-section-label">{t("practice.gapsTitle", { n: gaps.length })}</div>
      )}
      {gaps.map((gap, index) => {
        const added = Boolean(savedMap[index]);
        const category = gap.category ? t(`practice.gapCat.${gap.category}`) : "";
        return (
          <article key={index} className="fb-gap-card" data-note-context={gap.better || gap.original || ""}>
            <div className="fb-gap-head">
              <span className="fb-gap-num">{index + 1}</span>
              <div className="fb-gap-heading">
                {category && <span className="fb-gap-cat">{category}</span>}
                {category && gap.title && <span className="fb-gap-heading-dot">·</span>}
                {gap.title && <span className="fb-gap-title">{gap.title}</span>}
              </div>
              {onToggleGap && (
                <button
                  className={"fb-gap-add" + (added ? " added" : "")}
                  onClick={() => onToggleGap(gap, index)}
                  title={added ? t("practice.removeTitle") : t("practice.addTitle")}
                >
                  {added
                    ? <><Icon name="check" size={14} />&nbsp;{t("practice.inReview")}</>
                    : <><Icon name="plus" size={14} />&nbsp;{t("practice.addToReview")}</>}
                </button>
              )}
            </div>

            <div className="fb-gap-core">
              <div className="fb-gap-line is-said">
                <span className="fb-gap-tag">{t("practice.gapYouSaid")}</span>
                <span className="fb-gap-said">{gap.original}</span>
              </div>
              <div className="fb-gap-line is-fix">
                <span className="fb-gap-tag">{t("practice.gapSayThis")}</span>
                <span className="fb-gap-fix">{gap.better}</span>
                {canSpeak && <SpeakBtn text={gap.better} practiceId={practiceId} />}
              </div>
              {gap.why && (
                <div className="fb-gap-line is-why">
                  <span className="fb-gap-tag">{t("practice.gapWhy")}</span>
                  <span className="fb-gap-whytext">{gap.why}</span>
                </div>
              )}
            </div>

            {gap.example && (
              <details className="fb-gap-example-details">
                <summary>{t("practice.expandExample")}</summary>
                <div className="fb-gap-example-body">
                  <div className="fb-gap-example-row">
                    <span className="fb-gap-example">{gap.example}</span>
                    {canSpeak && <SpeakBtn text={gap.example} practiceId={practiceId} />}
                  </div>
                  {gap.exampleChinese && <p className="fb-gap-example-zh">{gap.exampleChinese}</p>}
                </div>
              </details>
            )}
          </article>
        );
      })}
    </div>
  );
}
