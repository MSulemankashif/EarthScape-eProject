/**
 * Feedback - support ticket system. Users submit tickets and see their own;
 * admins see all tickets and can update their status.
 */
import { useEffect, useState } from 'react'
import api, { errorMessage } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import { PageHeader } from '../components/Layout.jsx'
import { Spinner, EmptyState } from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'

const CATEGORIES = ['feedback', 'bug', 'data issue', 'feature request', 'other']

export default function Feedback() {
  const { user, isAdmin } = useAuth()
  const toast = useToast()
  const [tickets, setTickets] = useState(null)
  const [form, setForm] = useState({ subject: '', message: '', category: 'feedback' })
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      const { data } = await api.get('/feedback')
      setTickets(data.tickets)
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Could not load tickets' })
      setTickets([])
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      await api.post('/feedback', form)
      toast.success('Your ticket is in the queue — we will get back to you! 🎉',
        { title: 'Ticket submitted' })
      setForm({ subject: '', message: '', category: 'feedback' })
      load()
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Could not submit ticket' })
    } finally {
      setBusy(false)
    }
  }

  const setStatus = async (id, status) => {
    try {
      await api.patch(`/feedback/${id}`, { status })
      toast.info(`Ticket marked as ${status.replace('_', ' ')}`)
      load()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  return (
    <div>
      <PageHeader
        title="Feedback & Support"
        subtitle="Something look wrong? Missing a feature? Or just want to say thanks — this reaches the same team that runs the platform."
      />

      <div className="grid-2">
        <div className="card">
          <h3>✍️ Open a ticket</h3>
          <form className="stacked-form" onSubmit={submit}>
            <label>Category
              <select value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label>Subject
              <input value={form.subject} required maxLength={200}
                placeholder="One-line summary, e.g. “Wrong PM2.5 on STN-004”"
                onChange={(e) => setForm({ ...form, subject: e.target.value })} />
            </label>
            <label>Message
              <textarea rows={5} value={form.message} required maxLength={2000}
                placeholder="What happened, what you expected, and how we can reproduce it…"
                onChange={(e) => setForm({ ...form, message: e.target.value })} />
            </label>
            <button className="btn btn-primary" disabled={busy}>
              {busy
                ? <><span className="spinner spinner-sm" aria-hidden="true" /> Sending…</>
                : '📨 Submit ticket'}
            </button>
          </form>
        </div>

        <div className="card">
          <h3>{isAdmin ? 'All tickets' : 'My tickets'} ({tickets?.length ?? '…'})</h3>
          {tickets === null ? (
            <Spinner label="Loading your tickets…" />
          ) : tickets.length === 0 ? (
            <EmptyState emoji="💬" title="No tickets yet">
              <p>Your submitted issues and ideas will show up here with a status you
                can track from <em>open</em> to <em>resolved</em>.</p>
            </EmptyState>
          ) : (
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
            </div>
          )}
          {!isAdmin && tickets?.length > 0 && (
            <p className="muted" style={{ marginTop: 10 }}>
              Signed in as <strong>{user?.username}</strong> — you see only your own tickets.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
