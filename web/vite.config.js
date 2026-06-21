import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:3001",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
    css: false,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{js,jsx}"],
      exclude: [
        "src/test/**",
        "src/main.jsx",
        "src/App.jsx",
        "src/utils/tts.js",
      ],
      thresholds: {
        lines: 85,
        functions: 75,
        branches: 72,
        statements: 80,
      },
    },
  },
})
