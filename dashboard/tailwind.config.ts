import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Geist", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      colors: {
        bg: {
          base: "#0A0B0D",
          surface: "#111318",
          elevated: "#171A21",
          overlay: "#1E2028",
        },
        border: {
          DEFAULT: "#1E2028",
          subtle: "#16181E",
          strong: "#2A2D38",
        },
        primary: {
          DEFAULT: "#3B82F6",
          hover: "#2563EB",
          muted: "#1D4ED8",
          dim: "rgba(59,130,246,0.12)",
        },
        success: {
          DEFAULT: "#10B981",
          hover: "#059669",
          dim: "rgba(16,185,129,0.12)",
        },
        danger: {
          DEFAULT: "#EF4444",
          hover: "#DC2626",
          dim: "rgba(239,68,68,0.12)",
        },
        warning: {
          DEFAULT: "#F59E0B",
          hover: "#D97706",
          dim: "rgba(245,158,11,0.12)",
        },
        text: {
          primary: "#F1F3F9",
          secondary: "#8B8FA8",
          muted: "#4B5066",
          inverse: "#0A0B0D",
        },
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in-right": "slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
        pulse_slow: "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "shimmer": "shimmer 2s infinite linear",
        "ticker": "ticker 20s linear infinite",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        slideUp: {
          from: { opacity: "0", transform: "translateY(16px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        slideInRight: {
          from: { opacity: "0", transform: "translateX(16px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-1000px 0" },
          "100%": { backgroundPosition: "1000px 0" },
        },
        ticker: {
          "0%": { transform: "translateX(100%)" },
          "100%": { transform: "translateX(-100%)" },
        },
      },
      backdropBlur: {
        xs: "2px",
      },
      boxShadow: {
        glow: "0 0 20px rgba(59,130,246,0.15)",
        "glow-success": "0 0 20px rgba(16,185,129,0.15)",
        "glow-danger": "0 0 20px rgba(239,68,68,0.15)",
        card: "0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3)",
        "card-hover": "0 4px 12px rgba(0,0,0,0.5), 0 2px 6px rgba(0,0,0,0.4)",
      },
    },
  },
  plugins: [],
} satisfies Config;
