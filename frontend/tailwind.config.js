/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // CSS-переменные подтягиваются из Telegram WebApp themeParams
        tg: {
          bg: "var(--tg-bg, #ffffff)",
          text: "var(--tg-text, #000000)",
          hint: "var(--tg-hint, #999999)",
          link: "var(--tg-link, #2481cc)",
          btn: "var(--tg-btn, #2481cc)",
          "btn-text": "var(--tg-btn-text, #ffffff)",
          "secondary-bg": "var(--tg-secondary-bg, #efeff3)",
          destructive: "var(--tg-destructive, #ff3b30)",
        },
      },
    },
  },
  plugins: [],
};
