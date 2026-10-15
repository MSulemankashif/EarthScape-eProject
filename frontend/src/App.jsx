/**
 * App - routing shell for the EarthScape React dashboard.
 * Protected routes require a valid session token.
 */
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext.jsx'
import Layout from './components/Layout.jsx'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import DataExplorer from './pages/DataExplorer.jsx'
import Analytics from './pages/Analytics.jsx'
import Forecasts from './pages/Forecasts.jsx'
import Alerts from './pages/Alerts.jsx'
import LiveStream from './pages/LiveStream.jsx'
import Feedback from './pages/Feedback.jsx'
import Admin from './pages/Admin.jsx'

function Protected({ children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const { user } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route
        path="/"
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="data" element={<DataExplorer />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="forecasts" element={<Forecasts />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="live" element={<LiveStream />} />
        <Route path="feedback" element={<Feedback />} />
        <Route path="admin" element={<Admin />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
