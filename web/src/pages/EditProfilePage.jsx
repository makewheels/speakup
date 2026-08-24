import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import AvatarCropDialog from "../components/AvatarCropDialog.jsx";
import Icon from "../components/Icon.jsx";
import ProfileAvatar from "../components/ProfileAvatar.jsx";
import { useUser } from "../context/useUser.js";
import { useT } from "../i18n/useI18n.js";

const MAX_AVATAR_BYTES = 25 * 1024 * 1024;
const AVATAR_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

function maskedPhone(phone = "") {
  return phone ? `${phone.slice(0, 3)} **** ${phone.slice(-4)}` : "";
}

function AvatarEditor({ user, updateAvatar, removeAvatar, t }) {
  const fileInputRef = useRef(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarMessage, setAvatarMessage] = useState("");
  const [avatarError, setAvatarError] = useState("");
  const [cropFile, setCropFile] = useState(null);

  const chooseAvatar = (event) => {
    const [file] = event.target.files || [];
    event.target.value = "";
    if (!file || avatarBusy) return;
    setAvatarError("");
    setAvatarMessage("");
    if (file.size > MAX_AVATAR_BYTES) {
      setAvatarError(t("profile.avatarTooLarge"));
      return;
    }
    if (file.type && !AVATAR_TYPES.has(file.type)) {
      setAvatarError(t("profile.avatarTypeInvalid"));
      return;
    }
    setCropFile(file);
  };

  const saveCroppedAvatar = async (file) => {
    setAvatarBusy(true);
    try {
      await updateAvatar(file);
      setCropFile(null);
      setAvatarMessage(t("profile.avatarSaved"));
    } catch {
      setAvatarError(t("profile.avatarSaveFailed"));
    } finally {
      setAvatarBusy(false);
    }
  };

  const restoreDefaultAvatar = async () => {
    if (avatarBusy) return;
    setAvatarBusy(true);
    setAvatarError("");
    setAvatarMessage("");
    try {
      await removeAvatar();
      setAvatarMessage(t("profile.avatarRemoved"));
    } catch {
      setAvatarError(t("profile.avatarRemoveFailed"));
    } finally {
      setAvatarBusy(false);
    }
  };

  return (
    <section className="profile-editor-section" aria-labelledby="avatar-section-title">
      <div className="profile-editor-section-head">
        <div>
          <h2 id="avatar-section-title">{t("profile.avatar")}</h2>
          <p>{t("profile.avatarHint")}</p>
        </div>
        <ProfileAvatar user={user} alt={t("profile.avatarAlt")} size={72} />
      </div>
      <input
        ref={fileInputRef}
        className="profile-avatar-input"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        aria-label={t("profile.chooseAvatarFile")}
        onChange={chooseAvatar}
      />
      <div className="profile-editor-actions">
        <button
          className="profile-editor-action-primary"
          type="button"
          disabled={avatarBusy}
          onClick={() => fileInputRef.current?.click()}
        >
          {avatarBusy ? t("profile.avatarSaving") : t("profile.changeAvatar")}
        </button>
        {user.avatarUrl && (
          <button
            className="profile-editor-action-quiet"
            type="button"
            disabled={avatarBusy}
            onClick={restoreDefaultAvatar}
          >
            {t("profile.restoreDefaultAvatar")}
          </button>
        )}
      </div>
      {avatarError && <p className="profile-editor-error" role="alert">{avatarError}</p>}
      {avatarMessage && <p className="profile-editor-status" role="status">{avatarMessage}</p>}
      {cropFile && (
        <AvatarCropDialog
          error={avatarError}
          file={cropFile}
          onCancel={() => setCropFile(null)}
          onConfirm={saveCroppedAvatar}
          t={t}
        />
      )}
    </section>
  );
}

function NicknameEditor({ user, updateNickname, t }) {
  const [nickname, setNickname] = useState(user.nickname ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const normalized = nickname.trim().replace(/\s+/g, " ");
  const invalid = !normalized || normalized.length > 24;

  const save = async (event) => {
    event.preventDefault();
    if (invalid || normalized === user.nickname || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const data = await updateNickname(normalized);
      setNickname(data.nickname);
      setMessage(t("profile.nicknameSaved"));
    } catch {
      setError(t("profile.nicknameSaveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="profile-editor-section" onSubmit={save}>
      <label className="profile-editor-label" htmlFor="profile-nickname">
        {t("profile.nicknameInput")}
      </label>
      <input
        id="profile-nickname"
        className="profile-editor-text-input"
        maxLength={24}
        value={nickname}
        onChange={(event) => {
          setNickname(event.target.value);
          setError("");
          setMessage("");
        }}
      />
      <div className="profile-editor-field-meta">
        <span>{t("profile.nicknameHint")}</span>
        <span>{nickname.length}/24</span>
      </div>
      <button
        className="su-btn su-btn-primary profile-editor-save"
        type="submit"
        disabled={invalid || normalized === user.nickname || busy}
      >
        {busy ? t("profile.nicknameSaving") : t("profile.nicknameSave")}
      </button>
      {error && <p className="profile-editor-error" role="alert">{error}</p>}
      {message && <p className="profile-editor-status" role="status">{message}</p>}
    </form>
  );
}

function PhoneSummary({ phone, t }) {
  return (
    <section className="profile-editor-section profile-phone-section">
      <div>
        <h2>{t("profile.phone")}</h2>
        <p>{t("profile.phoneReadonly")}</p>
      </div>
      <div className="profile-phone-value">
        <span>{maskedPhone(phone)}</span>
        <span className="profile-readonly-badge">{t("profile.readonly")}</span>
      </div>
    </section>
  );
}

export default function EditProfilePage() {
  const { user, updateNickname, updateAvatar, removeAvatar } = useUser();
  const navigate = useNavigate();
  const t = useT();

  if (!user) return null;

  return (
    <div className="profile-editor-page fade-in">
      <button className="page-back" type="button" onClick={() => navigate("/me")}>
        <Icon name="back" size={16} />
        <span>{t("common.back")}</span>
      </button>

      <header className="profile-editor-head">
        <div className="eyebrow">{t("profile.accountEyebrow")}</div>
        <h1>{t("profile.editProfile")}</h1>
        <p>{t("profile.editProfileIntro")}</p>
      </header>

      <AvatarEditor {...{ user, updateAvatar, removeAvatar, t }} />
      <NicknameEditor {...{ user, updateNickname, t }} />
      <PhoneSummary phone={user.phone} t={t} />
    </div>
  );
}
