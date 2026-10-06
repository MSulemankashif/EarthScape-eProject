import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import ProtectedRoute from "./auth/ProtectedRoute.jsx";
import Login from "./pages/Login.jsx";
import Forbidden from "./pages/Forbidden.jsx";
import Placeholder from "./pages/Placeholder.jsx";

const P = (title, task) => <Placeholder title={title} task={task} />;

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/forbidden" element={<Forbidden />} />

      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={P("Overview dashboard", "7.2")} />
        <Route path="anomalies" element={P("Anomalies", "7.3")} />
        <Route path="forecasts" element={P("Forecasts", "7.4")} />
        <Route path="correlations" element={P("Correlations", "7.5")} />
        <Route path="live" element={P("Live view", "7.7")} />
        <Route path="alerts" element={P("Alerts & rules", "6.9–6.12")} />
        <Route path="support" element={P("Support & feedback", "6.13")} />
        <Route path="help" element={P("Help (user guide / FAQ)", "9.4")} />

        {/* Admin only (server enforces too) */}
        <Route path="admin/users" element={<ProtectedRoute role="admin">{P("User management", "6.5")}</ProtectedRoute>} />
        <Route path="admin/ingestion" element={<ProtectedRoute role="admin">{P("Ingestion", "6.8")}</ProtectedRoute>} />
        <Route path="admin/models" element={<ProtectedRoute role="admin">{P("Models", "5.6")}</ProtectedRoute>} />
        <Route path="admin/monitoring" element={<ProtectedRoute role="admin">{P("Monitoring", "8.1")}</ProtectedRoute>} />
        <Route path="admin/audit" element={<ProtectedRoute role="admin">{P("Audit log", "6.5")}</ProtectedRoute>} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
