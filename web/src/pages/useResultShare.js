import { useState } from "react";

import { api } from "../api/client.js";
import { shareOrCopy } from "../lib/share.js";

export default function useResultShare({ result, round, session, setSession, t, userId }) {
  const [shareBusy, setShareBusy] = useState(false);
  const [shareStatus, setShareStatus] = useState("");

  const resetShare = () => {
    setShareBusy(false);
    setShareStatus("");
  };

  const rollbackNewShare = async ({ failure, token, type }) => {
    try {
      await api.unsharePractice(session._id, userId);
      setSession((current) => ({ ...current, shared: false, shareToken: token }));
      setShareStatus(t(
        type === "cancelled"
          ? "practice.resultShareCancelledRolledBack"
          : "practice.resultShareFailedRolledBack",
        { msg: failure?.message || "unknown error" },
      ));
    } catch (rollbackError) {
      setShareStatus(t(
        type === "cancelled"
          ? "practice.resultShareCancelRollbackFailed"
          : "practice.resultShareFailureRollbackFailed",
        {
          rollbackMsg: rollbackError.message,
          shareMsg: failure?.message || "unknown error",
        },
      ));
    }
  };

  const shareResult = async () => {
    if (!session?._id || shareBusy) return;
    setShareBusy(true);
    setShareStatus("");
    const wasShared = Boolean(session.shared);
    let enabledNow = false;
    let token = wasShared ? session.shareToken : "";
    try {
      if (!token) {
        const response = await api.sharePractice(session._id, userId);
        token = response.shareToken;
        enabledNow = !wasShared;
        setSession((current) => ({ ...current, shared: true, shareToken: token }));
      }
      const attempts = session.attempts || [];
      const shareSession = attempts.length >= round
        ? session
        : { ...session, attempts: [...attempts, { score: result?.score }] };
      const method = await shareOrCopy(shareSession, token);
      if (method === "cancelled") {
        if (enabledNow) await rollbackNewShare({ token, type: "cancelled" });
        else setShareStatus(t("practice.resultShareCancelled"));
      } else {
        setShareStatus(t(method === "shared" ? "practice.resultShared" : "practice.resultShareCopied"));
      }
    } catch (error) {
      if (enabledNow) await rollbackNewShare({ failure: error, token, type: "failed" });
      else setShareStatus(t("practice.resultShareFailed", { msg: error.message }));
    } finally {
      setShareBusy(false);
    }
  };

  return { resetShare, shareBusy, shareResult, shareStatus };
}
