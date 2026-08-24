import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, chatStream } from "../api/client.js";
import { useUser } from "../context/useUser.js";
import { useT } from "../i18n/useI18n.js";
import Icon from "../components/Icon.jsx";
import SessionView from "../components/SessionView.jsx";
import { shareUrl } from "../lib/share.js";

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
  const [shareLink, setShareLink] = useState("");
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
    const latestAttempt = session?.attempts?.[session.attempts.length - 1];
    chatControllerRef.current = chatStream(
      {
        userId: user.userId,
        practiceId,
        attemptId: latestAttempt?.attemptId || latestAttempt?._id || "",
        question: q,
      },
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

  const doShare = async (attemptId = "") => {
    if (shareBusy) return;
    setShareBusy(true);
    try {
      let token = shareToken;
      if (!token) {
        const r = await api.sharePractice(practiceId, user.userId);
        token = r.shareToken;
        setShareToken(token);
      }
      setShareLink(shareUrl(token, attemptId));
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
      setShareLink("");
      flash(t("session.sharingStopped"));
    } catch (e) {
      flash(t("session.failed", { msg: e.message }));
    } finally {
      setShareBusy(false);
    }
  };

  const copyCurrentShareLink = async () => {
    if (!shareLink) return;
    try {
      await navigator.clipboard.writeText(shareLink);
      flash(t("session.linkCopied"));
    } catch (e) {
      flash(t("session.failed", { msg: e.message }));
    }
  };

  if (loading) return <div className="page-msg">{t("common.loading")}</div>;
  if (!session) return <div className="page-msg">{t("session.notFound")}</div>;

  return (
    <div className="session-detail-page fade-in">
      <button className="detail-back" onClick={() => navigate(-1)}>
        <Icon name="back" size={20} /> {t("session.back")}
      </button>

      <SessionView
        session={session}
        chat={chat}
        chatInput={chatInput}
        setChatInput={setChatInput}
        onSend={sendChat}
        chatBusy={chatBusy}
        noteUserId={user.userId}
        onShare={doShare}
        onCloseShareLink={() => setShareLink("")}
        onCopyShareLink={copyCurrentShareLink}
        onUnshare={shareToken ? doUnshare : null}
        shareBusy={shareBusy}
        shareLink={shareLink}
        shareStatus={shareToken ? t("session.sharedSub") : ""}
      />

      {toast && <div className="su-toast">{toast}</div>}
    </div>
  );
}
