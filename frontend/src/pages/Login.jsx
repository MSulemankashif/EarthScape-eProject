/**
 * Login - a warm, welcoming sign-in screen.
 * Demo accounts are one click away (chips fill the form),
 * passwords can be peeked, and lockouts are explained kindly.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'

const DEMO_ACCOUNTS = [
  { role: 'Admin', username: 'admin', password: 'admin@123',
    note: 'full access · users, rules, backups' },
  { role: 'Analyst', username: 'analyst', password: 'analyst@123',
    note: 'analytics & alerts only' },
]

export default function Login() {
  const { login } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const fillDemo = (acct) => {
    setUsername(acct.username)
    setPassword(acct.password)
    setError('')
    toast.info(`Filled in the ${acct.role.toLowerCase()} demo account — just press Sign in.`)
  }

  const submit = async (e) => {
    e.preventDefault()
    if (!username || !password) {
      setError('Please enter both your username and password.')
      return
    }
    setBusy(true)
    setError('')
    const result = await login(username, password)
    setBusy(false)
    if (result.ok) {
      toast.success(`Welcome back, ${username}! 🌍`)
      navigate('/')
    } else {
      setError(result.error)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="welcome">
          <span className="brand-icon" aria-hidden="true" style={{ fontSize: 46 }}>🌍</span>
          <h2>Welcome back</h2>
          <p>Sign in to the EarthScape climate analytics console</p>
        </div>

        {error && (
          <div className="alert alert-error" role="alert">{error}</div>
        )}

        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)}
            placeholder="e.g. analyst" autoComplete="username" autoFocus />
        </label>
        <label>
          Password
          <span className="password-wrap">
            <input type={showPassword ? 'text' : 'password'} value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••" autoComplete="current-password" />
            <button type="button" className="peek"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}>
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </span>
        </label>

        <button className="btn btn-primary" disabled={busy}>
          {busy ? (
            <><span className="spinner spinner-sm" aria-hidden="true" /> Signing in…</>
          ) : 'Sign in →'}
        </button>

        <div className="login-hint">
          <p><strong>Just exploring? Use a demo account:</strong></p>
          <div className="demo-chips">
            {DEMO_ACCOUNTS.map((acct) => (
              <button type="button" key={acct.username} className="demo-chip"
                onClick={() => fillDemo(acct)}>
                <strong>{acct.role} ↗</strong>
                {acct.username} · {acct.note}
              </button>
            ))}
          </div>
        </div>
      </form>
    </div>
  )
}
