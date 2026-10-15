/**
 * Login - authentication screen. Demo credentials are pre-filled.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('analyst')
  const [password, setPassword] = useState('analyst@123')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    const result = await login(username, password)
    setBusy(false)
    if (result.ok) navigate('/')
    else setError(result.error)
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="brand brand-center">
          <span className="brand-icon">🌍</span>
          <div>
            <h1>EarthScape</h1>
            <p>Climate Agency — Big Data Analytics</p>
          </div>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)}
            placeholder="analyst" autoFocus />
        </label>
        <label>
          Password
          <input type="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••" />
        </label>
        <button className="btn btn-primary" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>

        <div className="login-hint">
          <p><strong>Demo accounts</strong></p>
          <p>admin / admin@123 — full access</p>
          <p>analyst / analyst@123 — analytics only</p>
        </div>
      </form>
    </div>
  )
}
