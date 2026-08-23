// 分享文案：复制到剪贴板的内容 = 文案 + 链接
export function shareUrl(token) {
  return `${window.location.origin}/s/${token}`;
}

export function buildShareText(session, token) {
  const title = (session?.title || session?.topic || "speaking practice").trim();
  const attempts = session?.attempts || [];
  const last = attempts[attempts.length - 1];
  const score = last?.score != null ? Number(last.score).toFixed(1) : null;
  const scoreLine = score ? ` (IELTS ${score})` : "";
  return `I practiced "${title}" on SpeakUp${scoreLine} — take a look 👉 ${shareUrl(token)}`;
}

export async function copyShare(session, token) {
  const text = buildShareText(session, token);
  await navigator.clipboard.writeText(text);
  return text;
}

// 手机优先调系统分享面板；不支持 Web Share 时退回复制完整文案。
export async function shareOrCopy(session, token) {
  const text = buildShareText(session, token);
  if (typeof navigator.share === "function") {
    try {
      await navigator.share({ text });
      return "shared";
    } catch (error) {
      if (error?.name === "AbortError") return "cancelled";
      // 某些浏览器声明支持但实际拒绝文本分享，继续走剪贴板兜底。
    }
  }
  await navigator.clipboard.writeText(text);
  return "copied";
}
