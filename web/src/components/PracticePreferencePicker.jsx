import {
  LEVEL_OPTIONS,
  PURPOSE_OPTIONS,
} from "../lib/practicePreferences.js";

function OptionGrid({ label, value, options, name, onChange, labelFor, descFor }) {
  return (
    <div className="pref-group">
      <div className="pref-label">{label}</div>
      <div className="pref-grid" role="radiogroup" aria-label={label}>
        {options.map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={value === option}
            className={"pref-option" + (value === option ? " active" : "")}
            onClick={() => onChange(option)}
          >
            <span className="pref-option-title">{labelFor(name, option)}</span>
            <span className="pref-option-desc">{descFor(name, option)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default function PracticePreferencePicker({ value, onChange, t }) {
  const prefs = value;
  const labelFor = (name, option) => t(`practicePrefs.${name}.${option}`);
  const descFor = (name, option) => t(`practicePrefs.${name}Desc.${option}`);

  return (
    <div className="pref-picker">
      <OptionGrid
        label={t("practicePrefs.levelTitle")}
        value={prefs.level}
        options={LEVEL_OPTIONS}
        name="level"
        labelFor={labelFor}
        descFor={descFor}
        onChange={(level) => onChange({ ...prefs, level })}
      />
      <OptionGrid
        label={t("practicePrefs.purposeTitle")}
        value={prefs.purpose}
        options={PURPOSE_OPTIONS}
        name="purpose"
        labelFor={labelFor}
        descFor={descFor}
        onChange={(purpose) => onChange({ ...prefs, purpose })}
      />
    </div>
  );
}
