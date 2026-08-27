import { useState, useEffect } from "react";
import { api } from "../api/client.js";
import { UserContext } from "./user-context.js";
import { savePracticePreferences } from "../lib/practicePreferences.js";

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
    // 登录响应带回服务端偏好：先落本地缓存，练习页再对账
    if (data.practicePreferences) {
      savePracticePreferences(data.userId, data.practicePreferences);
    }
    setUser(data);
    return data;
  };

  const updateNickname = async (nickname) => {
    const data = await api.updateProfile(nickname);
    setUser((current) => (
      current ? { ...current, nickname: data.nickname } : current
    ));
    return data;
  };

  const updateAvatar = async (file) => {
    const data = await api.uploadAvatar(file);
    setUser((current) => (
      current ? { ...current, avatarUrl: data.avatarUrl } : current
    ));
    return data;
  };

  const removeAvatar = async () => {
    const data = await api.removeAvatar();
    setUser((current) => (
      current ? { ...current, avatarUrl: null } : current
    ));
    return data;
  };

  const logout = () => setUser(null);

  return (
    <UserContext.Provider value={{
      user,
      login,
      updateNickname,
      updateAvatar,
      removeAvatar,
      logout,
    }}>
      {children}
    </UserContext.Provider>
  );
}
