import { useCallback, useEffect, useRef, useState } from "react";
import { chatStream } from "../api/client.js";

/**
 * 追问教练对话：基于本次练习反馈继续问 AI（SSE 流式）。
 * sendChat(question, onError?) 追加 user+assistant 占位后流式填充。
 */
export default function useFollowupChat(userId, practiceId) {
  const [chat, setChat] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const controllerRef = useRef(null);

  // 组件卸载时断开流
  useEffect(() => () => controllerRef.current?.abort(), []);

  // formatError(err) → 助手气泡里的错误文案（i18n 在调用方，hook 不碰 t）
  const sendChat = useCallback((question, formatError) => {
    const q = (question ?? "").trim();
    if (!q || chatBusy || !practiceId) return;
    setChatInput("");
    // 先把用户问题和一个空的 assistant 占位推进去，流式往占位里填
    setChat((c) => [...c, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setChatBusy(true);
    controllerRef.current = chatStream(
      { userId, practiceId, question: q },
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
          const msg = formatError ? formatError(err) : String(err?.message || err);
          setChat((c) => {
            const next = [...c];
            next[next.length - 1] = { role: "assistant", content: msg };
            return next;
          });
        },
      }
    );
  }, [userId, practiceId, chatBusy]);

  const resetChat = useCallback((history) => setChat(history || []), []);

  return { chat, chatInput, setChatInput, chatBusy, sendChat, resetChat };
}
