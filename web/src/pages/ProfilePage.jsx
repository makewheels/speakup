import { useState } from "react";
import { useUser } from "../context/UserContext.jsx";
import { useNavigate } from "react-router-dom";
import { useT, useLang } from "../i18n/index.jsx";
import Icon from "../components/Icon.jsx";
import {
  getPracticePreferences,
} from "../lib/practicePreferences.js";

export default function ProfilePage() {
  const { user, logout } = useUser();
  const navigate = useNavigate();
  const t = useT();
  const { lang, setLang } = useLang();
  const [practicePrefs] = useState(() => getPracticePreferences(user?.userId));

  if (!user) return null;

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const maskedPhone = user.phone
    ? `${user.phone.slice(0, 3)} **** ${user.phone.slice(-4)}`
    : "";
  const initial = user.nickname?.charAt(0)?.toUpperCase() || "U";
  const prefSummary = t("practicePrefs.summary", {
    level: t(`practicePrefs.level.${practicePrefs.level}`),
    purpose: t(`practicePrefs.purpose.${practicePrefs.purpose}`),
  });

  return (
    <div className="profile-page">
      <div className="who">
        <div className="avatar">{initial}</div>
        <div>
          <div className="nickname">{user.nickname}</div>
          <div className="phone">{maskedPhone}</div>
        </div>
      </div>

      <div className="profile-section">
        <div className="profile-section-label">{t("profile.settings")}</div>
        <div className="profile-lang-row">
          <div className="profile-lang-key">
            <Icon name="globe" size={18} color="var(--ink-3)" />
            <span>{t("profile.language")}</span>
          </div>
          <div className="profile-lang-segmented" role="radiogroup" aria-label={t("profile.language")}>
            <button
              type="button"
              role="radio"
              aria-checked={lang === "zh-CN"}
              className={"seg" + (lang === "zh-CN" ? " active" : "")}
              onClick={() => setLang("zh-CN")}
            >
              {t("profile.langZh")}
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={lang === "en"}
              className={"seg" + (lang === "en" ? " active" : "")}
              onClick={() => setLang("en")}
            >
              {t("profile.langEn")}
            </button>
          </div>
        </div>
        <button className="profile-setting-row" onClick={() => navigate("/me/practice-preferences")}>
          <div className="profile-lang-key">
            <Icon name="spark" size={18} color="var(--ink-3)" />
            <span>{t("profile.practicePreference")}</span>
          </div>
          <span className="profile-setting-summary">{prefSummary}</span>
          <Icon name="next" size={16} color="var(--ink-4)" />
        </button>
      </div>

      <button className="profile-entry" onClick={() => navigate("/shares")}>
        <Icon name="share" size={18} color="var(--ink-3)" />
        <span>{t("profile.myShares")}</span>
        <Icon name="next" size={16} color="var(--ink-4)" />
      </button>

      <button className="su-btn su-btn-danger" onClick={handleLogout}>
        {t("profile.logout")}
      </button>
    </div>
  );
}
