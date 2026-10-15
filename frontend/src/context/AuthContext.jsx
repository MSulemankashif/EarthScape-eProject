/**
 * AuthContext - holds the logged-in user, exposes login/logout helpers.
 * Role information is used to hide admin-only controls in the UI.
 */
import { createContext, useContext, useState } from 'react'
import api, { errorMessage } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem('earthscape_user')
    return raw ? JSON.parse(raw) : null
  })

  const login = async (username, password) => {
    try {
      const { data } = await api.post('/auth/login', { username, password })
      localStorage.setItem('earthscape_token', data.token)
      localStorage.setItem('earthscape_user', JSON.stringify(data.user))
      setUser(data.user)
      return { ok: true, user: data.user }
    } catch (err) {
      return { ok: false, error: errorMessage(err, 'Login failed') }
    }
  }

  const logout = () => {
    localStorage.removeItem('earthscape_token')
    localStorage.removeItem('earthscape_user')
    setUser(null)
  }

  const isAdmin = user?.role === 'admin'

  return (
    <AuthContext.Provider value={{ user, isAdmin, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
