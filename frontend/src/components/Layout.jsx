/**
 * Layout - the friendly app shell: greeting sidebar, grouped navigation,
 * a live "new alerts" bell, system status chips and a mobile drawer.
 * Shows role badge and admin-only links based on the signed-in user.
 */
import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import api from '../api/client.js'

const GROUPS = [
  {
    title: 'Monitor',
    items: [
      { to: '/', label: 'Dashboard', icon: '📊', end: true },
      { to: '/live', label: 'Live Weather', icon: '🌦️' },
      { to: '/data', label: 'Data Explorer', icon: '🗄️' },
    ],
  },
  {
    title: 'Insights',
    items: [
      { to: '/analytics', label: 'Analytics & ML', icon: '🧠' },
      { to: '/forecasts', label: 'Forecasts', icon: '🔮' },
      { to: '/alerts', label: 'Alerts', icon: '🚨', bell: true },
    ],
  },
  {
    title: 'Help & community',
    items: [
      { to: '/feedback', label: 'Support', icon: '💬' },
      { to: '/help', label: 'Help & FAQ', icon: '❓' },
    ],
  },
]

const SEEN_KEY = 'es_seen_alerts'

function greetingFor(hour) {
  if (hour < 12) return { text: 'Good morning', icon: '🌅' }
  if (hour < 17) return { text: 'Good afternoon', icon: '☀️' }
  return { text: 'Good evening', icon: '🌙' }
}

export default function Layout() {
  const { user, isAdmin, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [newAlerts, setNewAlerts] = useState([])
  const [health, setHealth] = useState(null)

  const greeting = useMemo(() => greetingFor(new Date().getHours()), [])
  const today = useMemo(
    () => new Date().toLocaleDateString(undefined, {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    }), [])

  /* Poll for fresh alerts so the bell can badge "what's new since you arrived" */
  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const { data } = await api.get('/alerts/history?limit=60&severity=warning')
        if (!active) return
        const seen = new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || '[]'))
        const fresh = (data.alerts || []).filter(
          (a) => (a.severity === 'critical' || a.severity === 'warning')
                 && !seen.has(a.alert_id))
        setNewAlerts(fresh)
      } catch { /* backend asleep — badge stays quiet */ }
    }
    load()
    const timer = setInterval(load, 30000)
    return () => { active = false; clearInterval(timer) }
  }, [])

  /* Visiting the Alerts page marks everything as seen */
  useEffect(() => {
    if (location.pathname !== '/alerts' || newAlerts.length === 0) return
    const seen = new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || '[]'))
    newAlerts.forEach((a) => seen.add(a.alert_id))
    localStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-400)))
    setNewAlerts([])
  }, [location.pathname, newAlerts])

  /* System status chips (storage + database backend) */
  useEffect(() => {
    api.get('/health').then(({ data }) => setHealth(data)).catch(() => {})
  }, [])

  /* Close the mobile drawer whenever navigation happens */
  useEffect(() => { setDrawerOpen(false) }, [location.pathname])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const renderLink = (item) => (
    <NavLink key={item.to} to={item.to} end={item.end}
      className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
      <span className="nav-icon" aria-hidden="true">{item.icon}</span>
      {item.label}
      {item.bell && newAlerts.length > 0 && (
        <span className="nav-badge" title={`${newAlerts.length} new alert(s)`}>
          {newAlerts.length}
        </span>
      )}
    </NavLink>
  )

  return (
    <div className="app-shell">
      <button className="hamburger" onClick={() => setDrawerOpen(true)}
        aria-label="Open navigation menu">☰</button>
      {drawerOpen && (
        <button className="sidebar-backdrop" aria-label="Close menu"
          onClick={() => setDrawerOpen(false)} />
      )}

      <aside className={`sidebar${drawerOpen ? ' open' : ''}`}>
        <button className="sidebar-close" onClick={() => setDrawerOpen(false)}
          aria-label="Close navigation menu">✕</button>

        <div className="brand">
          <span className="brand-icon" aria-hidden="true">🌍</span>
          <div>
            <h1>EarthScape</h1>
            <p>Climate Agency</p>
          </div>
        </div>

        <nav aria-label="Main navigation">
          {GROUPS.map((group) => (
            <div className="nav-group" key={group.title}>
              <div className="nav-group-title">{group.title}</div>
              {group.items.map(renderLink)}
            </div>
          ))}
          {isAdmin && (
            <div className="nav-group">
              <div className="nav-group-title">Administration</div>
              {renderLink({ to: '/admin', label: 'Admin Console', icon: '⚙️' })}
            </div>
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="user-chip">
            <strong title={user?.username}>{user?.username}</strong>
            <span className={`role-badge role-${user?.role}`}>{user?.role}</span>
          </div>
          <div className="status-row" title="Connected backends">
            <span className="status-chip">
              <span className="dot" aria-hidden="true" />
              {health?.storage_backend || 'storage'}
            </span>
            <span className="status-chip">
              <span className="dot" aria-hidden="true" />
              {health?.database_backend || 'database'}
            </span>
          </div>
          <button className="btn btn-outline btn-sm" onClick={handleLogout}>
            👋 Sign out
          </button>
        </div>
      </aside>

      <main className="content">
        <div className="sr-only" aria-live="polite">
          {`${greeting.text}, ${user?.username}. ${today}`}
        </div>
        <Outlet />
      </main>
    </div>
  )
}

/** Reusable friendly header used by every page. */
export function PageHeader({ title, subtitle, actions, wave = false }) {
  return (
    <header className="page-header">
      <div>
        <h2>
          {title}
          {wave && <span className="wave" aria-hidden="true"> 👋</span>}
        </h2>
        {subtitle && <p className="page-sub">{subtitle}</p>}
      </div>
      {actions && <div className="header-actions">{actions}</div>}
    </header>
  )
}

export { greetingFor }
