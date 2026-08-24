import { useState, useEffect } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client.js";
import { useT } from "../i18n/useI18n.js";
import SessionView from "../components/SessionView.jsx";

export default function SharePage() {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  const initialAttemptId = searchParams.get("attempt") || "";
  const t = useT();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getSharedSession(token)
      .then(setSession)
      .catch(() => setError(t("share.closedTitle")))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (loading) return <div className="page-msg">{t("common.loading")}</div>;
  if (error || !session) {
    return (
      <div className="share-page">
        <div className="empty-state">
          <p className="title">{error || t("share.notFoundTitle")}</p>
          <p className="sub">{t("share.closedSub")}</p>
        </div>
      </div>
    );
  }

  const owner = session.ownerNickname;
  return (
    <div className="share-page fade-in">
      <div className="share-brand">{t("share.brand")}</div>
      <SessionView
        initialAttemptId={initialAttemptId}
        session={session}
        readOnly
        subtitle={owner ? t("share.sharedBy", { owner }) : null}
      />
    </div>
  );
}
