/**
 * Feedback - support ticket system. Users submit tickets and see their own;
 * admins see all tickets and can update their status.
 */
import { useEffect, useState } from 'react'
import api, { errorMessage } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'

const CATEGORIES = ['feedback', 'bug', 'data issue', 'feature request', 'other']

export default function Feedback() {
  const { user, isAdmin } = useAuth()
  const [tickets, setTickets] = useState([])
  const [form, setForm] = useState({ subject: '', message: '', category: 'feedback' })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      const { data } = await api.get('/feedback')
      setTickets(data.tickets)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  useEffect(() => { load() }, [])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.post('/feedback', form)
      setNotice('Ticket submitted — thank you! 🎉')
      setForm({ subject: '', message: '', category: 'feedback' })
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const setStatus = async (id, status) => {
    await api.patch(`/feedback/${id}`, { status })
    load()
  }

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Feedback & Support</h2>
          <p className="muted">Report issues, ask for help or suggest improvements.</p>
        </div>
      </header>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-info">{notice}</div>}

      <div className="grid-2">
        <div className="card">
          <h3>Open a ticket</h3>
          <form className="stacked-form" onSubmit={submit}>
            <label>Category
              <select value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label>Subject
              <input value={form.subject} required maxLength={200}
                placeholder="Short summary"
                onChange={(e) => setForm({ ...form, subject: e.target.value })} />
            </label>
            <label>Message
              <textarea rows={5} value={form.message} required maxLength={2000}
                placeholder="Describe your issue or feedback…"
                onChange={(e) => setForm({ ...form, message: e.target.value })} />
            </label>
            <button className="btn btn-primary" disabled={busy}>
              {busy ? 'Submitting…' : 'Submit ticket'}
            </button>
          </form>
        </div>

        <div className="card">
          <h3>{isAdmin ? 'All tickets' : 'My tickets'} ({tickets.length})</h3>
          <div className="ticket-list">
            {tickets.map((t) => (
              <div className="ticket" key={t._id}>
                <div className="ticket-head">
                  <strong>{t.subject}</strong>
                  <span className={`tag tag-status-${t.status}`}>{t.status}</span>
                </div>
                <p className="muted">
                  {t.category} · by {t.user} · {t.created_at?.slice(0, 16).replace('T', ' ')}
                </p>
                <p>{t.message}</p>
                {isAdmin && (
                  <div className="ticket-actions">
                    {['open', 'in_progress', 'resolved']
                      .filter((s) => s !== t.status)
                      .map((s) => (
                        <button key={s} className="btn btn-outline btn-sm"
                          onClick={() => setStatus(t._id, s)}>
                          Mark {s.replace('_', ' ')}
                        </button>
                      ))}
                  </div>
                )}
              </div>
            ))}
            {tickets.length === 0 && (
              <p className="muted">No tickets yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
