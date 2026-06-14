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
      setError("Invalid phone number, please check");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await login(phone);
      navigate("/");
    } catch {
      setError("Login failed, please try again");
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
          See a scene, speak to get it done.<br />
          AI shows you how a native would say it.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="login-field">
        <div className="eyebrow" style={{ marginBottom: 10 }}>Phone</div>
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
        <p className="hint">Enter your phone to sign up — no code needed.</p>

        <div className="spacer" />

        <button
          type="submit"
          className={`su-btn su-btn-primary submit${!valid && !loading ? " disabled" : ""}`}
          disabled={!valid || loading}
        >
          {loading ? (<><span className="spin" />&nbsp;Enter</>) : "Enter"}
        </button>
      </form>

      <p className="footer-note">Works on PC / Android / iOS (Chrome & Safari)</p>
    </div>
  );
}
