import { Link } from "react-router-dom";

export default function Forbidden() {
  return (
    <div className="center">
      <div className="card">
        <h2>403 – Not allowed</h2>
        <p className="muted">Your role does not have access to this page.</p>
        <Link to="/">Back to dashboard</Link>
      </div>
    </div>
  );
}
