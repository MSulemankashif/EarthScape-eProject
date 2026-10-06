import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError } from "../api/client.js";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

// Holds the current user ({ email, role, scopes }) from GET /me.
// NOTE: hiding UI by role is convenience only; the API enforces RBAC server-side.
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setUser(await api("/me"));
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 401) console.error(e);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = async (email, password) => {
    await api("/auth/login", { method: "POST", body: { email, password } });
    await refresh();
  };

  const logout = async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
    }
  };

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>;
}
