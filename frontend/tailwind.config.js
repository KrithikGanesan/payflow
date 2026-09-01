/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Indigo is the ONLY brand accent.
        accent: {
          DEFAULT: "#4f46e5",
          fg: "#ffffff",
          soft: "#eef2ff",
          softdark: "#312e81",
        },
        // Neutral canvas
        canvas: {
          light: "#f6f7f9",
          dark: "#0b0d12",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      fontFeatureSettings: {
        tnum: '"tnum" 1',
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 3px 0 rgb(0 0 0 / 0.06)",
        lift: "0 4px 12px -2px rgb(0 0 0 / 0.10), 0 2px 6px -2px rgb(0 0 0 / 0.06)",
      },
      keyframes: {
        pulsering: {
          "0%": { boxShadow: "0 0 0 0 rgba(79,70,229,0.45)" },
          "70%": { boxShadow: "0 0 0 8px rgba(79,70,229,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(79,70,229,0)" },
        },
        fadein: {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        pulsering: "pulsering 1.6s cubic-bezier(0.4,0,0.6,1) infinite",
        fadein: "fadein 0.25s ease-out",
      },
    },
  },
  plugins: [],
};
