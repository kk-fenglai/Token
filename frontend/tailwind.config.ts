import type { Config } from "tailwindcss";

// Design tokens from stitch_tokenscope_dashboard/tokenscope/DESIGN.md
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#005589",
        "primary-container": "#0f6ead",
        "on-primary": "#ffffff",
        secondary: "#974800",
        "secondary-container": "#fc9349",
        surface: "#f7f9fb",
        "surface-card": "#ffffff",
        "on-surface": "#191c20",
        "on-surface-variant": "#404750",
        outline: "#717881",
        "outline-variant": "#c0c7d1",
        "border-card": "#e1e4e8",
        error: "#ba1a1a",
        "error-container": "#ffdad6",
        "on-error-container": "#93000a",
        success: "#1b6d43",
        "success-container": "#d5f1e0",
        "on-success-container": "#04452a",
        // chart series colors (DESIGN.md data-centric palette)
        "chart-input": "#0F6EAD",
        "chart-output": "#E8833A",
        "chart-cache-write": "#7C9CB5",
        "chart-cache-read": "#C9D8E4",
        tooltip: "#1a1c1e",
      },
      fontFamily: {
        sans: ["Inter", "PingFang SC", "Microsoft YaHei", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      borderRadius: {
        DEFAULT: "0.5rem",
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.05), 0 1px 2px rgba(0,0,0,0.03)",
        float: "0 10px 15px -3px rgba(0,0,0,0.08)",
      },
      maxWidth: {
        container: "1440px",
      },
    },
  },
  plugins: [],
} satisfies Config;
