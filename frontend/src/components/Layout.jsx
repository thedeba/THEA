import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../api";
import { useAlerts } from "../alerts";
import { useAuth } from "../auth";
import Icon from "./Icons";
import { formatClock } from "../utils";

const navigation = [
  { to: "/", label: "Dashboard", icon: "dashboard", end: true },
  { to: "/alerts", label: "Alerts", icon: "alerts" },
  { to: "/watchlist", label: "Watchlist", icon: "watchlist" },
  { to: "/search", label: "Search", icon: "search" },
  { to: "/settings", label: "Settings", icon: "sliders" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const { connected, soundEnabled, popupsEnabled, toggleSound, togglePopups } = useAlerts();
  const location = useLocation();
  const [health, setHealth] = useState(null);
  const [clock, setClock] = useState(() => new Date());
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!sidebarOpen) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setSidebarOpen(false);
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [sidebarOpen]);

  useEffect(() => {
    const timer = window.setInterval(() => setClock(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api("/api/health")
        .then((data) => {
          if (!cancelled) setHealth(data);
        })
        .catch(() => {});
    };
    load();
    const timer = window.setInterval(load, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const engine = health?.face_engine;
  const engineLabel = engine?.backend === "mock" ? "Mock engine" : engine?.ready ? "Engine ready" : "Engine loading";
  const monitoring = health?.monitoring_enabled ?? true;

  return (
    <div className={`app-shell${sidebarOpen ? " sidebar-open" : ""}`}>
      <button
        type="button"
        className="sidebar-backdrop"
        aria-label="Close navigation"
        onClick={() => setSidebarOpen(false)}
      />
      <aside
        id="app-sidebar"
        className={`sidebar${sidebarOpen ? " open" : ""}`}
        aria-hidden={!sidebarOpen}
      >
        <div className="sidebar-head">
          <div className="brand">
            <span className="brand-mark">
              <Icon name="shield" size={23} />
            </span>
            <div>
              <strong>THEA</strong>
              <span>Local security</span>
            </div>
          </div>
          <button
            type="button"
            className="icon-button sidebar-close"
            onClick={() => setSidebarOpen(false)}
            tabIndex={sidebarOpen ? undefined : -1}
            aria-label="Close navigation"
          >
            ×
          </button>
        </div>

        <nav className="nav">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              tabIndex={sidebarOpen ? undefined : -1}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-status">
          <div className="status-line">
            <span className={`status-dot ${engine?.ready ? "online" : "warn"}`} />
            <span>{engineLabel}</span>
          </div>
          <div className="status-line">
            <span className={`status-dot ${health?.cameras_online ? "online" : "offline"}`} />
            <span>
              {health ? `${health.cameras_online}/${health.cameras} cameras` : "Camera status"}
            </span>
          </div>
          <div className="status-line">
            <span className={`status-dot ${monitoring ? "online" : "warn"}`} />
            <span>{monitoring ? "Monitoring active" : "Monitoring paused"}</span>
          </div>
          <div className="status-line">
            <span className="status-dot neutral" />
            <span>{health ? `${health.watchlist_people} on watchlist` : "Watchlist"}</span>
          </div>
          {health ? <p className="sidebar-footnote">{health.watchlist_index} search index</p> : null}
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="ghost-button menu-toggle"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation"
              aria-expanded={sidebarOpen}
              aria-controls="app-sidebar"
            >
              <Icon name="menu" size={18} />
            </button>
            <Link to="/" className="topbar-brand" aria-label="THEA dashboard">
              <span className="brand-mark">
                <Icon name="shield" size={18} />
              </span>
              <div>
                <strong>THEA</strong>
                <span>Local security</span>
              </div>
            </Link>
            <div className="connection-status">
              <span className={`status-dot ${connected ? "online" : "warn"}`} />
              <span className="connection-label">
                {connected ? "LIVE ALERT LINK" : "RECONNECTING TO ALERT LINK"}
              </span>
            </div>
          </div>
          <div className="topbar-actions">
            <div className="topbar-clock">
              <Icon name="clock" size={14} />
              <span>{formatClock(clock)}</span>
            </div>
            <button
              type="button"
              className={`ghost-button${popupsEnabled ? "" : " is-muted"}`}
              onClick={togglePopups}
              title={popupsEnabled ? "Pause alert popups" : "Enable alert popups"}
            >
              <Icon name={popupsEnabled ? "zap" : "pause"} size={16} />
              <span className="hide-small">{popupsEnabled ? "Popups on" : "Popups paused"}</span>
            </button>
            <button
              type="button"
              className={`ghost-button${soundEnabled ? "" : " is-muted"}`}
              onClick={toggleSound}
              title={soundEnabled ? "Mute warning alarm" : "Enable warning alarm"}
            >
              <Icon name={soundEnabled ? "volume" : "muted"} size={16} />
              <span className="hide-small">{soundEnabled ? "Alarm on" : "Alarm off"}</span>
            </button>
            <span className="user-chip">{user?.username}</span>
            <button type="button" className="ghost-button" onClick={logout}>
              <Icon name="logout" size={16} />
              <span className="hide-small">Sign out</span>
            </button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
