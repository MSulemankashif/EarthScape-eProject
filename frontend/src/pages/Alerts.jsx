/**
 * Alerts - notification history + configurable threshold rules.
 * Only admins can add/remove/toggle rules; everyone can watch the feed.
 */
import { useEffect, useState } from 'react'
import api, { errorMessage } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import { PageHeader } from '../components/Layout.jsx'
import { Spinner, ConfirmModal, EmptyState } from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'

const EMPTY_FORM = { name: '', metric: 'temperature_c', comparator: 'gt',
                     threshold: '', severity: 'warning' }

export default function Alerts() {
  const { isAdmin } = useAuth()
  const toast = useToast()
  const [alerts, setAlerts] = useState(null)
  const [stats, setStats] = useState(null)
  const [rules, setRules] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [severity, setSeverity] = useState('info')
  const [error, setError] = useState('')
  const [pendingDelete, setPendingDelete] = useState(null)

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
      setAlerts((prev) => prev || [])
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 8000)
    return () => clearInterval(id)
  }, [severity]) // eslint-disable-line react-hooks/exhaustive-deps

  const addRule = async (e) => {
    e.preventDefault()
    try {
      const { data } = await api.post('/alerts/rules', {
        ...form, threshold: Number(form.threshold),
      })
      setRules(data.rules)
      setForm(EMPTY_FORM)
      toast.success(`“${form.name}” now watches ${form.metric} ${form.comparator === 'gt' ? '>' : '<'} ${form.threshold}`,
        { title: 'Rule saved' })
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Could not save rule' })
    }
  }

  const toggle = async (rule) => {
    const action = rule.enabled ? 'disable' : 'enable'
    try {
      await api.post(`/alerts/rules/${rule.name}/${action}`)
      toast.info(`“${rule.name}” is now ${action}d`, { title: 'Rule updated' })
      load()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  const confirmDelete = async () => {
    const name = pendingDelete
    setPendingDelete(null)
    try {
      await api.delete(`/alerts/rules/${name}`)
      toast.success(`“${name}” was removed.`, { title: 'Rule deleted' })
      load()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  return (
    <div>
      <PageHeader
        title="Alerts & Notifications"
        subtitle="Every reading from batch files or the live stream is checked against these thresholds — you decide what counts as alarming."
        actions={(
          <select value={severity} onChange={(e) => setSeverity(e.target.value)}
            aria-label="Filter by severity">
            <option value="info">All severities</option>
            <option value="warning">Warning + critical</option>
            <option value="critical">Critical only</option>
          </select>
        )}
      />

      {stats && (
        <div className="model-status" style={{ marginBottom: 16 }}>
          <span className="tag tag-info">🔔 {stats.total} alerts</span>
          <span className="tag tag-critical">{stats.by_severity.critical} critical</span>
          <span className="tag tag-warning">{stats.by_severity.warning} warnings</span>
          <span className="tag tag-ok">{stats.enabled_rules}/{stats.total_rules} rules active</span>
        </div>
      )}

      {error && <div className="alert alert-error">{error}</div>}

      <div className="grid-2">
        <div className="card">
          <h3>Alert history</h3>
          {alerts === null ? (
            <Spinner label="Watching for events…" small={false} />
          ) : alerts.length === 0 ? (
            <EmptyState emoji="🌤️" title="All quiet — no alerts yet">
              <p>Sync live weather from the <strong>Live Weather</strong> page —
                every reading is checked against your rules on arrival, and any
                threshold breach appears here within seconds.</p>
            </EmptyState>
          ) : (
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
                </tbody>
              </table>
            </div>
          )}
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
                          {r.enabled ? 'Pause' : 'Enable'}
                        </button>{' '}
                        <button className="btn btn-danger btn-sm"
                          onClick={() => setPendingDelete(r.name)}
                          aria-label={`Delete rule ${r.name}`}>✕</button>
                      </td>
                    )}
                  </tr>
                ))}
                {rules.length === 0 && (
                  <tr><td colSpan={5} className="muted">No rules yet — add your first one below.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {isAdmin ? (
            <form className="rule-form" onSubmit={addRule}>
              <h4>➕ Add your own rule</h4>
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
          ) : (
            <p className="muted" style={{ marginTop: 12 }}>
              Only admins can edit rules — but you will see every alert they trigger.
            </p>
          )}
        </div>
      </div>

      <ConfirmModal
        open={Boolean(pendingDelete)}
        title="Delete this rule?"
        message={`“${pendingDelete}” will stop watching its threshold. Existing alert history stays untouched.`}
        confirmLabel="Yes, delete it"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
