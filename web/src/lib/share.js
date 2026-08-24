// 分享文案：复制到剪贴板的内容 = 文案 + 链接
export function shareUrl(token, attemptId = "") {
  const url = new URL(`/s/${encodeURIComponent(token)}`, window.location.origin);
  if (attemptId) url.searchParams.set("attempt", attemptId);
  return url.toString();
}

export async function copyShareLink(token, attemptId = "") {
  const url = shareUrl(token, attemptId);
  await navigator.clipboard.writeText(url);
  return url;
}
