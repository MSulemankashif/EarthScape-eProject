/**
 * Admin - the admin console (admin role only):
 *   * user management (list + change roles)
 *   * one-click automated backups (list, create, verify)
 *   * system health + performance monitoring (processing times, freshness)
 */
import { useEffect, useState } from 'react'
import api, { errorMessage } from '../api/client.js'
import { PageHeader } from '../components/Layout.jsx'
import { Spinner, ConfirmModal, EmptyState } from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'

const fmtMB = (bytes) => `${(bytes / 1024 / 1024).toFixed(2)} MB`

function ago(iso) {
  if (!iso) return 'never'
  const mins = Math.round((Date.now() - new Date(iso)) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  if (mins < 1440) return `${Math.round(mins / 60)} h ago`
  return new Date(iso).toLocaleDateString()
}

export default function Admin() {
  const toast = useToast()
  const [users, setUsers] = useState(null)
  const [system, setSystem] = useState(null)
  const [backups, setBackups] = useState(null)
  const [busyBackup, setBusyBackup] = useState(false)
  const [confirmBackup, setConfirmBackup] = useState(false)

  const load = async () => {
    try {
      const [u, s] = await Promise.all([
        api.get('/auth/users'),
        api.get('/system/stats'),
      ])
      setUsers(u.data.users)
      setSystem(s.data)
      const b = await api.get('/system/backups')
      setBackups(b.data.backups)
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Could not load admin data' })
      setUsers((v) => v || [])
      setBackups((v) => v || [])
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const setRole = async (username, role) => {
    try {
      const { data } = await api.patch(`/auth/users/${username}/role`, { role })
      toast.success(data.message, { title: 'Role updated' })
      load()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  const runBackup = async () => {
    setConfirmBackup(false)
    setBusyBackup(true)
    try {
      const { data } = await api.post('/system/backup', { label: 'manual' })
      toast.success(
        `${data.backup.files} files → ${data.backup.file} (${fmtMB(data.backup.size_bytes)})`,
        { title: 'Backup complete 🛡️' },
      )
      load()
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Backup failed' })
    } finally {
      setBusyBackup(false)
    }
  }

  const verify = async (name) => {
    try {
      const { data } = await api.get(`/system/backups/${name}/verify`)
      toast.success(`Archive intact — ${data.members} members verified.`, { title: 'Integrity check passed' })
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Archive problem' })
    }
  }

  return (
    <div>
      <PageHeader
        title="Admin Console"
        subtitle="People, backups and the platform’s vital signs — everything a keeper of this system needs in one place."
      />

      {users === null && <Spinner label="Loading the admin console…" />}

      {users !== null && (
        <div className="grid-2">
          <div className="card">
            <h3>👥 Users ({users.length})</h3>
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
                        <select value={u.role} aria-label={`Role for ${u.username}`}
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
            <p className="muted" style={{ marginTop: 10 }}>
              Analysts can read and analyse; admins can additionally manage users,
              rules and backups.
            </p>
          </div>

          <div className="card">
            <div className="card-head">
              <h3 style={{ margin: 0 }}>🛡️ Data backups</h3>
              <button className="btn btn-warm btn-sm" onClick={() => setConfirmBackup(true)}
                disabled={busyBackup}>
                {busyBackup
                  ? <><span className="spinner spinner-sm" aria-hidden="true" /> Backing up…</>
                  : '📦 Back up now'}
              </button>
            </div>
            <p className="muted">
              Zips users, alerts, tickets, trained models, results and logs into
              <code> backups/</code> — the newest 14 are always kept.
            </p>
            {backups === null ? (
              <Spinner label="Reading backup folder…" small />
            ) : backups.length === 0 ? (
              <EmptyState emoji="📦" title="No backups yet">
                <p>Press <strong>Back up now</strong> to create your first point-in-time
                  snapshot of everything that cannot be regenerated.</p>
              </EmptyState>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Archive</th><th>Size</th><th>Created</th><th></th></tr>
                  </thead>
                  <tbody>
                    {backups.slice(0, 8).map((b) => (
                      <tr key={b.file}>
                        <td>{b.file}</td>
                        <td>{fmtMB(b.size_bytes)}</td>
                        <td>{ago(b.modified_at)}</td>
                        <td>
                          <button className="btn btn-outline btn-sm"
                            onClick={() => verify(b.file)}>Verify</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card">
            <h3>🩺 System health</h3>
            {system ? (
              <div className="model-status">
                <span className="tag tag-ok">uptime {(system.uptime_seconds / 60).toFixed(1)} min</span>
                <span className="tag">storage: {system.storage.backend}</span>
                <span className="tag">db: {system.database.backend}</span>
                <span className="tag">cpu: {system.cpu_count} cores</span>
                <span className="tag">storage used: {fmtMB(system.storage.total_bytes)}</span>
                <span className={system.stream_active ? 'tag tag-ok' : 'tag'}>
                  live stream: {system.stream_active ? 'active' : 'idle'}
                </span>
                <span className="tag tag-warn">alerts: {system.alerts.total} total
                  ({system.alerts.by_severity.critical} critical)</span>
                <span className={system.models.anomaly_model_trained ? 'tag tag-ok' : 'tag'}>
                  ml models: {system.models.anomaly_model_trained ? 'trained' : 'not trained'}
                </span>
                <span className="tag tag-info">
                  backups: {system.backups?.count ?? 0}
                  {system.backups?.latest ? ` · latest ${ago(system.backups.latest.modified_at)}` : ''}
                </span>
                {system.models.freshness && (
                  <span className="tag tag-ok">
                    models trained {ago(system.models.freshness.trained_at)}
                  </span>
                )}
                {system.log_files.map((f) => (
                  <span className="tag" key={f.name}>📄 {f.name} ({f.size_kb} KB)</span>
                ))}
              </div>
            ) : (
              <p className="muted">Loading…</p>
            )}
          </div>

          <div className="card">
            <h3>⏱️ Data-processing times</h3>
            {system?.processing?.recent_jobs?.length > 0 ? (
              <>
                <div className="model-status">
                  <span className="tag tag-info">{system.processing.job_count} jobs this session</span>
                  <span className="tag tag-ok">avg {system.processing.avg_seconds}s</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr><th>Job</th><th>Rows</th><th>Duration</th><th>Finished</th></tr>
                    </thead>
                    <tbody>
                      {[...system.processing.recent_jobs].reverse().map((j, i) => (
                        <tr key={`${j.name}-${j.finished_at}-${i}`}>
                          <td>{j.name}</td>
                          <td>{j.rows.toLocaleString()}</td>
                          <td><span className="time-chip">⏱ {j.duration_seconds}s</span></td>
                          <td className="muted">{j.finished_at?.slice(11, 19)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <p className="muted">
                Run a MapReduce job or train the ML models — every run is timed here so
                you can spot slow work.
              </p>
            )}
          </div>
        </div>
      )}

      <ConfirmModal
        open={confirmBackup}
        title="Create a backup now?"
        message="This archives users, alerts, tickets, models, processed results and logs into a timestamped zip. Nothing is overwritten, and only the newest 14 archives are kept."
        confirmLabel="Yes, back it up"
        onConfirm={runBackup}
        onCancel={() => setConfirmBackup(false)}
      />
    </div>
  )
}
