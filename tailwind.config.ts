import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        background: "#0b0f19",
        surface: "#131826",
        accent: "#6366f1",
      },
    },
  },
  plugins: [],
};

export default config;
