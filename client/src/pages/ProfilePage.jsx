import { useUser } from "../context/UserContext.jsx";
import { useNavigate } from "react-router-dom";

export default function ProfilePage() {
  const { user, logout } = useUser();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const maskedPhone = user.phone
    ? `${user.phone.slice(0, 3)} **** ${user.phone.slice(-4)}`
    : "";
  const initial = user.nickname?.charAt(0) || "用";

  return (
    <div className="profile-page">
      <div className="who">
        <div className="avatar">{initial}</div>
        <div>
          <div className="nickname">{user.nickname}</div>
          <div className="phone">{maskedPhone}</div>
        </div>
      </div>

      <div className="info-list">
        <div className="info-row">
          <span>语音识别</span>
          <span className="v">Chrome only</span>
        </div>
        <div className="info-row">
          <span>反馈方式</span>
          <span className="v">未配置</span>
        </div>
        <div className="info-row">
          <span>版本</span>
          <span className="v">v0.1 · DEMO</span>
        </div>
      </div>

      <button className="su-btn su-btn-danger" onClick={handleLogout}>
        退出登录
      </button>
    </div>
  );
}
