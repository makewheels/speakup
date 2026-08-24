import Icon from "../Icon.jsx";
import FeedbackBar from "./FeedbackBar.jsx";
import { useT } from "../../i18n/useI18n.js";

export default function ResultFooterActions({
  attemptId,
  attemptIndex,
  onCloseShareLink = null,
  onCopyShareLink = null,
  onShare,
  onUnshare = null,
  practiceId,
  shareAriaLabel,
  shareBusy = false,
  shareBusyLabel,
  shareLabel,
  shareLink = "",
  shareStatus = "",
  snapshot,
  stopSharingLabel = "",
}) {
  const t = useT();
  return (
    <div className="fb-result-footer">
      <FeedbackBar
        attemptId={attemptId}
        attemptIndex={attemptIndex}
        compact
        practiceId={practiceId}
        snapshot={snapshot}
      />
      <button
        aria-label={shareAriaLabel}
        className="su-btn su-btn-tertiary share-btn"
        type="button"
        onClick={() => onShare?.(attemptId)}
        disabled={shareBusy}
      >
        <Icon name="share" size={16} />
        {shareBusy ? shareBusyLabel : shareLabel}
      </button>
      {shareLink && (
        <div className="fb-share-link-popover" role="dialog" aria-label={t("practice.shareLinkTitle")}>
          <div className="fb-share-link-head">
            <strong>{t("practice.shareLinkTitle")}</strong>
            <button type="button" onClick={onCloseShareLink} aria-label={t("common.close")}>×</button>
          </div>
          <div className="fb-share-link-row">
            <input
              aria-label={t("practice.shareLinkTitle")}
              readOnly
              value={shareLink}
              onFocus={(event) => event.currentTarget.select()}
            />
            <button className="su-btn su-btn-primary" type="button" onClick={onCopyShareLink}>
              {t("session.copyLink")}
            </button>
          </div>
        </div>
      )}
      {(shareStatus || onUnshare) && (
        <div className="fb-result-footer-status">
          {shareStatus && <span role="status">{shareStatus}</span>}
          {onUnshare && (
            <button type="button" onClick={onUnshare} disabled={shareBusy}>
              {stopSharingLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
