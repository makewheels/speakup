import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client.js";
import SessionView from "../components/SessionView.jsx";

export default function SharePage() {
  const { token } = useParams();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getSharedSession(token)
      .then(setSession)
      .catch(() => setError("This share is closed or doesn't exist"))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) return <div className="page-msg">Loading…</div>;
  if (error || !session) {
    return (
      <div className="share-page">
        <div className="empty-state">
          <p className="title">{error || "Share not found"}</p>
          <p className="sub">The link may have been turned off</p>
        </div>
      </div>
    );
  }

  const owner = session.ownerNickname;
  return (
    <div className="share-page fade-in">
      <div className="share-brand">SpeakUp · Speaking practice</div>
      <SessionView
        session={session}
        readOnly
        subtitle={owner ? `Shared by ${owner}` : null}
      />
    </div>
  );
}
