// 主题（浅色 / 深色）切换。
// 模式：auto（默认，按日出日落自动切）、light、dark，存在 localStorage。
// auto 时优先用定位纬度算日出日落；拿不到定位就退化为固定时间（6:30 / 18:30）。

const MODE_KEY = "english-speak-theme-mode";
const LAT_KEY = "english-speak-theme-lat";

export const FIXED_SUNRISE = 6.5; // 6:30
export const FIXED_SUNSET = 18.5; // 18:30

export function getThemeMode() {
  const m = localStorage.getItem(MODE_KEY);
  return m === "light" || m === "dark" ? m : "auto";
}

export function setThemeMode(mode) {
  if (mode === "light" || mode === "dark") localStorage.setItem(MODE_KEY, mode);
  else localStorage.removeItem(MODE_KEY);
}

/**
 * 估算日出 / 日落（小时，当地时间）。用简化的太阳赤纬公式，
 * 不追求天文精度，只用于"白天 / 夜晚"的主题判断。
 * @returns {{sunrise:number, sunset:number}} 或在极昼极夜时为 null
 */
export function sunTimes(date, latitude) {
  const rad = Math.PI / 180;
  const start = new Date(date.getFullYear(), 0, 0);
  const dayOfYear = Math.floor((date - start) / 864e5);
  // 太阳赤纬（近似）
  const decl = -23.44 * Math.cos(rad * (360 / 365) * (dayOfYear + 10));
  const latRad = latitude * rad;
  const declRad = decl * rad;
  const cosH =
    (Math.cos(90.833 * rad) - Math.sin(latRad) * Math.sin(declRad)) /
    (Math.cos(latRad) * Math.cos(declRad));
  if (cosH > 1 || cosH < -1) return null; // 极昼 / 极夜
  const H = Math.acos(cosH) / rad; // 半日弧（度）
  return { sunrise: 12 - H / 15, sunset: 12 + H / 15 };
}

export function isDaytime(date = new Date(), latitude = null) {
  let sunrise = FIXED_SUNRISE;
  let sunset = FIXED_SUNSET;
  if (latitude != null) {
    const t = sunTimes(date, latitude);
    if (t) {
      sunrise = t.sunrise;
      sunset = t.sunset;
    }
  }
  const h = date.getHours() + date.getMinutes() / 60;
  return h >= sunrise && h < sunset;
}

export function resolveTheme(mode, date = new Date(), latitude = null) {
  if (mode === "light" || mode === "dark") return mode;
  return isDaytime(date, latitude) ? "light" : "dark";
}

function setMetaThemeColor(theme) {
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "dark" ? "#1c1c1e" : "#f6f5f0");
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  setMetaThemeColor(theme);
}

/** 静默尝试拿一次纬度（短超时，失败就算了），缓存到 localStorage。 */
function fetchLatitude() {
  const cached = Number(localStorage.getItem(LAT_KEY));
  if (Number.isFinite(cached) && cached !== 0) return Promise.resolve(cached);
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    const timer = setTimeout(() => resolve(null), 2000);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        clearTimeout(timer);
        const lat = pos?.coords?.latitude;
        if (Number.isFinite(lat)) {
          localStorage.setItem(LAT_KEY, String(lat));
          resolve(lat);
        } else resolve(null);
      },
      () => {
        clearTimeout(timer);
        resolve(null);
      },
      { timeout: 1800, maximumAge: 864e5 },
    );
  });
}

/**
 * 初始化主题：立即应用一次，然后每分钟复查一次（到点自动切换）。
 * 返回清理函数。
 */
export function initTheme() {
  let latitude = null;
  const refresh = () => {
    applyTheme(resolveTheme(getThemeMode(), new Date(), latitude));
  };
  refresh();
  fetchLatitude().then((lat) => {
    latitude = lat;
    refresh();
  });
  const interval = setInterval(refresh, 60_000);
  const onVisible = () => {
    if (document.visibilityState === "visible") refresh();
  };
  document.addEventListener("visibilitychange", onVisible);
  return () => {
    clearInterval(interval);
    document.removeEventListener("visibilitychange", onVisible);
  };
}
