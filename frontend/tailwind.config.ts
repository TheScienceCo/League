import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // A restrained palette: one accent, a warm/cool pair for good/bad, and
        // neutrals that carry the rest. Charts reuse these tokens so the page
        // reads as one system.
        surface: {
          DEFAULT: "#0d1117",
          raised: "#151b23",
          overlay: "#1c232c",
          border: "#262d38",
        },
        ink: {
          DEFAULT: "#e6edf3",
          muted: "#9aa7b4",
          faint: "#6b7785",
        },
        accent: {
          DEFAULT: "#4c9aff",
          soft: "#2b5f9e",
        },
        good: "#3fb950",
        warn: "#d29922",
        bad: "#f85149",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
