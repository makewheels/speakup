// 主题（浅色 / 深色）切换。
// 模式：auto（默认，跟随系统）、light、dark，存在 localStorage。

const MODE_KEY = "english-speak-theme-mode";
const LEGACY_LAT_KEY = "english-speak-theme-lat";
const DARK_MEDIA_QUERY = "(prefers-color-scheme: dark)";

export function getThemeMode() {
  const m = localStorage.getItem(MODE_KEY);
  return m === "light" || m === "dark" ? m : "auto";
}

export function setThemeMode(mode) {
  if (mode === "light" || mode === "dark") localStorage.setItem(MODE_KEY, mode);
  else localStorage.removeItem(MODE_KEY);
}

function systemPrefersDark() {
  return Boolean(window.matchMedia?.(DARK_MEDIA_QUERY).matches);
}

export function resolveTheme(mode, prefersDark = systemPrefersDark()) {
  if (mode === "light" || mode === "dark") return mode;
  return prefersDark ? "dark" : "light";
}

function setMetaThemeColor(theme) {
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "dark" ? "#1c1c1e" : "#f6f5f0");
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  setMetaThemeColor(theme);
}

/**
 * 初始化主题：立即应用一次；auto 模式下跟随系统主题变化。
 * 返回清理函数。
 */
export function initTheme() {
  localStorage.removeItem(LEGACY_LAT_KEY);
  const mediaQuery = window.matchMedia?.(DARK_MEDIA_QUERY);
  const refresh = () => {
    applyTheme(resolveTheme(getThemeMode(), Boolean(mediaQuery?.matches)));
  };
  refresh();

  const onSystemThemeChange = () => {
    if (getThemeMode() === "auto") refresh();
  };

  if (mediaQuery?.addEventListener) {
    mediaQuery.addEventListener("change", onSystemThemeChange);
  } else {
    mediaQuery?.addListener?.(onSystemThemeChange);
  }

  return () => {
    if (mediaQuery?.removeEventListener) {
      mediaQuery.removeEventListener("change", onSystemThemeChange);
    } else {
      mediaQuery?.removeListener?.(onSystemThemeChange);
    }
  };
}
