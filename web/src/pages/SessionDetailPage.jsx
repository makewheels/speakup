import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, chatStream } from "../api/client.js";
import { useUser } from "../context/useUser.js";
import { useT } from "../i18n/useI18n.js";
import Icon from "../components/Icon.jsx";
import SessionView from "../components/SessionView.jsx";
import { copyShare } from "../lib/share.js";

export default function SessionDetailPage() {
  const { practiceId } = useParams();
  const navigate = useNavigate();
  const { user } = useUser();
  const t = useT();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [chat, setChat] = useState([]);          // 最新一轮的追问对话
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [shareToken, setShareToken] = useState(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [toast, setToast] = useState("");
  const chatControllerRef = useRef(null);

  useEffect(() => {
    api.getPractice(practiceId)
      .then((s) => {
        setSession(s);
        setShareToken(s?.shared ? s.shareToken : null);
        const ats = s?.attempts || [];
        setChat(ats.length ? (ats[ats.length - 1].chat || []) : []);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [practiceId]);

  const flash = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 2000);
  };

  // 追问：基于本次练习最新一轮的反馈继续问 AI
  const sendChat = () => {
    const q = chatInput.trim();
    if (!q || chatBusy || !user?.userId) return;
    setChatInput("");
    setChat((c) => [...c, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setChatBusy(true);
    chatControllerRef.current = chatStream(
      { userId: user.userId, practiceId, question: q },
      {
        onChunk: (text) =>
          setChat((c) => {
            const next = [...c];
            next[next.length - 1] = { role: "assistant", content: next[next.length - 1].content + text };
            return next;
          }),
        onDone: () => setChatBusy(false),
        onError: (err) => {
          setChatBusy(false);
          setChat((c) => {
            const next = [...c];
            next[next.length - 1] = { role: "assistant", content: t("practice.chatError", { msg: err.message }) };
            return next;
          });
        },
      }
    );
  };

  const doShare = async () => {
    if (shareBusy) return;
    setShareBusy(true);
    try {
      let token = shareToken;
      if (!token) {
        const r = await api.sharePractice(practiceId, user.userId);
        token = r.shareToken;
        setShareToken(token);
      }
      await copyShare(session, token);
      flash(t("session.linkCopied"));
    } catch (e) {
      flash(t("session.failed", { msg: e.message }));
    } finally {
      setShareBusy(false);
    }
  };

  const doUnshare = async () => {
    if (shareBusy) return;
    setShareBusy(true);
    try {
      await api.unsharePractice(practiceId, user.userId);
      setShareToken(null);
      flash(t("session.sharingStopped"));
    } catch (e) {
      flash(t("session.failed", { msg: e.message }));
    } finally {
      setShareBusy(false);
    }
  };

  if (loading) return <div className="page-msg">{t("common.loading")}</div>;
  if (!session) return <div className="page-msg">{t("session.notFound")}</div>;

  const shareBar = shareToken ? (
    <div className="share-bar shared">
      <div className="share-bar-status">
        <span className="share-dot" />
        <span className="share-bar-title">{t("session.shared")}</span>
        <span className="share-bar-sub">{t("session.sharedSub")}</span>
      </div>
      <div className="share-bar-actions">
        <button className="su-btn su-btn-primary" onClick={doShare} disabled={shareBusy}>
          <Icon name="link" size={15} /> {t("session.copyLink")}
        </button>
        <button className="share-cancel" onClick={doUnshare} disabled={shareBusy}>
          {t("session.stopSharing")}
        </button>
      </div>
    </div>
  ) : (
    <div className="share-bar">
      <div className="share-bar-status">
        <span className="share-bar-title muted">{t("session.notShared")}</span>
        <span className="share-bar-sub">{t("session.notSharedSub")}</span>
      </div>
      <button className="su-btn su-btn-tertiary share-btn" onClick={doShare} disabled={shareBusy}>
        <Icon name="share" size={16} /> {t("session.share")}
      </button>
    </div>
  );

  return (
    <div className="session-detail-page fade-in">
      <button className="detail-back" onClick={() => navigate(-1)}>
        <Icon name="back" size={20} /> {t("session.back")}
      </button>

      <SessionView
        session={session}
        belowHero={shareBar}
        chat={chat}
        chatInput={chatInput}
        setChatInput={setChatInput}
        onSend={sendChat}
        chatBusy={chatBusy}
        noteUserId={user.userId}
      />

      {toast && <div className="su-toast">{toast}</div>}
    </div>
  );
}
