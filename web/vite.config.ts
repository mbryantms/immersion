import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// /api and /media go to the FastAPI dev server; in production Caddy owns both.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8770",
      "/media": "http://127.0.0.1:8770",
    },
  },
});
