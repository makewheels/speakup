import Icon from "../Icon.jsx";
import FeedbackBar from "./FeedbackBar.jsx";

export default function ResultFooterActions({
  attemptIndex,
  onShare,
  onUnshare = null,
  practiceId,
  shareAriaLabel,
  shareBusy = false,
  shareBusyLabel,
  shareLabel,
  shareStatus = "",
  snapshot,
  stopSharingLabel = "",
}) {
  return (
    <div className="fb-result-footer">
      <FeedbackBar
        attemptIndex={attemptIndex}
        compact
        practiceId={practiceId}
        snapshot={snapshot}
      />
      <button
        aria-label={shareAriaLabel}
        className="su-btn su-btn-tertiary share-btn"
        type="button"
        onClick={onShare}
        disabled={shareBusy}
      >
        <Icon name="share" size={16} />
        {shareBusy ? shareBusyLabel : shareLabel}
      </button>
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
