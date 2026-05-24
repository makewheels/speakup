import { Outlet, NavLink } from "react-router-dom";
import { useEffect, useState } from "react";
import { useUser } from "../../context/UserContext.jsx";
import { api } from "../../api/client.js";
import Icon from "../Icon.jsx";

const TABS = [
  { to: "/practice",   label: "练习", icon: "home" },
  { to: "/vocabulary", label: "复习", icon: "book", showDue: true },
  { to: "/me",         label: "我的", icon: "user" },
];

export default function Layout() {
  const { user } = useUser();
  const [dueCount, setDueCount] = useState(0);

  useEffect(() => {
    if (!user) return;
    api.listVocabulary(user.userId, true)
      .then((items) => setDueCount(items.length))
      .catch(() => setDueCount(0));
  }, [user]);

  return (
    <div className="app-shell">
      <main className="app-main">
        <Outlet />
      </main>
      <nav className="su-tabbar">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.to === "/practice"}
            className={({ isActive }) => `su-tab${isActive ? " active" : ""}`}
          >
            {({ isActive }) => (
              <>
                <Icon name={t.icon} size={22} stroke={isActive ? 1.9 : 1.5} />
                <span>{t.label}</span>
                {t.showDue && dueCount > 0 && <span className="badge">{dueCount}</span>}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
