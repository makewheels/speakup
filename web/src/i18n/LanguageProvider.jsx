import { useEffect, useMemo, useState } from "react";
import { detectLang, buildT } from "./i18n-core.js";
import { LangContext } from "./lang-context.js";

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(detectLang);

  useEffect(() => {
    try { localStorage.setItem("speakup_lang", lang); } catch { /* 同 detect 处理 */ }
    if (typeof document !== "undefined") document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo(
    () => ({ lang, setLang: setLangState, t: buildT(lang) }),
    [lang],
  );

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}
