import { useContext } from "react";
import { LangContext } from "./lang-context.js";

export function useT() {
  return useContext(LangContext).t;
}

export function useLang() {
  return useContext(LangContext);
}
