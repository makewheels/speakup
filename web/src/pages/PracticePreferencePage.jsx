import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/useUser.js";
import { useT } from "../i18n/useI18n.js";
import Icon from "../components/Icon.jsx";
import PracticePreferencePicker from "../components/PracticePreferencePicker.jsx";
import {
  getPracticePreferences,
  savePracticePreferences,
} from "../lib/practicePreferences.js";
import { api } from "../api/client.js";

export default function PracticePreferencePage() {
  const { user } = useUser();
  const navigate = useNavigate();
  const t = useT();
  const [prefs, setPrefs] = useState(() => getPracticePreferences(user?.userId));
  const [toast, setToast] = useState("");
  const toastTimerRef = useRef(null);

  useEffect(() => () => clearTimeout(toastTimerRef.current), []);

  // 服务端是事实源：进入页面先对账，跨设备看到的都是同一份设置
  useEffect(() => {
    if (!user?.userId) return undefined;
    let cancelled = false;
    api.getPracticePreferences(user.userId).then((serverPrefs) => {
      if (cancelled) return;
      setPrefs(savePracticePreferences(user.userId, serverPrefs));
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [user?.userId]);

  if (!user) return null;

  const summary = (value) => t("practicePrefs.summary", {
    level: t(`practicePrefs.level.${value.level}`),
    purpose: t(`practicePrefs.purpose.${value.purpose}`),
  });

  const updatePrefs = (next) => {
    const saved = savePracticePreferences(user.userId, next);
    setPrefs(saved);
    api.savePracticePreferences({ userId: user.userId, ...saved }).catch(console.error);
    setToast(t("practicePrefs.saved", { summary: summary(saved) }));
    clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(""), 1800);
  };

  return (
    <div className="pref-settings-page fade-in">
      <button className="page-back" onClick={() => navigate("/me")}>
        <Icon name="back" size={16} />
        <span>{t("common.back")}</span>
      </button>

      <div className="pref-settings-head">
        <div className="eyebrow">{t("profile.practicePreference")}</div>
        <h1>{summary(prefs)}</h1>
        <p>{t("practicePrefs.settingsSub")}</p>
      </div>

      <PracticePreferencePicker value={prefs} onChange={updatePrefs} t={t} />

      {toast && (
        <div className="pref-toast" role="status">
          <Icon name="check" size={15} />
          <span>{toast}</span>
        </div>
      )}
    </div>
  );
}
