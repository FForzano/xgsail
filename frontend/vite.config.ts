import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// Dev server proxies /api to the FastAPI backend so cookies stay first-party
// (the browser only ever talks to :5173). Run the backend with
// SAILFRAMES_COOKIE_SECURE=0 so cookies are set over plain http in dev.
//
// Native (Capacitor) builds have no such proxy — the WebView talks directly
// to whatever origin VITE_API_BASE points at, so it must be set to the full
// backend URL (e.g. https://api.xgsail.com/api — the direct-to-backend
// Cloudflare Tunnel route, NOT xgsail.com/api which goes through nginx) at
// build time. See frontend/.env.native.example and docs/native-apps.md.
// This is also why native auth uses Bearer tokens rather than cookies (see
// api/client.ts), and why the WebView origin needs to be in the backend's
// SAILFRAMES_CORS_ORIGINS (see deploy/README.md) — unlike a fully native
// HTTP client, a WebView's fetch() is still subject to CORS.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      // Overridable so the same config works running on the host (backend
      // on localhost:8000) and running inside the docker-compose dev
      // override (backend reached via the compose service name).
      "/api": { target: process.env.VITE_BACKEND_PROXY_TARGET ?? "http://localhost:8000", changeOrigin: true },
    },
    // Docker Desktop's bind-mounted filesystem (docker-compose.dev.yml)
    // doesn't reliably forward inotify events from host to container, so
    // Vite's default watcher never sees host-side edits. Polling works
    // around it; only enabled inside that container (see VITE_DOCKER_DEV
    // in docker-compose.dev.yml), never on a native host run.
    watch: process.env.VITE_DOCKER_DEV ? { usePolling: true, interval: 300 } : undefined,
  },
  build: { outDir: "dist", sourcemap: true },
  base: "/",
});
