// Temporary page body. Each one is replaced by the real page in its task (see task.md Phase 6/7).
export default function Placeholder({ title, task }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      <p className="muted">Coming in task {task}.</p>
    </div>
  );
}
