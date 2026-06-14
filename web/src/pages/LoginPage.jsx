import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";

export default function LoginPage() {
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useUser();
  const navigate = useNavigate();

  const valid = /^1\d{10}$/.test(phone);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!valid) {
      setError("手机号格式不对，请重新输入");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await login(phone);
      navigate("/");
    } catch {
      setError("登录失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="brand">
        <div className="eyebrow brand-eyebrow">v0.1 · DEMO</div>
        <h1>SpeakUp</h1>
        <p className="subtitle">
          看场景，开口完成任务。<br />
          AI 帮你对照 native 怎么说。
        </p>
      </div>

      <form onSubmit={handleSubmit} className="login-field">
        <div className="eyebrow" style={{ marginBottom: 10 }}>手机号</div>
        <div className={`login-field-row${error ? " error" : ""}`}>
          <span className="cc">+86</span>
          <input
            type="tel"
            inputMode="numeric"
            placeholder="138 0000 0000"
            value={phone}
            onChange={(e) => {
              setPhone(e.target.value.replace(/\D/g, "").slice(0, 11));
              if (error) setError("");
            }}
            maxLength={11}
          />
        </div>
        {error && <div className="error-text">{error}</div>}
        <p className="hint">输入手机号即注册，无需验证码。</p>

        <div className="spacer" />

        <button
          type="submit"
          className={`su-btn su-btn-primary submit${!valid && !loading ? " disabled" : ""}`}
          disabled={!valid || loading}
        >
          {loading ? (<><span className="spin" />&nbsp;进入</>) : "进入"}
        </button>
      </form>

      <p className="footer-note">建议电脑或 Android Chrome 使用（iOS 暂不支持麦克风识别）</p>
    </div>
  );
}
