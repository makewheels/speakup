import { useState } from "react";

import { api } from "../api/client.js";
import { shareUrl } from "../lib/share.js";
import { track } from "../lib/analytics.js";

export default function useResultShare({ session, setSession, t, userId }) {
  const [shareBusy, setShareBusy] = useState(false);
  const [shareLink, setShareLink] = useState("");
  const [shareStatus, setShareStatus] = useState("");

  const resetShare = () => {
    setShareBusy(false);
    setShareLink("");
    setShareStatus("");
  };

  const shareResult = async (attemptId = "") => {
    if (!session?._id || shareBusy) return;
    setShareBusy(true);
    setShareStatus("");
    let token = session.shared ? session.shareToken : "";
    try {
      if (!token) {
        const response = await api.sharePractice(session._id, userId);
        token = response.shareToken;
        setSession((current) => ({ ...current, shared: true, shareToken: token }));
      }
      setShareLink(shareUrl(token, attemptId));
      track("result_share_link_opened", { attemptId, userId });
    } catch (error) {
      setShareStatus(t("practice.resultShareFailed", { msg: error.message }));
    } finally {
      setShareBusy(false);
    }
  };

  const copyShareLink = async () => {
    if (!shareLink) return;
    try {
      await navigator.clipboard.writeText(shareLink);
      setShareStatus(t("practice.resultLinkCopied"));
      track("result_share_link_copied", { userId });
    } catch (error) {
      setShareStatus(t("practice.resultShareFailed", { msg: error.message }));
    }
  };

  const closeShareLink = () => {
    setShareLink("");
    setShareStatus("");
  };

  return {
    closeShareLink,
    copyShareLink,
    resetShare,
    shareBusy,
    shareLink,
    shareResult,
    shareStatus,
  };
}
