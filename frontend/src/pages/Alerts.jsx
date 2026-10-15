/**
 * Alerts - notification history + configurable threshold rules.
 * Only admins can add/remove/toggle rules.
 */
import { useEffect, useState } from 'react'
import api, { errorMessage } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'

const EMPTY_FORM = { name: '', metric: 'temperature_c', comparator: 'gt',
                     threshold: '', severity: 'warning' }

export default function Alerts() {
  const { isAdmin } = useAuth()
  const [alerts, setAlerts] = useState([])
  const [stats, setStats] = useState(null)
  const [rules, setRules] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [severity, setSeverity] = useState('info')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = async () => {
    try {
      const [a, r] = await Promise.all([
        api.get(`/alerts/history?limit=200&severity=${severity}`),
        api.get('/alerts/rules'),
      ])
      setAlerts(a.data.alerts)
      setStats(a.data.stats)
      setRules(r.data.rules)
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 8000)
    return () => clearInterval(id)
  }, [severity])

  const addRule = async (e) => {
    e.preventDefault()
    setNotice('')
    try {
      const { data } = await api.post('/alerts/rules', {
        ...form, threshold: Number(form.threshold),
      })
      setRules(data.rules)
      setForm(EMPTY_FORM)
      setNotice('Rule saved ✅')
    } catch (err) {
      setNotice(errorMessage(err))
    }
  }

  const toggle = async (rule) => {
    const action = rule.enabled ? 'disable' : 'enable'
    await api.post(`/alerts/rules/${rule.name}/${action}`)
    load()
  }

  const remove = async (name) => {
    if (!window.confirm(`Delete rule "${name}"?`)) return
    await api.delete(`/alerts/rules/${name}`)
    load()
  }

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Alerts & Notifications</h2>
          <p className="muted">
            {stats ? `${stats.total} alerts · ${stats.by_severity.critical} critical · ${stats.by_severity.warning} warnings · ${stats.enabled_rules}/${stats.total_rules} rules active` : ''}
          </p>
        </div>
        <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="info">All severities</option>
          <option value="warning">Warning + critical</option>
          <option value="critical">Critical only</option>
        </select>
      </header>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-info">{notice}</div>}

      <div className="grid-2">
        <div className="card">
          <h3>Alert history</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th><th>Severity</th><th>Station</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.alert_id}>
                    <td>{a.timestamp?.slice(11, 19)}</td>
                    <td>
                      <span className={`tag tag-${a.severity}`}>{a.severity}</span>
                    </td>
                    <td>{a.station_id}</td>
                    <td>{a.message}</td>
                  </tr>
                ))}
                {alerts.length === 0 && (
                  <tr><td colSpan={4} className="muted">
                    No alerts yet. Start the live stream to generate events.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <h3>Threshold rules ({rules.length})</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Rule</th><th>Condition</th><th>Severity</th>
                  <th>Status</th>{isAdmin && <th>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.name}>
                    <td>{r.name}</td>
                    <td><code>{r.metric} {r.comparator === 'gt' ? '>' : '<'} {r.threshold}</code></td>
                    <td><span className={`tag tag-${r.severity}`}>{r.severity}</span></td>
                    <td>{r.enabled ? '🟢 on' : '⚪ off'}</td>
                    {isAdmin && (
                      <td>
                        <button className="btn btn-outline btn-sm"
                          onClick={() => toggle(r)}>
                          {r.enabled ? 'Disable' : 'Enable'}
                        </button>{' '}
                        <button className="btn btn-danger btn-sm"
                          onClick={() => remove(r.name)}>✕</button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {isAdmin && (
            <form className="rule-form" onSubmit={addRule}>
              <h4>Add custom rule</h4>
              <input placeholder="rule name" value={form.name} required
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <select value={form.metric}
                onChange={(e) => setForm({ ...form, metric: e.target.value })}>
                <option value="temperature_c">temperature_c</option>
                <option value="co2_ppm">co2_ppm</option>
                <option value="pm25">pm25</option>
                <option value="wind_speed_kph">wind_speed_kph</option>
                <option value="rainfall_mm">rainfall_mm</option>
                <option value="humidity_pct">humidity_pct</option>
              </select>
              <select value={form.comparator}
                onChange={(e) => setForm({ ...form, comparator: e.target.value })}>
                <option value="gt">exceeds (&gt;)</option>
                <option value="lt">below (&lt;)</option>
              </select>
              <input type="number" step="0.1" placeholder="threshold" required
                value={form.threshold}
                onChange={(e) => setForm({ ...form, threshold: e.target.value })} />
              <select value={form.severity}
                onChange={(e) => setForm({ ...form, severity: e.target.value })}>
                <option value="warning">warning</option>
                <option value="critical">critical</option>
              </select>
              <button className="btn btn-primary btn-sm">Add rule</button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
