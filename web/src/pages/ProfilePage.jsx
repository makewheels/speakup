import { useState } from "react";
import { useUser } from "../context/useUser.js";
import { useNavigate } from "react-router-dom";
import { useT, useLang } from "../i18n/useI18n.js";
import Icon from "../components/Icon.jsx";
import {
  getPracticePreferences,
} from "../lib/practicePreferences.js";
import {
  getThemeMode,
  setThemeMode,
  resolveTheme,
  applyTheme,
} from "../lib/theme.js";

function NicknameEditor({ user, updateNickname, t }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(user.nickname ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const cancel = () => {
    setDraft(user.nickname ?? "");
    setError("");
    setEditing(false);
  };

  const save = async (event) => {
    event.preventDefault();
    const nickname = draft.trim().replace(/\s+/g, " ");
    if (!nickname || nickname.length > 24 || busy) return;
    setBusy(true);
    setError("");
    try {
      await updateNickname(nickname);
      setEditing(false);
    } catch {
      setError(t("profile.nicknameSaveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const maskedPhone = user.phone
    ? `${user.phone.slice(0, 3)} **** ${user.phone.slice(-4)}`
    : "";

  return (
    <div className="profile-identity">
      {editing ? (
        <form className="profile-nickname-form" onSubmit={save}>
          <input
            autoFocus
            aria-label={t("profile.nicknameInput")}
            className="profile-nickname-input"
            maxLength={24}
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
              if (error) setError("");
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") cancel();
            }}
          />
          <div className="profile-nickname-actions">
            <button
              className="profile-nickname-save"
              type="submit"
              disabled={!draft.trim() || busy}
            >
              {busy ? t("profile.nicknameSaving") : t("profile.nicknameSave")}
            </button>
            <button
              className="profile-nickname-cancel"
              type="button"
              onClick={cancel}
              disabled={busy}
            >
              {t("profile.nicknameCancel")}
            </button>
          </div>
          {error && <p className="profile-nickname-error" role="alert">{error}</p>}
        </form>
      ) : (
        <div className="profile-nickname-row">
          <div className="nickname">{user.nickname}</div>
          <button
            className="profile-nickname-edit"
            type="button"
            onClick={() => {
              setDraft(user.nickname ?? "");
              setError("");
              setEditing(true);
            }}
          >
            {t("profile.nicknameEdit")}
          </button>
        </div>
      )}
      <div className="phone">{maskedPhone}</div>
    </div>
  );
}

export default function ProfilePage() {
  const { user, updateNickname, logout } = useUser();
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

  const initial = user.nickname?.charAt(0)?.toUpperCase() || "U";
  const prefSummary = t("practicePrefs.summary", {
    level: t(`practicePrefs.level.${practicePrefs.level}`),
    purpose: t(`practicePrefs.purpose.${practicePrefs.purpose}`),
  });

  return (
    <div className="profile-page">
      <div className="who">
        <div className="avatar">{initial}</div>
        <NicknameEditor user={user} updateNickname={updateNickname} t={t} />
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
