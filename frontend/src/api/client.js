/**
 * Axios instance preconfigured for the EarthScape Flask API.
 * - Attaches the JWT from localStorage on every request
 * - Redirects to /login when the token expires (401)
 */
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('earthscape_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !error.config.url.includes('/auth/login')) {
      localStorage.removeItem('earthscape_token')
      localStorage.removeItem('earthscape_user')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export const errorMessage = (err, fallback = 'Something went wrong') =>
  err?.response?.data?.error || err?.message || fallback

export default api
