import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext.jsx";

// <ProtectedRoute role="admin"> ... </ProtectedRoute>
// admin passes every role check; analyst only passes role="analyst".
export default function ProtectedRoute({ role, children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <p className="center muted">Loading…</p>;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  if (role === "admin" && user.role !== "admin") return <Navigate to="/forbidden" replace />;
  return children;
}
