import { NavLink, Outlet } from "react-router-dom";
import { currentEmail, currentRoles, keycloak } from "../lib/keycloak";
import { AlertIcon, ChartIcon, ChatIcon, ListIcon, TruckIcon, WrenchIcon } from "./icons";

const NAV = [
  { to: "/at-risk", label: "At-Risk Fleet", icon: <TruckIcon width={19} height={19} /> },
  { to: "/maintenance", label: "Maintenance", icon: <WrenchIcon width={19} height={19} /> },
  { to: "/alerts", label: "Live Alerts", icon: <AlertIcon width={19} height={19} /> },
  { to: "/copilot", label: "Copilot", icon: <ChatIcon width={19} height={19} /> },
  { to: "/analytics", label: "Analytics", icon: <ChartIcon width={19} height={19} /> },
  { to: "/audit", label: "Audit Log", icon: <ListIcon width={19} height={19} /> },
];

export default function Layout() {
  const roles = currentRoles();
  const email = currentEmail();
  return (
    <div className="app-shell">
      <nav className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <TruckIcon width={20} height={20} color="#06101f" />
          </div>
          <div className="brand-text">
            <h1>FleetPulse</h1>
            <span>Predictive maintenance</span>
          </div>
        </div>
        <div className="nav-section-label">Fleet</div>
        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? "active" : "")}>
            {item.icon}
            {item.label}
          </NavLink>
        ))}
        <div className="user-box">
          <div className="user-email" title={email}>{email}</div>
          {roles.map((r) => (
            <span key={r} className="badge role user-role">{r}</span>
          ))}
          {roles.length === 0 && <span className="user-role">no roles</span>}
          <button className="secondary" onClick={() => keycloak.logout()}>
            Log out
          </button>
        </div>
      </nav>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
