/**
 * Small shared UI atoms: Spinner, EmptyState and ConfirmModal.
 * They keep pages consistent and the tone friendly + guidance-first.
 */

export function Spinner({ label = 'Crunching climate data…', small = false }) {
  if (small) return <span className="spinner spinner-sm" aria-hidden="true" />
  return (
    <div className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span className="muted">{label}</span>
    </div>
  )
}

export function EmptyState({ emoji = '🌱', title, children, actions }) {
  return (
    <div className="card empty-state">
      <span className="empty-emoji" aria-hidden="true">{emoji}</span>
      <h3>{title}</h3>
      {children}
      {actions && <div className="empty-actions">{actions}</div>}
    </div>
  )
}

export function ConfirmModal({ open, title, message, confirmLabel = 'Yes, do it',
  onConfirm, onCancel, danger = false }) {
  if (!open) return null
  return (
    <div className="modal-overlay" onClick={onCancel} role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}
        onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="modal-actions">
          <button className="btn btn-outline" onClick={onCancel}>Cancel</button>
          <button className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
            onClick={onConfirm} autoFocus>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
