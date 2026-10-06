import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/anomalies", label: "Anomalies" },
  { to: "/forecasts", label: "Forecasts" },
  { to: "/correlations", label: "Correlations" },
  { to: "/live", label: "Live view" },
  { to: "/alerts", label: "Alerts" },
  { to: "/support", label: "Support" },
  { to: "/help", label: "Help" },
];

const ADMIN_NAV = [
  { to: "/admin/users", label: "Users" },
  { to: "/admin/ingestion", label: "Ingestion" },
  { to: "/admin/models", label: "Models" },
  { to: "/admin/monitoring", label: "Monitoring" },
  { to: "/admin/audit", label: "Audit log" },
];

const link = ({ isActive }) => "nav-link" + (isActive ? " active" : "");

export default function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <aside className="sidebar">
        <h1 className="brand">🌍 EarthScape</h1>
        <nav>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={link}>
              {n.label}
            </NavLink>
          ))}
          {user?.role === "admin" && (
            <>
              <div className="nav-section">Admin</div>
              {ADMIN_NAV.map((n) => (
                <NavLink key={n.to} to={n.to} className={link}>
                  {n.label}
                </NavLink>
              ))}
            </>
          )}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <span className="muted">
            {user?.email} · <span className="badge">{user?.role}</span>
          </span>
          <button onClick={logout}>Log out</button>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
