import { useUser } from "../context/UserContext.jsx";
import { useNavigate } from "react-router-dom";
import Icon from "../components/Icon.jsx";

export default function ProfilePage() {
  const { user, logout } = useUser();
  const navigate = useNavigate();

  if (!user) return null;

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

      <button className="profile-entry" onClick={() => navigate("/shares")}>
        <Icon name="share" size={18} color="var(--ink-3)" />
        <span>My shares</span>
        <Icon name="next" size={16} color="var(--ink-4)" />
      </button>

      <button className="su-btn su-btn-danger" onClick={handleLogout}>
        Log out
      </button>
    </div>
  );
}

