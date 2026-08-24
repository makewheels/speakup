import { useState } from "react";
import { useUser } from "../context/useUser.js";
import { useNavigate } from "react-router-dom";
import { useT, useLang } from "../i18n/useI18n.js";
import Icon from "../components/Icon.jsx";
import ProfileAvatar from "../components/ProfileAvatar.jsx";
import {
  getPracticePreferences,
} from "../lib/practicePreferences.js";
import {
  getThemeMode,
  setThemeMode,
  resolveTheme,
  applyTheme,
} from "../lib/theme.js";

export default function ProfilePage() {
  const { user, logout } = useUser();
  const navigate = useNavigate();
  const t = useT();
  const { lang, setLang } = useLang();
  const [practicePrefs] = useState(() => getPracticePreferences(user?.userId));
  const [themeMode, setThemeModeState] = useState(() => getThemeMode());

  const chooseTheme = (mode) => {
    setThemeMode(mode);
    setThemeModeState(mode);
    // 立即生效；auto 会跟随系统深浅色设置
    applyTheme(resolveTheme(mode));
  };

  if (!user) return null;

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const maskedPhone = user.phone
    ? `${user.phone.slice(0, 3)} **** ${user.phone.slice(-4)}`
    : "";
  const prefSummary = t("practicePrefs.summary", {
    level: t(`practicePrefs.level.${practicePrefs.level}`),
    purpose: t(`practicePrefs.purpose.${practicePrefs.purpose}`),
  });

  return (
    <div className="profile-page">
      <button
        className="profile-summary"
        type="button"
        aria-label={t("profile.editProfile")}
        onClick={() => navigate("/me/profile")}
      >
        <ProfileAvatar user={user} alt={t("profile.avatarAlt")} />
        <span className="profile-summary-identity">
          <span className="profile-summary-nickname">{user.nickname}</span>
          <span className="profile-summary-phone">{maskedPhone}</span>
        </span>
        <Icon name="next" size={18} color="var(--ink-4)" />
      </button>

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
        <div className="profile-lang-row">
          <div className="profile-lang-key">
            <Icon name="moon" size={18} color="var(--ink-3)" />
            <span>{t("profile.theme")}</span>
          </div>
          <div className="profile-lang-segmented" role="radiogroup" aria-label={t("profile.theme")}>
            {[
              ["auto", t("profile.themeAuto"), t("profile.themeAutoTitle")],
              ["light", t("profile.themeLight")],
              ["dark", t("profile.themeDark")],
            ].map(([mode, label, title]) => (
              <button
                key={mode}
                type="button"
                role="radio"
                aria-checked={themeMode === mode}
                title={title}
                className={"seg" + (themeMode === mode ? " active" : "")}
                onClick={() => chooseTheme(mode)}
              >
                {label}
              </button>
            ))}
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
        <button className="profile-setting-row" onClick={() => navigate("/me/feedback")}>
          <div className="profile-lang-key">
            <Icon name="message" size={18} color="var(--ink-3)" />
            <span>{t("profile.feedback")}</span>
          </div>
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
