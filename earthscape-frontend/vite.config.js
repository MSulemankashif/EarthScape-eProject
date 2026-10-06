import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: React on :5173, proxy /api to FastAPI on :8000 (same-origin, so httpOnly cookies just work).
// Prod: `npm run build` -> dist/ is served by Apache, which also proxies /api to the Uvicorn instances.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: false } },
  },
});
