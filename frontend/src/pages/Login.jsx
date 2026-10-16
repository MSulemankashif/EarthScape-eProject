/**
 * Login - a warm, welcoming sign-in screen with a built-in register flow.
 * Demo accounts are one click away (chips fill the form), passwords can be
 * peeked, lockouts are explained kindly, and newcomers can create their own
 * analyst account without leaving the page.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import api, { errorMessage } from '../api/client.js'

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
  const [mode, setMode] = useState('login')          // 'login' | 'register'
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const isRegister = mode === 'register'

  const fillDemo = (acct) => {
    setMode('login')
    setUsername(acct.username)
    setPassword(acct.password)
    setError('')
    toast.info(`Filled in the ${acct.role.toLowerCase()} demo account — just press Sign in.`)
  }

  const switchMode = (next) => {
    setMode(next)
    setError('')
    setPassword('')
    setConfirm('')
  }

  const submit = async (e) => {
    e.preventDefault()
    if (isRegister) {
      if (!username.trim() || !email.trim() || !password) {
        setError('Please fill in username, email and password.')
        return
      }
      if (!/^\S+@\S+\.\S+$/.test(email)) {
        setError('That email address does not look quite right.')
        return
      }
      if (password.length < 6) {
        setError('Pick a password of at least 6 characters.')
        return
      }
      if (password !== confirm) {
        setError('The two passwords do not match.')
        return
      }
    } else if (!username || !password) {
      setError('Please enter both your username and password.')
      return
    }

    setBusy(true)
    setError('')

    if (isRegister) {
      try {
        await api.post('/auth/register',
          { username: username.trim(), email: email.trim(), password })
      } catch (err) {
        setBusy(false)
        setError(errorMessage(err, 'Could not create the account'))
        return
      }
    }

    const result = await login(username.trim(), password)
    setBusy(false)
    if (result.ok) {
      toast.success(isRegister
        ? `Welcome aboard, ${username.trim()}! Your analyst seat is ready 🌱`
        : `Welcome back, ${username.trim()}! 🌍`)
      navigate('/')
    } else {
      setError(isRegister
        ? `Account created, but auto sign-in failed: ${result.error}`
        : result.error)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="welcome">
          <span className="brand-icon" aria-hidden="true" style={{ fontSize: 46 }}>
            {isRegister ? '🌱' : '🌍'}
          </span>
          <h2>{isRegister ? 'Create your account' : 'Welcome back'}</h2>
          <p>
            {isRegister
              ? 'Join the EarthScape climate analytics console as an analyst'
              : 'Sign in to the EarthScape climate analytics console'}
          </p>
        </div>

        {error && (
          <div className="alert alert-error" role="alert">{error}</div>
        )}

        {isRegister && (
          <label>
            Email
            <input type="email" value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com" autoComplete="email" autoFocus />
          </label>
        )}
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)}
            placeholder="e.g. analyst" autoComplete="username"
            autoFocus={!isRegister} />
        </label>
        <label>
          Password
          <span className="password-wrap">
            <input type={showPassword ? 'text' : 'password'} value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete={isRegister ? 'new-password' : 'current-password'} />
            <button type="button" className="peek"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}>
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </span>
        </label>

        {isRegister && (
          <label>
            Confirm password
            <input type={showPassword ? 'text' : 'password'} value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="••••••••" autoComplete="new-password" />
          </label>
        )}

        <button className="btn btn-primary" disabled={busy}>
          {busy ? (
            <><span className="spinner spinner-sm" aria-hidden="true" />{' '}
              {isRegister ? 'Creating your seat…' : 'Signing in…'}</>
          ) : (isRegister ? 'Create account 🌱' : 'Sign in →')}
        </button>

        {!isRegister && (
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
        )}

        {isRegister && (
          <p className="muted small" style={{ textAlign: 'center', margin: 0 }}>
            New accounts start as <strong>analysts</strong> — an admin can
            promote you anytime from the Admin Console.
          </p>
        )}

        <button type="button" className="link-btn"
          onClick={() => switchMode(isRegister ? 'login' : 'register')}>
          {isRegister
            ? '← Already have an account? Sign in'
            : 'New to EarthScape? Create an account →'}
        </button>
      </form>
    </div>
  )
}
