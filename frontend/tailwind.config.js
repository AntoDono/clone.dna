/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{vue,js,ts}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans:    ['Outfit', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['Instrument Serif', 'Georgia', 'serif'],
        mono:    ['IBM Plex Mono', 'ui-monospace', 'monospace'],
      },
      colors: {
        parchment: '#FAF8F4',
        card:      '#FFFFFF',
        subtle:    '#F3F0EB',
        hover:     '#EDEAE4',
        border:    '#E2DDD6',
        mid:       '#CCC7BE',
        ink:       '#1C1811',
        stone:     '#6B6050',
        muted:     '#A8A098',
        forest: {
          DEFAULT: '#166534',
          mid:     '#15803D',
          light:   '#DCFCE7',
          text:    '#14532D',
        },
        amber: {
          warm:    '#92400E',
          light:   '#FEF3C7',
        },
        danger: {
          DEFAULT: '#991B1B',
          light:   '#FEE2E2',
        },
      },
      boxShadow: {
        soft: '0 1px 3px rgba(28,24,17,0.06), 0 1px 2px rgba(28,24,17,0.04)',
        card: '0 4px 12px rgba(28,24,17,0.08), 0 2px 4px rgba(28,24,17,0.04)',
      },
      letterSpacing: {
        tightest: '-0.03em',
        tighter:  '-0.02em',
      },
    },
  },
  plugins: [],
}
