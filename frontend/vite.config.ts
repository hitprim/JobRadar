import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api → backend для dev (без CORS-плясок)
const API_TARGET = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
    },
  },
});
