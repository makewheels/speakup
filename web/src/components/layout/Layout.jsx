import { Outlet, NavLink } from "react-router-dom";
import { useEffect, useState } from "react";
import { useUser } from "../../context/useUser.js";
import { useT } from "../../i18n/useI18n.js";
import { api } from "../../api/client.js";
import Icon from "../Icon.jsx";

const TABS = [
  { to: "/practice",   key: "practice", icon: "home" },
  { to: "/review",     key: "review",   icon: "book", showDue: true },
  { to: "/history",    key: "history",  icon: "clock" },
  { to: "/me",         key: "me",       icon: "user" },
];

export default function Layout() {
  const { user } = useUser();
  const t = useT();
  const [dueCount, setDueCount] = useState(0);

  useEffect(() => {
    if (!user) return;
    api.listReviewItems(user.userId, true)
      .then((items) => setDueCount(items.length))
      .catch(() => setDueCount(0));
  }, [user]);

  return (
    <div className="app-shell">
      <main className="app-main">
        <Outlet />
      </main>
      <nav className="su-tabbar">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.to === "/practice"}
            className={({ isActive }) => `su-tab${isActive ? " active" : ""}`}
          >
            {({ isActive }) => (
              <>
                <Icon name={tab.icon} size={22} stroke={isActive ? 1.9 : 1.5} />
                <span>{t(`nav.${tab.key}`)}</span>
                {tab.showDue && dueCount > 0 && <span className="badge">{dueCount}</span>}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
