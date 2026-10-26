import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// `npm run dev` runs in mock mode (.env.development, VITE_MOCK=1); `npm run dev:api` proxies /api to
// the FastAPI backend on :8000. Production builds never include the mock module.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1100,
  },
})
