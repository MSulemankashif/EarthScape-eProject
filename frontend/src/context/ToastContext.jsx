/**
 * ToastContext - lightweight, friendly toast notifications.
 * Used across pages so actions give immediate, human feedback
 * ("Saved! 🎉" / "Something went wrong" instead of silent state).
 */
import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'

const ToastContext = createContext(null)

const ICONS = {
  success: '✅',
  error: '⚠️',
  warn: '🔔',
  info: 'ℹ️',
}

const TITLES = {
  success: 'Done',
  error: 'Oops',
  warn: 'Heads up',
  info: 'FYI',
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const counter = useRef(0)

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id))
  }, [])

  const push = useCallback((message, kind = 'info', opts = {}) => {
    const id = ++counter.current
    const ttl = opts.ttl ?? (kind === 'error' ? 7000 : 4500)
    setToasts((list) => [...list.slice(-3), {
      id, kind, message,
      title: opts.title || TITLES[kind] || 'Notice',
    }])
    if (ttl > 0) setTimeout(() => dismiss(id), ttl)
    return id
  }, [dismiss])

  const api = useMemo(() => ({
    push,
    dismiss,
    success: (m, opts) => push(m, 'success', opts),
    error: (m, opts) => push(m, 'error', opts),
    warn: (m, opts) => push(m, 'warn', opts),
    info: (m, opts) => push(m, 'info', opts),
  }), [push, dismiss])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toaster" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            <span className="toast-icon" aria-hidden="true">{ICONS[t.kind] || ICONS.info}</span>
            <div className="toast-body">
              <div className="toast-title">{t.title}</div>
              <div className="toast-msg">{t.message}</div>
            </div>
            <button className="toast-close" onClick={() => dismiss(t.id)}
              aria-label="Dismiss notification">✕</button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
