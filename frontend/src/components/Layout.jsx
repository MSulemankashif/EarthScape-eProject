/**
 * Layout - sidebar navigation + topbar + routed outlet.
 * Shows role badge and admin-only links based on the signed-in user.
 */
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

const NAV = [
  { to: '/', label: 'Dashboard', icon: '📊', end: true },
  { to: '/live', label: 'Live Stream', icon: '📡' },
  { to: '/data', label: 'Data Explorer', icon: '🗄️' },
  { to: '/analytics', label: 'Analytics & ML', icon: '🧠' },
  { to: '/forecasts', label: 'Forecasts', icon: '🔮' },
  { to: '/alerts', label: 'Alerts', icon: '🚨' },
  { to: '/feedback', label: 'Support', icon: '💬' },
]

export default function Layout() {
  const { user, isAdmin, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon">🌍</span>
          <div>
            <h1>EarthScape</h1>
            <p>Climate Agency</p>
          </div>
        </div>
        <nav>
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
              <span className="nav-icon">{item.icon}</span> {item.label}
            </NavLink>
          ))}
          {isAdmin && (
            <NavLink to="/admin" className={({ isActive }) =>
              isActive ? 'nav-link active' : 'nav-link'}>
              <span className="nav-icon">⚙️</span> Admin
            </NavLink>
          )}
        </nav>
        <div className="sidebar-footer">
          <div className="user-chip">
            <strong>{user?.username}</strong>
            <span className={`role-badge role-${user?.role}`}>{user?.role}</span>
          </div>
          <button className="btn btn-outline btn-sm" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
