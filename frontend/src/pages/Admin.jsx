/**
 * Admin - user management (admin role only): list users, change roles.
 * Also shows system/health stats.
 */
import { useEffect, useState } from 'react'
import api, { errorMessage } from '../api/client.js'

export default function Admin() {
  const [users, setUsers] = useState([])
  const [system, setSystem] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = async () => {
    try {
      const [u, s] = await Promise.all([
        api.get('/auth/users'),
        api.get('/system/stats'),
      ])
      setUsers(u.data.users)
      setSystem(s.data)
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  useEffect(() => { load() }, [])

  const setRole = async (username, role) => {
    setNotice('')
    try {
      const { data } = await api.patch(`/auth/users/${username}/role`, { role })
      setNotice(data.message)
      load()
    } catch (err) {
      setNotice(errorMessage(err))
    }
  }

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Administration</h2>
          <p className="muted">User management & system health.</p>
        </div>
      </header>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-info">{notice}</div>}

      <div className="grid-2">
        <div className="card">
          <h3>Users ({users.length})</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Username</th><th>Email</th><th>Role</th>
                  <th>Status</th><th>Last login</th><th></th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.username}>
                    <td>{u.username}</td>
                    <td>{u.email}</td>
                    <td><span className={`role-badge role-${u.role}`}>{u.role}</span></td>
                    <td>{u.active ? '🟢 active' : '⚪ disabled'}</td>
                    <td>{u.last_login?.slice(0, 16).replace('T', ' ') || '—'}</td>
                    <td>
                      <select value={u.role}
                        onChange={(e) => setRole(u.username, e.target.value)}>
                        <option value="analyst">analyst</option>
                        <option value="admin">admin</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <h3>System health</h3>
          {system ? (
            <div className="model-status">
              <span className="tag tag-ok">uptime {(system.uptime_seconds / 60).toFixed(1)} min</span>
              <span className="tag">storage: {system.storage.backend}</span>
              <span className="tag">db: {system.database.backend}</span>
              <span className="tag">cpu: {system.cpu_count} cores</span>
              <span className="tag">storage used: {(system.storage.total_bytes / 1024 / 1024).toFixed(2)} MB</span>
              <span className={system.stream_active ? 'tag tag-ok' : 'tag'}>
                live stream: {system.stream_active ? 'active' : 'idle'}
              </span>
              <span className="tag tag-warn">alerts: {system.alerts.total} total
                ({system.alerts.by_severity.critical} critical)</span>
              <span className={system.models.anomaly_model_trained ? 'tag tag-ok' : 'tag'}>
                ml models: {system.models.anomaly_model_trained ? 'trained' : 'not trained'}
              </span>
              {system.log_files.map((f) => (
                <span className="tag" key={f.name}>📄 {f.name} ({f.size_kb} KB)</span>
              ))}
            </div>
          ) : (
            <p className="muted">Loading…</p>
          )}
        </div>
      </div>
    </div>
  )
}
