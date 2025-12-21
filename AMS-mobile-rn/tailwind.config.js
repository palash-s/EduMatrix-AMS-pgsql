/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./App.{js,jsx,ts,tsx}', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        mit: {
          purple: '#48166d',
          purpleDark: '#2d0d45',
          purpleHover: '#350f50',
          teal: '#00a887',
          orange: '#f17736',
          gold: '#bf9d55',
          slateBg: '#f8fafc',
        },
      },
    },
  },
  plugins: [],
};
