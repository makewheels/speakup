import Icon from "../Icon.jsx";
import PracticePreferencePicker from "../PracticePreferencePicker.jsx";

/**
 * 首次练习的偏好欢迎页（选水平/目标）。纯展示组件，状态在 PracticePage。
 * Props: modeSwitch, value, onChange, onStart, t
 */
export default function PracticePrefsWelcome({ modeSwitch, value, onChange, onStart, t }) {
  return (
    <div className="practice-page pref-welcome fade-in">
      {modeSwitch}
      <div className="pref-hero">
        <div className="pref-hero-main">
          <h1>{t("practicePrefs.welcomeTitle")}</h1>
        </div>
      </div>

      <PracticePreferencePicker
        value={value}
        onChange={onChange}
        t={t}
      />

      <button className="su-btn su-btn-primary pref-start" onClick={onStart}>
        {t("practicePrefs.start")}
        <Icon name="next" size={16} />
      </button>
    </div>
  );
}
