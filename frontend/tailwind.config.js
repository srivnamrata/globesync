/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './hooks/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      borderRadius: {
        control: '0.75rem',
        panel: '1rem',
        feature: '1.5rem',
      },
      boxShadow: {
        panel: '0 16px 40px rgba(2, 6, 23, 0.18)',
        focus: '0 0 0 3px rgba(129, 140, 248, 0.45)',
      },
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        },
      },
      transitionTimingFunction: {
        interface: 'cubic-bezier(0.2, 0, 0, 1)',
      },
      transitionDuration: {
        interface: '160ms',
      },
    },
  },
  plugins: [],
};
