/**
 * 极简 i18n —— 不引入 react-i18next，避免 20kb gzip 依赖。
 *
 * 字典 schema 见 zh-CN.json / en.json；按页面/区块分组，避免一坨。
 * 占位符语法 {name} —— 调用方传 vars={name: value}。
 * 默认跟随 navigator.language；用户可在 Profile 切换，存 localStorage。
 *
 * AI 输出（gaps/nativeVersion/summary）仍保持中文——不归 i18n 管，跟着 corrector 走。
 */
import { createContext, useContext, useEffect, useMemo, useState } from "react";
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
  // 支持点号路径："practice.youSaid" → dict.practice.youSaid
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

function buildT(lang) {
  const dict = DICTS[lang] || DICTS.en;
  const fallback = DICTS.en;
  return (key, vars) => {
    const v = lookup(dict, key) ?? lookup(fallback, key);
    if (v === undefined) return key;
    return format(v, vars);
  };
}

// 默认值：让组件在没有 Provider 包裹时（单元测试、Storybook 等）也能正常渲染英文文案
const LangContext = createContext({
  lang: "en",
  setLang: () => {},
  t: buildT("en"),
});

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(detectLang);

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, lang); } catch { /* 同 detect 处理 */ }
    if (typeof document !== "undefined") document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo(
    () => ({ lang, setLang: setLangState, t: buildT(lang) }),
    [lang]
  );

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useT() {
  return useContext(LangContext).t;
}

export function useLang() {
  return useContext(LangContext);
}
