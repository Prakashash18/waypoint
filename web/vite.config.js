import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built into the Flask app's static tree and served at /app, so the existing
// prebuilt SPA at / keeps working untouched.
export default defineConfig({
  plugins: [react()],
  base: '/app/',
  build: {
    outDir: '../src/ui/agent-app',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:2000', '/static': 'http://localhost:2000' },
  },
})
