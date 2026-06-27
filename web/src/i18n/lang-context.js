import { createContext } from "react";
import { buildT } from "./i18n-core.js";

export const LangContext = createContext({
  lang: "en",
  setLang: () => {},
  t: buildT("en"),
});
