import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useUser } from "../context/useUser.js";
import { useT } from "../i18n/useI18n.js";

// 登录成功后回跳：只接受站内路径，拒绝外链/协议相对路径/登录页自身
function safeRedirect(value) {
  if (!value || !/^\/(?!\/)/.test(value)) return "/";
  if (value === "/login" || value.startsWith("/login?") || value.startsWith("/login/")) return "/";
  return value;
}

export default function LoginPage() {
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useUser();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const t = useT();

  const valid = /^1\d{10}$/.test(phone);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!valid) {
      setError(t("login.errorInvalidPhone"));
      return;
    }
    setLoading(true);
    setError("");
    try {
      await login(phone);
      navigate(safeRedirect(searchParams.get("redirect")));
    } catch {
      setError(t("login.errorLoginFailed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="brand">
        <div className="eyebrow brand-eyebrow">{t("login.demoTag")}</div>
        <h1>{t("login.appName")}</h1>
        <p
          className="subtitle"
          dangerouslySetInnerHTML={{ __html: t("login.subtitle") }}
        />
      </div>

      <form onSubmit={handleSubmit} className="login-field">
        <div className="eyebrow" style={{ marginBottom: 10 }}>{t("login.phoneLabel")}</div>
        <div className={`login-field-row${error ? " error" : ""}`}>
          <span className="cc">+86</span>
          <input
            type="tel"
            inputMode="numeric"
            placeholder={t("login.phonePlaceholder")}
            value={phone}
            onChange={(e) => {
              setPhone(e.target.value.replace(/\D/g, "").slice(0, 11));
              if (error) setError("");
            }}
            maxLength={11}
          />
        </div>
        {error && <div className="error-text">{error}</div>}
        <p className="hint">{t("login.hint")}</p>

        <div className="spacer" />

        <button
          type="submit"
          className={`su-btn su-btn-primary submit${!valid && !loading ? " disabled" : ""}`}
          disabled={!valid || loading}
        >
          {loading ? (<><span className="spin" />&nbsp;{t("login.enter")}</>) : t("login.enter")}
        </button>
      </form>

      <p className="footer-note">{t("login.footerNote")}</p>
    </div>
  );
}
