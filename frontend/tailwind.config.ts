/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B0D10",
        surface: "#15181D",
        surfaceRaised: "#1B1F26",
        border: "#262B33",
        text: "#E9EBEE",
        muted: "#8890A0",
        // FIA-spec tire compound colors — the real, regulated colors used
        // on tyre sidewalls and broadcast graphics, not an invented palette.
        soft: "#F02D2D",
        medium: "#F5C51D",
        hard: "#F2F2F0",
        intermediate: "#3DAA35",
        wet: "#1E7FD1",
        // F1 timing-screen convention: purple marks the fastest sector/lap.
        fastest: "#9B4DFF",
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        body: ["var(--font-body)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      borderRadius: {
        DEFAULT: "2px",
        sm: "1px",
        md: "3px",
        lg: "4px",
      },
    },
  },
  plugins: [],
};
