import { Outlet, NavLink } from "react-router-dom";

export default function Layout() {
  return (
    <div className="app-shell">
      <main className="app-main">
        <Outlet />
      </main>
      <nav className="bottom-nav">
        <NavLink to="/practice" end>
          🏠 练习
        </NavLink>
        <NavLink to="/history">
          📋 历史
        </NavLink>
        <NavLink to="/vocabulary">
          📖 生词本
        </NavLink>
      </nav>
    </div>
  );
}
