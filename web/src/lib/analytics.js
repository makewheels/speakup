// 产品埋点（Umami，自建、无 cookie）。事件字典见 docs/业务/数据埋点.md。
// website id 是公开标识（访问者本就能看到），不含任何密钥。
// 脚本与上报走主域同源路径（Caddy 代理到 umami 容器），管理后台走服务器 IP:30040，不占子域。
const UMAMI_WEBSITE_ID = "b4842023-49b7-48ed-98ca-f65cf7f0f0f2";

export function initAnalytics() {
  if (!import.meta.env.PROD) return; // 本地 dev 不打点，保持 dev/prod 数据隔离
  if (document.querySelector("script[data-website-id]")) return;
  const script = document.createElement("script");
  script.async = true;
  script.src = "/umami-script.js";
  script.setAttribute("data-website-id", UMAMI_WEBSITE_ID);
  document.head.appendChild(script);
}

// umami 脚本未加载（dev / 加载失败）时静默无操作
export function track(event, props = {}) {
  window.umami?.track(event, props);
}
