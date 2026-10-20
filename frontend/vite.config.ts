import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { defineConfig } from "vitest/config";

// The browser calls /api/*; Vite forwards it to FastAPI with the /api prefix stripped.
const backend = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";

const { version } = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The app version, for the feedback link.
  define: { __APP_VERSION__: JSON.stringify(version) },
  build: {
    rollupOptions: {
      output: {
        // Chart libraries in their own cached chunks, with everything only recharts uses, so
        // pages without charts don't download it.
        manualChunks: (id) =>
          id.includes("node_modules/lightweight-charts") || id.includes("node_modules/fancy-canvas")
            ? "candles"
            : /node_modules\/(recharts|d3-[\w-]+|internmap|victory-vendor|@reduxjs|redux|react-redux|redux-thunk|immer|reselect|es-toolkit|decimal\.js-light|eventemitter3|tiny-invariant|use-sync-external-store|@standard-schema|clsx)\//.test(id)
              ? "recharts"
              : id.includes("node_modules")
                ? "vendor"
                : undefined,
      },
    },
  },
  server: {
    // This machine only. Docker sets VITE_HOST=0.0.0.0 (its port is still published on 127.0.0.1).
    host: process.env.VITE_HOST ?? "localhost",
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // tokens.test.ts reads these as text (?raw); other CSS stays stubbed out for speed.
    css: { include: [/src\/styles\/tokens\.css/, /src\/index\.css/] },
  },
});
