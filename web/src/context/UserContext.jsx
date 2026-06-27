import { useState, useEffect } from "react";
import { api } from "../api/client.js";
import { UserContext } from "./user-context.js";

export function UserProvider({ children }) {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem("english-speak-user");
    return saved ? JSON.parse(saved) : null;
  });

  useEffect(() => {
    if (user) {
      localStorage.setItem("english-speak-user", JSON.stringify(user));
    } else {
      localStorage.removeItem("english-speak-user");
    }
  }, [user]);

  useEffect(() => {
    const handleUnauthorized = () => setUser(null);
    window.addEventListener("speakup:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("speakup:unauthorized", handleUnauthorized);
  }, []);

  const login = async (phone) => {
    const data = await api.login(phone);
    setUser(data);
    return data;
  };

  const logout = () => setUser(null);

  return (
    <UserContext.Provider value={{ user, login, logout }}>
      {children}
    </UserContext.Provider>
  );
}
