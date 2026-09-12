import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    // Build straight into the Python package so the dashboard ships as
    // package data (committed to git, included in the wheel).
    outDir: "../src/tokenscope/static",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Long-lived vendor chunks cache across releases; recharts only loads
        // with the pages that draw charts.
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          recharts: ["recharts"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8787",
    },
  },
});
