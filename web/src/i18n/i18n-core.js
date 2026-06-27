import zh from "./zh-CN.json";
import en from "./en.json";

const DICTS = { "zh-CN": zh, en };
const STORAGE_KEY = "speakup_lang";

export function detectLang() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && DICTS[saved]) return saved;
  } catch {
    // localStorage 不可用时（隐私模式）静默走探测
  }
  const nav = (typeof navigator !== "undefined" && navigator.language) || "en";
  return nav.toLowerCase().startsWith("zh") ? "zh-CN" : "en";
}

function lookup(dict, key) {
  const parts = key.split(".");
  let cur = dict;
  for (const p of parts) {
    if (cur && typeof cur === "object" && p in cur) cur = cur[p];
    else return undefined;
  }
  return typeof cur === "string" ? cur : undefined;
}

function format(tmpl, vars) {
  if (!vars) return tmpl;
  return tmpl.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? String(vars[k]) : `{${k}}`));
}

export function buildT(lang) {
  const dict = DICTS[lang] || DICTS.en;
  const fallback = DICTS.en;
  return (key, vars) => {
    const v = lookup(dict, key) ?? lookup(fallback, key);
    if (v === undefined) return key;
    return format(v, vars);
  };
}
