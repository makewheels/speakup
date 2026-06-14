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
  const initial = user.nickname?.charAt(0)?.toUpperCase() || "U";

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
          <span>Speech</span>
          <span className="v">All platforms</span>
        </div>
        <div className="info-row">
          <span>Version</span>
          <span className="v">v0.1 · DEMO</span>
        </div>
      </div>

      <button className="su-btn su-btn-danger" onClick={handleLogout}>
        Log out
      </button>
    </div>
  );
}
