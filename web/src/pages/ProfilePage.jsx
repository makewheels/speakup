import { useUser } from "../context/UserContext.jsx";
import { useNavigate } from "react-router-dom";

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

      <button className="su-btn su-btn-danger" onClick={handleLogout}>
        Log out
      </button>
    </div>
  );
}
