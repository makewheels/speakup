import { useContext } from "react";
import { UserContext } from "./user-context.js";

export function useUser() {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error("useUser must be inside UserProvider");
  return ctx;
}
